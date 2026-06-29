"""
value_bets.py — Predicción de eventos de partido (córners, tarjetas, tiros, faltas)
con modelo Poisson + ajuste por fuerza del rival + detección de edges contra cuotas reales.
"""
import json, math
from pathlib import Path
from collections import defaultdict

# ─── Configuración ───────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data" / "worldcup"
ALL_MATCHES = DATA_DIR / "all_matches.json"

# Stats que vamos a predecir
PREDICTABLE_STATS = {
    'cornerKicks':    {'label': 'Córners',    'icon': '🏳️',   'avg_range': (5, 15)},
    'yellowCards':    {'label': 'Tarjetas',   'icon': '🟨',   'avg_range': (1, 6)},
    'totalShotsOnGoal': {'label': 'Tiros Totales', 'icon': '🎯', 'avg_range': (8, 32)},
    'shotsOnGoal':    {'label': 'Tiros Puerta', 'icon': '🥅',  'avg_range': (2, 14)},
    'fouls':          {'label': 'Faltas',      'icon': '⚡',   'avg_range': (8, 30)},
}

# Líneas Over/Under que vamos a evaluar para cada stat
EVALUATION_LINES = {
    'cornerKicks': [7.5, 8.5, 9.5, 10.5],
    'yellowCards': [2.5, 3.5, 4.5],
    'totalShotsOnGoal': [12.5, 14.5, 16.5, 18.5, 22.5],
    'shotsOnGoal': [6.5, 7.5, 8.5, 10.5],
    'fouls': [18.5, 20.5, 22.5, 24.5],
}


def load_all_matches():
    with open(ALL_MATCHES) as f:
        return json.load(f)


def compute_team_averages(matches):
    """Calcula promedios POR equipo Y lo que CADA equipo PERMITE al rival"""
    team_for = defaultdict(lambda: defaultdict(list))
    team_against = defaultdict(lambda: defaultdict(list))  # lo que PERMITE al rival
    opponents = defaultdict(list)  # a quiénes se enfrentó cada equipo

    for m in matches:
        home = m.get('home_team', '?')
        away = m.get('away_team', '?')
        for period in m.get('statistics', []):
            if period['period'] != 'ALL':
                continue
            for group in period['groups']:
                for item in group['statisticsItems']:
                    key = item['key']
                    hv = item.get('homeValue')
                    av = item.get('awayValue')
                    if hv is not None:
                        team_for[home][key].append(hv)
                        team_against[away][key].append(hv)  # lo que el away PERMITIÓ al home
                    if av is not None:
                        team_for[away][key].append(av)
                        team_against[home][key].append(av)

            # Guardar oponentes (solo una vez por partido)
            opponents[home].append(away)
            opponents[away].append(home)
            break  # solo ALL

    # Calcular promedios
    result = {}
    all_teams = set(team_for.keys()) | set(team_against.keys())
    for team in all_teams:
        result[team] = {'for': {}, 'against': {}, 'opponents': opponents.get(team, [])}
        for key in PREDICTABLE_STATS:
            f_vals = team_for[team].get(key, [])
            a_vals = team_against[team].get(key, [])
            result[team]['for'][key] = sum(f_vals) / len(f_vals) if f_vals else 0
            result[team]['against'][key] = sum(a_vals) / len(a_vals) if a_vals else 0

    return result


def adjusted_prediction(team_stats, home_team, away_team, stat_key):
    """Predice eventos esperados para un partido con ajuste por rival.
    Fórmula: (media_a_favor_A * media_en_contra_B) / media_liga_en_contra
    
    Esto ajusta: si B permite MÁS córners que la media de la liga, A tendrá más córners.
    """
    ht = team_stats.get(home_team, {})
    at = team_stats.get(away_team, {})

    h_fav = ht.get('for', {}).get(stat_key, 0)
    h_con = ht.get('against', {}).get(stat_key, 0)
    a_fav = at.get('for', {}).get(stat_key, 0)
    a_con = at.get('against', {}).get(stat_key, 0)

    if h_fav + a_con < 0.5 or a_fav + h_con < 0.5:
        return 0, 0

    # Media de la liga para este stat (lo que todos los equipos permiten)
    all_against = [t['against'].get(stat_key, 0) for t in team_stats.values()]
    all_against = [x for x in all_against if x > 0]
    league_against = sum(all_against) / len(all_against) if all_against else 1

    # Predicción: media del equipo × ratio del rival vs liga
    ratio_a = a_con / league_against if league_against > 0 else 1
    ratio_b = h_con / league_against if league_against > 0 else 1

    pred_home = h_fav * ratio_a
    pred_away = a_fav * ratio_b

    return round(pred_home, 2), round(pred_away, 2)


