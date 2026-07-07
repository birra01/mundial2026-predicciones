#!/usr/bin/env python3
"""
backfill_tracker.py — Carga datos históricos en el tracker de aprendizaje.
Ejecutar una vez para entrenar el sistema con partidos ya jugados.
"""
import sys, json, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from worldcup.tracker import BetTracker

DATA_DIR = Path(__file__).parent / "data"

# Mapeo de mercados legibles a stat_key + direction
MARKET_MAP = {
    'Córners': ('cornerKicks', 'corners'),
    'Tarjetas': ('yellowCards', 'cards'),
    'Tiros Totales': ('totalShotsOnGoal', 'shots'),
    'Tiros Puerta': ('shotsOnGoal', 'shots'),
    'Faltas': ('fouls', 'fouls'),
    'Goles': ('totalGoals', 'goals'),
}

# Mapeo abreviado para formato vbs ("YC U3.5", "CK U8.5", etc.)
VBS_MARKET_MAP = {
    'yc': ('yellowCards', 'cards'),
    'ck': ('cornerKicks', 'corners'),
    'ts': ('totalShotsOnGoal', 'shots'),
    'sg': ('shotsOnGoal', 'shots'),
    'fl': ('fouls', 'fouls'),
    'gl': ('totalGoals', 'goals'),
}

def parse_match_name(name):
    """Normaliza 'Team A_vs_Team B' o 'Team A vs Team B' → ('Team A', 'Team B')"""
    name = name.replace('_vs_', ' vs ').replace(' vs ', ' vs ')
    parts = name.split(' vs ')
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None, None

def normalize_match_key(key):
    """'Brazil vs Japan' → 'brazil vs japan' lowercase"""
    return key.lower().strip()

# Aliases para nombres de equipos (español → inglés)
NAME_ALIASES = {
    'españa': 'spain',
    'bélgica': 'belgium',
    'alemania': 'germany',
    'inglaterra': 'england',
    'francia': 'france',
    'países bajos': 'netherlands',
    'paises bajos': 'netherlands',
    'costa de marfil': "côte d'ivoire",
    'corea del sur': 'south korea',
    'república checa': 'czechia',
    'rep. checa': 'czechia',
    'suiza': 'switzerland',
    'argelia': 'algeria',
    'paraguay': 'paraguay',
    'marruecos': 'morocco',
    'senegal': 'senegal',
    'japón': 'japan',
    'japon': 'japan',
}

def resolve_name(name):
    """Resuelve alias de nombre a inglés estándar."""
    lower = name.lower().strip()
    return NAME_ALIASES.get(lower, name)

def find_real_stats_for_match(home, away, real_stats):
    """Busca stats reales con matching flexible."""
    # Resolver aliases
    h = resolve_name(home)
    a = resolve_name(away)
    
    # Intento directo
    for h_try in [home, h]:
        for a_try in [away, a]:
            key = f"{h_try} vs {a_try}"
            if key in real_stats:
                return real_stats[key]
            # Case-insensitive
            for rk, rv in real_stats.items():
                if rk.startswith('_'):
                    continue
                if normalize_match_key(rk) == normalize_match_key(key):
                    return rv
    
    # Intento inverso
    for h_try in [home, h]:
        for a_try in [away, a]:
            key_rev = f"{a_try} vs {h_try}"
            for rk, rv in real_stats.items():
                if rk.startswith('_'):
                    continue
                if normalize_match_key(rk) == normalize_match_key(key_rev):
                    return rv
    return None

