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
        ("Ivory Coast", "Norway"),
        ("France", "Sweden"),
        ("Mexico", "Ecuador"),
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
    
    # DEDUPLICAR: solo mejor línea por partido+stat (mayor EV)
    seen = {}
    deduped = []
    for vb in value_bets:
        key = (vb['match'], vb['stat_key'])
        if key in seen:
            # Quedarse con el de mayor EV
            if vb['ev_pct'] > seen[key]['ev_pct']:
                seen[key] = vb
        else:
            seen[key] = vb
    value_bets = sorted(seen.values(), key=lambda x: x['edge_pct'], reverse=True)

    return value_bets, team_stats


def build_matchup_narrative(home_team, away_team, team_stats):
    """Genera una narrativa estadística del enfrentamiento comparando 
    medias de cada equipo, lo que permiten al rival, y detectando puntos clave.
    
    Retorna un string HTML listo para insertar en la web."""
    
    LABELS = {
        'cornerKicks': 'córners', 'yellowCards': 'tarjetas amarillas',
        'totalShotsOnGoal': 'disparos totales', 'shotsOnGoal': 'tiros a puerta',
        'fouls': 'faltas'
    }
    ICONS = {
        'cornerKicks': '🏳️', 'yellowCards': '🟨', 'totalShotsOnGoal': '⚽',
        'shotsOnGoal': '🎯', 'fouls': '⚡'
    }
    
    ht = team_stats.get(home_team, {})
    at = team_stats.get(away_team, {})
    if not ht or not at:
        return ''
    
    h_for = ht.get('for', {})
    h_ag = ht.get('against', {})
    a_for = at.get('for', {})
    a_ag = at.get('against', {})
    
    # Media de liga para referencia
    all_for = {}
    for key in LABELS:
        vals = [t['for'].get(key, 0) for t in team_stats.values() if t['for'].get(key, 0) > 0]
        all_for[key] = sum(vals) / len(vals) if vals else 1
    
    # Construir frases narrativas para los 5 stats
    phrases = []
    
    for key in ['shotsOnGoal', 'cornerKicks', 'yellowCards', 'totalShotsOnGoal', 'fouls']:
        hf = h_for.get(key, 0)
        af = a_for.get(key, 0)
        ha = h_ag.get(key, 0)
        aa = a_ag.get(key, 0)
        liga = all_for[key]
        label = LABELS[key]
        icon = ICONS[key]
        
        if hf < 0.3 and af < 0.3:
            continue
        
        total = hf + af
        
        # Frase narrativa
        if hf >= af * 1.5:
            # Local domina mucho
            pct = int((hf - liga) / liga * 100) if liga > 0 else 0
            pct = abs(pct)
            if aa > liga * 1.1:
                phrases.append(
                    f"{icon} Se esperan <strong>~{total:.0f} {label}</strong>. "
                    f"{home_team} genera <strong>{hf:.1f}</strong> (+{pct}% sobre la media) "
                    f"y {away_team} encaja {aa:.1f} por partido."
                )
            else:
                phrases.append(
                    f"{icon} Dominio claro de {home_team} en {label}: <strong>{hf:.1f}</strong> por partido "
                    f"frente a solo {af:.1f} de {away_team}. Se esperan ~{total:.0f} en total."
                )
        elif af >= hf * 1.5:
            # Visitante domina mucho
            pct = int((af - liga) / liga * 100) if liga > 0 else 0
            pct = abs(pct)
            if ha > liga * 1.1:
                phrases.append(
                    f"{icon} Ojo a {away_team}: promedia <strong>{af:.1f} {label}</strong> (+{pct}% sobre la media) "
                    f"y {home_team} permite {ha:.1f}. Se esperan ~{total:.0f} en total."
                )
            else:
                phrases.append(
                    f"{icon} {away_team} llega con <strong>{af:.1f} {label}</strong> por partido "
                    f"vs {hf:.1f} de {home_team}. Se esperan ~{total:.0f}."
                )
        elif abs(hf - af) > liga * 0.4:
            # Diferencia notable pero no abismal
            stronger = home_team if hf > af else away_team
            weaker = away_team if hf > af else home_team
            s_val = max(hf, af)
            w_val = min(hf, af)
            phrases.append(
                f"{icon} {stronger} ({s_val:.1f}) supera a {weaker} ({w_val:.1f}) en {label}. "
                f"Se esperan ~{total:.0f} en total."
            )
        else:
            # Equilibrado
            if hf > liga * 1.05 and af > liga * 1.05:
                phrases.append(
                    f"{icon} Ambos equipos por encima de la media en {label}: "
                    f"{hf:.1f} y {af:.1f}. Partido con ~{total:.0f} esperados."
                )
            elif hf < liga * 0.95 and af < liga * 0.95:
                phrases.append(
                    f"{icon} Pocos {label} esperados: {hf:.1f} y {af:.1f} por partido "
                    f"(ambos por debajo de la media de {liga:.1f})."
                )
            else:
                phrases.append(
                    f"{icon} Equilibrio en {label}: {home_team} {hf:.1f} — {away_team} {af:.1f}. "
                    f"Total esperado ~{total:.0f}."
                )
    
    if not phrases:
        return ''
    
    # Cabecera con resumen del partido
    html = '<div class="matchup-narrative"><strong>🔬 Radiografía estadística del partido</strong>'
    for p in phrases:
        html += f'<div class="narrative-line">{p}</div>\n'
    html += '</div>'
    
    return html