def poisson_prob(lam, k):
    """P(X = k) para Poisson"""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def over_prob(lam, line):
    """P(X > line) usando Poisson. Retorna 0-1"""
    if lam <= 0:
        return 0.0
    # Sumar hasta 2x lambda + 20 para cubrir cola (converge rápido)
    cumulative = sum(poisson_prob(lam, k) for k in range(int(line) + 1))
    # Si lam es muy alto y la línea es baja, Poisson se aproxima a 1
    return max(0.0, min(1.0, 1 - cumulative))


def build_value_bets(matches_data, odds_cache):
    """Construye TODAS las recomendaciones de value bets.
    
    Para cada partido y cada stat, calcula la probabilidad de Over en cada línea,
    la cruza con la cuota de bet365 si existe, y detecta edges positivos.
    
    Retorna lista de value bets ordenada por edge descendente.
    """
    team_stats = compute_team_averages(matches_data)
    value_bets = []

    # Partidos de hoy
    today_matches = [
        ("Brazil", "Japan"),
        ("Germany", "Paraguay"),
        ("Netherlands", "Morocco"),
    ]

    for home_team, away_team in today_matches:
        # Buscar cuotas en caché
        match_odds = None
        for fid, info in odds_cache.items():
            ch = info.get("home", "").lower().strip()
            ca = info.get("away", "").lower().strip()
            hl = home_team.lower().strip()
            al = away_team.lower().strip()
            if (ch == hl or hl in ch or ch in hl) and \
               (ca == al or al in ca or ca in al):
                match_odds = info.get("odds", {})
                break

        bet365 = (match_odds or {}).get("bet365", {})

        for stat_key, stat_info in PREDICTABLE_STATS.items():
            # Calcular predicción total del partido
            pred_h, pred_a = adjusted_prediction(team_stats, home_team, away_team, stat_key)
            total_pred = pred_h + pred_a

            if total_pred < 0.5:
                continue  # sin datos suficientes

            team_h_for = team_stats.get(home_team, {}).get('for', {}).get(stat_key, 0)
            team_a_for = team_stats.get(away_team, {}).get('for', {}).get(stat_key, 0)
            team_h_against = team_stats.get(home_team, {}).get('against', {}).get(stat_key, 0)
            team_a_against = team_stats.get(away_team, {}).get('against', {}).get(stat_key, 0)

            # Evaluar cada línea
            for line in EVALUATION_LINES.get(stat_key, []):
                prob = over_prob(total_pred, line)

                # Buscar cuota real en bet365
                bet365_stat = bet365.get(stat_key, {})
                over_key = f"over_{line}"
                under_key = f"under_{line}"
                odd = bet365_stat.get(over_key)
                odd_under = bet365_stat.get(under_key)

                if not odd:
                    continue  # sin cuota real, no hay edge

                # Edge = probabilidad modelo - probabilidad implícita de la cuota
                implied = 1.0 / odd if odd > 0 else 0
                edge_pct = round((prob - implied) * 100, 1)

                # Solo mostrar bets con edge positivo (o cercano a 0 para info)
                # Mostramos todas para que el usuario tenga contexto, 
                # pero marcamos claramente las positivas
                if edge_pct >= -2:  # mostramos desde -2% para comparación
                    ev = round((prob * odd * 100) - 100, 1)
                    value_bets.append({
                        'match': f"{home_team} vs {away_team}",
                        'home': home_team, 'away': away_team,
                        'stat_key': stat_key,
                        'label': stat_info['label'],
                        'icon': stat_info['icon'],
                        'line': line,
                        'total_pred': round(total_pred, 1),
                        'pred_home': pred_h,
                        'pred_away': pred_a,
                        'prob_over': round(prob * 100, 1),
                        'odd': round(odd, 2),
                        'implied_pct': round(implied * 100, 1),
                        'edge_pct': edge_pct,
                        'ev_pct': ev,
                        'team_h_for': round(team_h_for, 1),
                        'team_a_for': round(team_a_for, 1),
                        'team_h_against': round(team_h_against, 1),
                        'team_a_against': round(team_a_against, 1),
                    })

    # Ordenar por edge descendente (más positivos primero)
    value_bets.sort(key=lambda x: x['edge_pct'], reverse=True)

    return value_bets, team_stats