def main():
    tracker = BetTracker()

    # 1. Cargar real stats
    real_path = DATA_DIR / "real_stats.json"
    if not real_path.exists():
        print("No hay real_stats.json")
        return

    with open(real_path) as f:
        real_stats = json.load(f)

    real_matches = {k: v for k, v in real_stats.items() if not k.startswith('_') and not v.get('_blocked')}
    print(f"Partidos con stats reales: {len(real_matches)}")

    # 2. Recopilar TODAS las predicciones de todos los archivos
    # Formato unificado: {match_name: [{market, pick, cuota, prob, edge}]}
    all_predictions = {}

    # Formato 1: all_value_bets*.json (flat list)
    for f in sorted(DATA_DIR.glob("all_value_bets*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
            if isinstance(data, list):
                for entry in data:
                    mname = entry.get('match', '')
                    home, away = parse_match_name(mname)
                    if not home:
                        continue
                    key = f"{home} vs {away}"
                    if key not in all_predictions:
                        all_predictions[key] = {'home': home, 'away': away, 'bets': []}
                    all_predictions[key]['bets'].append({
                        'market': entry.get('market', ''),
                        'pick': entry.get('pick', ''),
                        'cuota': entry.get('cuota'),
                        'prob': entry.get('prob'),
                        'edge': entry.get('edge'),
                    })
        except Exception as e:
            print(f"  Error cargando {f.name}: {e}")

    # Formato 2: vbs_*.json (nested dict OR flat list)
    for f in sorted(DATA_DIR.glob("vbs_*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
            if isinstance(data, list):
                # Flat list format: [{match, market, pick, cuota, prob, edge}]
                for entry in data:
                    mname = entry.get('match', '')
                    home, away = parse_match_name(mname)
                    if not home:
                        continue
                    key = f"{home} vs {away}"
                    if key not in all_predictions:
                        all_predictions[key] = {'home': home, 'away': away, 'bets': []}
                    all_predictions[key]['bets'].append({
                        'market': entry.get('market', ''),
                        'pick': entry.get('pick', ''),
                        'cuota': entry.get('cuota'),
                        'prob': entry.get('prob'),
                        'edge': entry.get('edge'),
                        'src': entry.get('bookie', ''),
                    })
            elif isinstance(data, dict):
                matches_dict = data.get('matches', {})
                for match_key, match_data in matches_dict.items():
                    home, away = parse_match_name(match_key)
                    if not home:
                        continue
                    key = f"{home} vs {away}"
                    if key not in all_predictions:
                        all_predictions[key] = {'home': home, 'away': away, 'bets': []}
                    for vb in match_data.get('value_bets', []):
                        all_predictions[key]['bets'].append({
                            'market': vb.get('market', ''),
                            'pick': vb.get('pick', ''),
                            'cuota': vb.get('cuota'),
                            'prob': vb.get('prob'),
                            'edge': vb.get('edge'),
                            'src': vb.get('src', ''),
                        })
        except Exception as e:
            print(f"  Error cargando {f.name}: {e}")

    # Formato 3: value_bets_analysis*.json
    for f in sorted(DATA_DIR.glob("value_bets_analysis*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                for match_key, match_data in data.items():
                    if match_key.startswith('_'):
                        continue
                    home, away = parse_match_name(match_key)
                    if not home:
                        continue
                    key = f"{home} vs {away}"
                    if key not in all_predictions:
                        all_predictions[key] = {'home': home, 'away': away, 'bets': []}
                    if isinstance(match_data, list):
                        for vb in match_data:
                            all_predictions[key]['bets'].append(vb)
                    elif isinstance(match_data, dict):
                        all_predictions[key]['bets'].append(match_data)
        except Exception as e:
            print(f"  Error cargando {f.name}: {e}")

    print(f"Predicciones encontradas para {len(all_predictions)} partidos")

    # 3. Para cada partido con predicciones Y resultados, registrar en tracker
    imported = 0
    total_bets = 0

    for match_key, pred in all_predictions.items():
        home, away = pred['home'], pred['away']

        # Buscar resultado real
        real = find_real_stats_for_match(home, away, real_stats)
        if not real:
            continue

        bets = pred['bets']
        if not bets:
            continue

        # Convertir apuestas al formato del tracker
        value_bets_for_tracker = []
        for b in bets:
            market_str = b.get('market', '')
            pick = b.get('pick', '')
            cuota = b.get('cuota')
            prob = b.get('prob')
            edge = b.get('edge')

            # Parsear pick: "Under 8.5", "Over 2.5", "U3.5", etc.
            direction = 'over'
            line = 0
            pick_lower = pick.lower().strip()
            if 'under' in pick_lower or pick_lower.startswith('u'):
                direction = 'under'
            elif 'over' in pick_lower or pick_lower.startswith('o'):
                direction = 'over'
            
            # Extraer línea numérica del pick
            nums = re.findall(r'[\d.]+', pick)
            if nums:
                line = float(nums[0])
            else:
                # Intentar del market string (ej: "YC U3.5")
                nums = re.findall(r'[\d.]+', market_str)
                if nums:
                    line = float(nums[0])

            # Mapear market a stat_key
            stat_key = None
            
            # Formato vbs: "YC U3.5", "CK U8.5", etc.
            market_prefix = market_str.split()[0].lower() if market_str else ''
            if market_prefix in VBS_MARKET_MAP:
                stat_key, _ = VBS_MARKET_MAP[market_prefix]
            
            # Formato largo: "Córners", "Tarjetas", etc.
            if not stat_key:
                for mk, (sk, _) in MARKET_MAP.items():
                    if mk.lower() in market_str.lower():
                        stat_key = sk
                        break
            
            if not stat_key:
                # Intentar por nombre directo
                for mk, (sk, _) in MARKET_MAP.items():
                    if market_str.lower().startswith(mk.lower()[:4]):
                        stat_key = sk
                        break

            if not stat_key or not cuota:
                continue

            # Normalizar prob (puede ser 0-1 o 0-100)
            if prob and prob > 1:
                prob = prob / 100.0

            value_bets_for_tracker.append({
                'stat_key': stat_key,
                'line': line,
                'prob_over': prob * 100 if prob else 0,
                'odd': cuota,
                'edge_pct': edge or 0,
                'total_pred': 0,
            })

        if not value_bets_for_tracker:
            continue

        # Registrar predicción
        tracker.log_prediction(
            f"{home} vs {away}", home, away,
            value_bets_for_tracker
        )

        # Registrar resultado
        stats_for_result = {}
        for sk in ['cornerKicks', 'yellowCards', 'totalShotsOnGoal',
                    'shotsOnGoal', 'fouls', 'totalGoals']:
            if sk in real:
                stats_for_result[sk] = real[sk]

        tracker.log_result(f"{home} vs {away}", stats_for_result)
        total_bets += len(value_bets_for_tracker)
        imported += 1

    print(f"Importados {imported} partidos ({total_bets} apuestas) al tracker")

    # 4. Mostrar reporte
    report = tracker.get_report()
    o = report['overall']
    print(f"\n{'='*50}")
    print(f"  REPORTE DEL TRACKER DE APRENDIZAJE")
    print(f"{'='*50}")
    print(f"  Partidos analizados:  {o['total_matches']}")
    print(f"  Apuestas totales:     {o['total_bets']}")
    print(f"  Aciertos:             {o['total_wins']}")
    print(f"  Win rate:             {o['win_rate']}%")
    print(f"  ROI:                  {o['roi']}%")
    print(f"  Profit:               {o['total_profit']} units")

    if report['by_market']:
        print(f"\n  {'MERCADO':<20} {'BETS':>5} {'WR%':>6} {'ROI%':>7} {'PROFIT':>8}")
        print(f"  {'-'*50}")
        for market, stats in sorted(report['by_market'].items(), key=lambda x: x[1]['roi'], reverse=True):
            icon = '✅' if stats['roi'] > 0 else '❌'
            print(f"  {icon} {market:<18} {stats['bets']:>5} {stats['win_rate']:>5.1f}% {stats['roi']:>6.1f}% {stats['total_profit']:>7.2f}")

    # 5. Recalibrar
    if o['total_bets'] >= 10:
        print(f"\n  --- RECALIBRACIÓN ---")
        adj = tracker.recalibrate()
        if adj.get('recommendations'):
            for rec in adj['recommendations']:
                arrow = '⬆️' if rec['action'] == 'increase_weight' else '⬇️'
                print(f"  {arrow} {rec['market']}: {rec['reason']}")
        else:
            print("  Sin recomendaciones aún")

    print(f"\n  Datos guardados en: data/learning/")

if __name__ == '__main__':
    main()