# ─── COMPARATIVA PREDICHO vs REAL ──────────────────────────────────

def load_real_stats():
    """Carga estadísticas reales de partidos ya jugados desde data/real_stats.json
    y/o desde la caché de Sofascore (data/sofascore_cache/).
    """
    real = {}
    
    # 1. Cargar del archivo principal
    real_path = DATA_DIR.parent / "real_stats.json"
    if real_path.exists():
        with open(real_path) as f:
            data = json.load(f)
        for key, val in data.items():
            if key.startswith('_'):
                continue
            real[key] = val
    
    # 2. Cargar de la caché de Sofascore (datos frescos de API)
    cache_dir = DATA_DIR.parent / "sofascore_cache"
    if cache_dir.exists():
        for cache_file in cache_dir.glob("event_*.json"):
            try:
                with open(cache_file) as f:
                    cached = json.load(f)
                stats = cached.get('stats', {})
                if stats:
                    # Buscar el match key correspondiente
                    eid = cache_file.stem.replace('event_', '')
                    # Intentar mapear stats al formato estándar
                    mapped = {}
                    for sk in PREDICTABLE_STATS:
                        if sk in stats:
                            mapped[sk] = stats[sk]
                    if mapped:
                        key = f"event_{eid}"
                        if key not in real:
                            real[key] = {'event_id': int(eid), **mapped}
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
    
    return real


def compare_predictions(predictions, real_stats):
    """
    Compara las predicciones del modelo con estadísticas reales.
    
    Args:
        predictions: lista de dicts con {home_team, away_team, ...} (de worldcup_web.py)
        real_stats: dict de real_stats.json
    
    Retorna lista de comparaciones por partido+stat, con error absoluto y relativo.
    """
    comparisons = []
    
    # Construir índice de real_stats por nombre de equipo
    real_index = {}
    for key, val in real_stats.items():
        if key.startswith('_'):
            continue
        if val.get('_blocked'):
            continue
        home = key.split(' vs ')[0] if ' vs ' in key else ''
        away = key.split(' vs ')[1] if ' vs ' in key else ''
        real_index[(home.lower(), away.lower())] = val
        # También intentar con orden inverso
        real_index[(away.lower(), home.lower())] = val
    
    for pred in predictions:
        home = pred.get('home_team', '')
        away = pred.get('away_team', '')
        match_key = (home.lower().strip(), away.lower().strip())
        real = real_index.get(match_key)
        
        if not real:
            continue
        
        for stat_key in PREDICTABLE_STATS:
            if stat_key not in real:
                continue
            
            real_total = real[stat_key].get('total')
            real_home = real[stat_key].get('home')
            real_away = real[stat_key].get('away')
            
            if real_total is None:
                continue
            
            # Obtener predicción del modelo (si existe en los datos)
            pred_total = None
            pred_home = None
            pred_away = None
            
            # Intentar de 'value_bets' del prediction dict
            vb_list = pred.get('value_bets', [])
            for vb in vb_list:
                if vb.get('stat_key') == stat_key:
                    # Tomar la mejor línea (mayor ev_pct)
                    if pred_total is None or vb.get('ev_pct', -999) > getattr(comparisons[-1] if comparisons else None, 'best_ev', -999):
                        pred_total = vb.get('total_pred')
                        pred_home = vb.get('pred_home')
                        pred_away = vb.get('pred_away')
            
            # Si no hay value_bets, intentar de team_stats
            if pred_total is None:
                # Buscar en los datos cargados
                continue
            
            error_abs = round(abs(pred_total - real_total), 1)
            error_pct = round(error_abs / real_total * 100, 1) if real_total > 0 else 0
            accuracy = round(max(0, 100 - error_pct), 1)
            
            comparisons.append({
                'match': f"{home} vs {away}",
                'home': home,
                'away': away,
                'stat_key': stat_key,
                'label': PREDICTABLE_STATS[stat_key]['label'],
                'icon': PREDICTABLE_STATS[stat_key]['icon'],
                'pred_total': pred_total,
                'pred_home': pred_home,
                'pred_away': pred_away,
                'real_total': real_total,
                'real_home': real_home,
                'real_away': real_away,
                'error_abs': error_abs,
                'error_pct': error_pct,
                'accuracy': accuracy,
            })
    
    # Ordenar por precisión (mayor a menor = mejores predicciones)
    comparisons.sort(key=lambda x: x['accuracy'], reverse=True)
    
    return comparisons


