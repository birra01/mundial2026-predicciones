#!/usr/bin/env python3
"""Genera data/vbs_bug_fixed.json para España-Francia (14 jul) usando la lógica
de analisis_hoy.py. Lo consume worldcup_web.py (pestaña Value Bets)."""
import json, math, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from src.worldcup.engine import WorldCupEngine

engine = WorldCupEngine()
engine.load_data()
cache = json.load(open('data/odds_cache.json'))

FID = 'id1000001653452533'

def poisson_pmf(k, lam):
    return (lam**k) * math.exp(-lam) / math.factorial(k)
def poisson_over(lam, line):
    k = int(line) + 1 if line == int(line) else int(math.ceil(line))
    return 1 - sum(poisson_pmf(i, lam) for i in range(k))
def poisson_under(lam, line):
    return 1 - poisson_over(lam, line)
def poisson_btts(lam_h, lam_a):
    p0_h = poisson_pmf(0, lam_h)
    p0_a = poisson_pmf(0, lam_a)
    return 1 - p0_h - p0_a + p0_h * p0_a
def implied_prob(odds):
    return 1 / odds if odds > 0 else 0
def edge(model_prob, odds):
    return (model_prob - implied_prob(odds)) * 100

pred = engine.predict_match('Spain', 'France')  # motor: home=Spain, away=France
if 'error' in pred:
    print('ERROR', pred['error']); sys.exit(1)

xg_h = pred['expected_goals']['home']   # Spain
xg_a = pred['expected_goals']['away']   # France
total_xg = xg_h + xg_a
prob = pred['probabilities']
ts_h = pred['team_stats']['home']
ts_a = pred['team_stats']['away']

# En el caché el fixture es France(home) vs Spain(away); bet365['1x2'] usa esas claves
odds = cache[FID]['odds']
bet365 = odds['bet365']
pin = odds.get('pinnacle', {})

# Mapear 1X2 del caché (home=France, away=Spain) a nuestro frame (home=Spain, away=France)
b365_1x2 = {
    'home': bet365['1x2']['away'],   # Spain
    'draw': bet365['1x2']['draw'],
    'away': bet365['1x2']['home'],   # France
}

vbs = []
# 1X2
for side, p, o in [
    ('España', prob['home']/100, b365_1x2['home']),
    ('Empate', prob['draw']/100, b365_1x2['draw']),
    ('Francia', prob['away']/100, b365_1x2['away']),
]:
    e = edge(p, o)
    if e > 0:
        vbs.append({'market': '1X2', 'pick': side, 'cuota': round(o,2), 'prob': round(p*100,1), 'edge': round(e,1), 'src': 'bet365'})

# Goles
for line in [1.5, 2.5, 3.5]:
    over_p = poisson_over(total_xg, line)
    under_p = poisson_under(total_xg, line)
    ok = f'over_{str(line).replace(".","")}'
    uk = f'under_{str(line).replace(".","")}'
    if ok in bet365:
        e = edge(over_p, bet365[ok])
        if e > 0:
            vbs.append({'market': 'Goles', 'pick': f'Over {line}', 'cuota': round(bet365[ok],2), 'prob': round(over_p*100,1), 'edge': round(e,1), 'src': 'bet365'})
    if uk in bet365:
        e = edge(under_p, bet365[uk])
        if e > 0:
            vbs.append({'market': 'Goles', 'pick': f'Under {line}', 'cuota': round(bet365[uk],2), 'prob': round(under_p*100,1), 'edge': round(e,1), 'src': 'bet365'})

# BTTS
btts_p = poisson_btts(xg_h, xg_a)
for side, key in [('Sí', 'btts_yes'), ('No', 'btts_no')]:
    p = btts_p if side == 'Sí' else 1 - btts_p
    e = edge(p, bet365[key])
    if e > 0:
        vbs.append({'market': 'BTTS', 'pick': f'BTTS {side}', 'cuota': round(bet365[key],2), 'prob': round(p*100,1), 'edge': round(e,1), 'src': 'bet365'})

# Córners (bet365 + pinnacle)
ck_total = ts_h['avg_stats_raw']['cornerKicks'] + ts_a['avg_stats_raw']['cornerKicks']
for src, src_name in [(bet365, 'bet365'), (pin, 'pinnacle')]:
    ck = src.get('cornerKicks', {})
    for key, val in ck.items():
        if not key.startswith(('over_', 'under_')):
            continue
        try:
            line = float(key.split('_')[1])
        except ValueError:
            continue
        side = 'over' if key.startswith('over') else 'under'
        model_p = poisson_over(ck_total, line) if side == 'over' else poisson_under(ck_total, line)
        e = edge(model_p, val)
        if e > 2:
            label = f"{'O' if side=='over' else 'U'}{line}"
            vbs.append({'market': 'Córners', 'pick': label, 'cuota': round(val,2), 'prob': round(model_p*100,1), 'edge': round(e,1), 'src': src_name})

# Tarjetas (bet365 + pinnacle)
yc_total = ts_h['avg_stats_raw']['yellowCards'] + ts_a['avg_stats_raw']['yellowCards']
for src, src_name in [(bet365, 'bet365'), (pin, 'pinnacle')]:
    yc = src.get('yellowCards', {})
    for key, val in yc.items():
        if not key.startswith(('over_', 'under_')):
            continue
        try:
            line = float(key.split('_')[1])
        except ValueError:
            continue
        side = 'over' if key.startswith('over') else 'under'
        model_p = poisson_over(yc_total, line) if side == 'over' else poisson_under(yc_total, line)
        e = edge(model_p, val)
        if e > 2:
            label = f"{'O' if side=='over' else 'U'}{line}"
            vbs.append({'market': 'Tarjetas', 'pick': label, 'cuota': round(val,2), 'prob': round(model_p*100,1), 'edge': round(e,1), 'src': src_name})

vbs.sort(key=lambda x: x['edge'], reverse=True)

output = {
    'date': '2026-07-14',
    'matches': {
        'Spain_vs_France': {
            'vbs': vbs,
        }
    }
}
with open('data/vbs_bug_fixed.json', 'w') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"✅ {len(vbs)} value bets guardadas en data/vbs_bug_fixed.json")
for v in vbs:
    print(f"  {v['market']:8s} {v['pick']:10s} @ {v['cuota']:.2f}  Prob {v['prob']:.1f}%  Edge +{v['edge']:.1f}%  ({v['src']})")
