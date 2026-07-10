"""
Bridge entre vbs_bug_fixed.json y BetTracker.

Convierte nuestro formato de value bets (market/pick/cuota/prob/edge)
al formato que espera BetTracker (stat_key/line/direction/prob_over/odd).
"""
import json
import re
from pathlib import Path

# Mapeo de nuestros picks a stat_key + direction + line del tracker
PICK_TO_STAT = {
    # Corners
    'Corners Menos de': {'stat_key': 'cornerKicks', 'direction': 'under'},
    'Corners Más de': {'stat_key': 'cornerKicks', 'direction': 'over'},
    # Tarjetas
    'Tarjetas Menos de': {'stat_key': 'yellowCards', 'direction': 'under'},
    'Tarjetas Más de': {'stat_key': 'yellowCards', 'direction': 'over'},
    # Goles
    'Goles Más de': {'stat_key': 'totalGoals', 'direction': 'over'},
    'Goles Menos de': {'stat_key': 'totalGoals', 'direction': 'under'},
    # Tiros
    'Tiros Más de': {'stat_key': 'totalShotsOnGoal', 'direction': 'over'},
    'Tiros Menos de': {'stat_key': 'totalShotsOnGoal', 'direction': 'under'},
    # Faltas
    'Faltas Más de': {'stat_key': 'fouls', 'direction': 'over'},
    'Faltas Menos de': {'stat_key': 'fouls', 'direction': 'under'},
}

# Mercados que NO son stat-based (1X2, BTTS) — se trackean por separado
NON_STAT_MARKETS = {'1X2', 'BTTS'}


def _extract_line(pick_str):
    """Extrae la línea numérica de un pick. Ej: 'Corners Menos de 9.5' → 9.5"""
    match = re.search(r'(\d+\.?\d*)', pick_str)
    return float(match.group(1)) if match else 0


def vbs_to_tracker_format(vbs_bets):
    """Convierte lista de value bets del formato vbs al formato tracker.
    
    Returns:
        stat_bets: lista de bets stat-based para log_prediction()
        non_stat_bets: lista de bets 1X2/BTTS para tracking manual
    """
    stat_bets = []
    non_stat_bets = []
    
    for vb in vbs_bets:
        pick = vb.get('pick', '')
        market = vb.get('market', '')
        cuota = vb.get('cuota', 0)
        prob = vb.get('prob', 0) / 100.0  # tracker usa 0-1
        edge = vb.get('edge', 0)
        
        # Buscar match en PICK_TO_STAT
        matched = False
        for prefix, info in PICK_TO_STAT.items():
            if pick.startswith(prefix):
                line = _extract_line(pick)
                stat_bets.append({
                    'stat_key': info['stat_key'],
                    'line': line,
                    'direction': info['direction'],
                    'prob_over': prob * 100,  # tracker espera 0-100
                    'odd': cuota,
                    'edge_pct': edge,
                    'total_pred': line,  # línea predicha
                })
                matched = True
                break
        
        if not matched:
            # 1X2, BTTS u otro mercado no-stat
            non_stat_bets.append({
                'market': market,
                'pick': pick,
                'cuota': cuota,
                'prob': prob,
                'edge': edge,
            })
    
    return stat_bets, non_stat_bets


def log_vbs_predictions(tracker, match_name, home_team, away_team, vbs_path, match_date=None):
    """Lee vbs_bug_fixed.json y registra predicciones en el tracker.
    
    Returns:
        (stat_count, non_stat_count, combis_count)
    """
    with open(vbs_path) as f:
        vbs = json.load(f)
    
    match_key = f"{home_team}_vs_{away_team}"
    match_data = vbs.get('matches', {}).get(match_key, {})
    
    if not match_data:
        # Buscar por nombre flexible
        for mk, md in vbs.get('matches', {}).items():
            parts = mk.lower().split('_vs_')
            if len(parts) == 2:
                h, a = parts
                if (home_team.lower().startswith(h) or h.startswith(home_team.lower())) and \
                   (away_team.lower().startswith(a) or a.startswith(away_team.lower())):
                    match_data = md
                    break
    
    vbs_bets = match_data.get('value_bets', [])
    combis = match_data.get('combinadas', [])
    
    stat_bets, non_stat_bets = vbs_to_tracker_format(vbs_bets)
    
    # Log stat-based bets via tracker
    stat_count = 0
    if stat_bets:
        stat_count = tracker.log_prediction(
            match_name, home_team, away_team, stat_bets, match_date
        )
    
    return stat_count, len(non_stat_bets), len(combis)