def build_comparison_html(comparisons):
    """
    Genera HTML para la sección de comparativa Predicho vs Real.
    """
    if not comparisons:
        return '<div class="no-value-bets">🔍 No hay datos reales para comparar aún. Los partidos deben haberse jugado y tener estadísticas en data/real_stats.json.</div>'
    
    # Agrupar por partido
    by_match = {}
    for c in comparisons:
        m = c['match']
        if m not in by_match:
            by_match[m] = []
        by_match[m].append(c)
    
    html = '<div class="comparison-intro">📊 Comparativa: Predicciones del modelo vs Estadísticas Reales (Sofascore)</div>\n'
    
    for match_name, items in by_match.items():
        # Calcular precisión media del partido
        avg_acc = sum(c['accuracy'] for c in items) / len(items)
        acc_color = '#60f0a0' if avg_acc >= 80 else '#f0c040' if avg_acc >= 60 else '#f060a0'
        
        html += f'''
        <div class="comparison-match">
            <div class="comparison-match-header">
                <span class="comparison-match-name">⚽ {match_name}</span>
                <span class="comparison-avg-acc" style="color: {acc_color}">Precisión media: {avg_acc:.0f}%</span>
            </div>
            <div class="comparison-grid">
'''
        for c in items:
            # Barra visual de precisión
            bar_width = c['accuracy']
            bar_color = '#60f0a0' if c['accuracy'] >= 80 else '#f0c040' if c['accuracy'] >= 60 else '#f060a0'
            
            # Calcular dirección del error (sobreestimó o subestimó)
            over_under = ''
            if c['pred_total'] > c['real_total']:
                over_under = '⬆️ +' + str(round(c['pred_total'] - c['real_total'], 1))
            elif c['pred_total'] < c['real_total']:
                over_under = '⬇️ -' + str(round(c['real_total'] - c['pred_total'], 1))
            else:
                over_under = '✅ Exacto'
            
            html += f'''
                <div class="comparison-row">
                    <div class="comparison-stat-name">{c['icon']} {c['label']}</div>
                    <div class="comparison-values">
                        <span class="comp-pred">Pred: <strong>{c['pred_total']:.1f}</strong></span>
                        <span class="comp-vs">vs</span>
                        <span class="comp-real">Real: <strong>{c['real_total']}</strong></span>
                        <span class="comp-diff">{over_under}</span>
                    </div>
                    <div class="comparison-bar-track">
                        <div class="comparison-bar-fill" style="width: {bar_width}%; background: {bar_color}"></div>
                    </div>
                    <div class="comparison-acc" style="color: {bar_color}">{c['accuracy']:.0f}% acierto</div>
                </div>
'''
        html += '''
            </div>
        </div>
'''
    
    return html