def log_vbs_result(tracker, match_name, sportdb_stats, home_score=None, away_score=None, home_team=None, away_team=None):
    """Registra resultado real y evalúa apuestas.
    
    sportdb_stats: dict del API sportdb {statName: {homeValue, awayValue, total}}
    """
    # Convertir formato sportdb → formato tracker
    real_stats = {}
    
    # Mapeo de nombres sportdb → stat_keys del tracker
    STAT_NAME_MAP = {
        'Corner kicks': 'cornerKicks',
        'Yellow cards': 'yellowCards',
        'Red cards': 'redCards',
        'Total shots': 'totalShotsOnGoal',
        'Shots on target': 'shotsOnGoal',
        'Fouls': 'fouls',
        'Expected goals (xG)': 'totalGoals',
    }
    
    for period in sportdb_stats:
        if period.get('period') != 'Match':
            continue
        for s in period.get('stats', []):
            name = s.get('statName', '')
            stat_key = STAT_NAME_MAP.get(name)
            if stat_key:
                def parse_val(v):
                    if v is None:
                        return None
                    v = str(v).replace('%', '').strip()
                    # Handle "89% (432/486)" format
                    if '(' in v:
                        v = v.split('(')[0].replace('%', '').strip()
                    try:
                        return float(v)
                    except:
                        return None
                
                home_val = parse_val(s.get('homeValue'))
                away_val = parse_val(s.get('awayValue'))
                total = None
                if home_val is not None and away_val is not None:
                    total = home_val + away_val
                
                real_stats[stat_key] = {
                    'home': home_val,
                    'away': away_val,
                    'total': total,
                }
    
    evaluated = tracker.log_result(match_name, real_stats, home_score, away_score)
    
    # Evaluar apuestas 1X2 y BTTS del bridge
    non_stat_evaluated = 0
    non_stat_results = []
    
    if home_score is not None and away_score is not None:
        # Encontrar predicción con non_stat_bets
        for p in reversed(tracker.predictions):
            if p['match'].lower() == match_name.lower():
                ns_bets = p.get('non_stat_bets', [])
                for b in ns_bets:
                    pick = b.get('pick', '')
                    cuota = b.get('cuota', 0)
                    won = False
                    
                    if 'gana' in pick.lower():
                        team = pick.split(' gana')[0].strip().lower()
                        if team == home_team.lower() and home_score > away_score:
                            won = True
                        elif team == away_team.lower() and away_score > home_score:
                            won = True
                    elif 'empate' in pick.lower():
                        won = (home_score == away_score)
                    elif 'ambos' in pick.lower() and 'marcan' in pick.lower():
                        both_scored = home_score > 0 and away_score > 0
                        if 'no' in pick.lower():
                            won = not both_scored
                        else:
                            won = both_scored
                    
                    stake = 1.0
                    payout = stake * cuota if won else 0
                    profit = round(payout - stake, 2) if won else -stake
                    
                    non_stat_results.append({
                        'market': b['market'],
                        'pick': pick,
                        'cuota': cuota,
                        'prob': b['prob'],
                        'edge': b['edge'],
                        'won': won,
                        'profit': profit,
                    })
                    non_stat_evaluated += 1
                break
    
    return evaluated, real_stats, non_stat_results
