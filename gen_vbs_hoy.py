#!/usr/bin/env python3
"""
gen_vbs_hoy.py — Value bets de España-Francia (14 jul) con CONTRASTE HONESTO.

NO presenta las value bets como "apuestas seguras". Calcula el edge del modelo
vs cuota, pero marca fiabilidad:
  - Si el modelo discrepa >10% del mercado en 1X2 -> advertencia de que el
    modelo no tiene fiabilidad suficiente (muestra minúscula: 2-3 partidos).
  - Las value bets de goles/BTTS se marcan como "baja fiabilidad" cuando el xG
    del modelo depende del piso defensivo artificial (equipo con GA~0).

El JSON resultante alimenta worldcup_web.py (pestaña Value Bets), que ahora
muestra una advertencia de fiabilidad.
"""
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

# ─── Predicción del modelo ────────────────────────────────
pred = engine.predict_match('Spain', 'France')  # home=Spain, away=France
if 'error' in pred:
    print('ERROR', pred['error']); sys.exit(1)

xg_h = pred['expected_goals']['home']   # Spain
xg_a = pred['expected_goals']['away']   # France
total_xg = xg_h + xg_a
prob = pred['probabilities']
ts_h = pred['team_stats']['home']
ts_a = pred['team_stats']['away']

# ─── Cuotas (caché: home=France, away=Spain) ──────────────
odds = cache[FID]['odds']
bet365 = odds['bet365']
pin = odds.get('pinnacle', {})
b365_1x2 = {
    'home': bet365['1x2']['away'],   # Spain
    'draw': bet365['1x2']['draw'],
    'away': bet365['1x2']['home'],   # France
}

# ─── CONTRASTE MODELO vs MERCADO (honesto) ────────────────
# Mercado = bet365 (implícito). Si el modelo discrepa >10pp del mercado en 1X2,
# el modelo NO es fiable para ese partido (muestra de 2-3 partidos).
market_impl = {s: implied_prob(b365_1x2[s]) for s in ('home', 'draw', 'away')}
model_1x2 = {'home': prob['home']/100, 'draw': prob['draw']/100, 'away': prob['away']/100}
max_divergence = max(abs(model_1x2[s] - market_impl[s]) for s in model_1x2) * 100
model_reliable = max_divergence <= 10.0   # sólo fiable si discrepa <=10pp

# ¿El xG depende del piso defensivo artificial? (equipo con GA~0 en muestra)
ga_floor_used = (ts_h['avg_goals_against'] < 0.1) or (ts_a['avg_goals_against'] < 0.1)

print(f"Discrepancia modelo vs mercado (1X2): {max_divergence:+.1f}pp -> "
      f"{'FIABLE' if model_reliable else 'NO FIABLE (muestra 2-3 partidos)'}")
print(f"xG depende de piso defensivo artificial: {ga_floor_used}")

vbs = []

# 1X2 — siempre mostramos el edge, pero marcamos fiabilidad
for side, p, o in [
    ('España', prob['home']/100, b365_1x2['home']),
    ('Empate', prob['draw']/100, b365_1x2['draw']),
    ('Francia', prob['away']/100, b365_1x2['away']),
]:
    e = edge(p, o)
    vbs.append({
        'market': '1X2', 'pick': side, 'cuota': round(o, 2),
        'prob': round(p*100, 1), 'edge': round(e, 1), 'src': 'bet365',
        'reliable': model_reliable,
    })

# Goles / BTTS — fiabilidad baja si el xG usa piso artificial
goals_reliable = not ga_floor_used
for line in [1.5, 2.5, 3.5]:
    over_p = poisson_over(total_xg, line)
    under_p = poisson_under(total_xg, line)
    ok = f'over_{str(line).replace(".", "")}'
    uk = f'under_{str(line).replace(".", "")}'
    if ok in bet365:
        e = edge(over_p, bet365[ok])
        vbs.append({'market': 'Goles', 'pick': f'Over {line}', 'cuota': round(bet365[ok], 2),
                    'prob': round(over_p*100, 1), 'edge': round(e, 1), 'src': 'bet365',
                    'reliable': goals_reliable})
    if uk in bet365:
        e = edge(under_p, bet365[uk])
        vbs.append({'market': 'Goles', 'pick': f'Under {line}', 'cuota': round(bet365[uk], 2),
                    'prob': round(under_p*100, 1), 'edge': round(e, 1), 'src': 'bet365',
                    'reliable': goals_reliable})

btts_p = poisson_btts(xg_h, xg_a)
for side, key in [('Sí', 'btts_yes'), ('No', 'btts_no')]:
    p = btts_p if side == 'Sí' else 1 - btts_p
    e = edge(p, bet365[key])
    vbs.append({'market': 'BTTS', 'pick': f'BTTS {side}', 'cuota': round(bet365[key], 2),
                'prob': round(p*100, 1), 'edge': round(e, 1), 'src': 'bet365',
                'reliable': goals_reliable})

# Córners / Tarjetas — sin piso artificial, pero el track record está vacío
# => fiabilidad "media" (modelo Poisson de stats, sin validación histórica)
ck_total = ts_h['avg_stats_raw']['cornerKicks'] + ts_a['avg_stats_raw']['cornerKicks']
yc_total = ts_h['avg_stats_raw']['yellowCards'] + ts_a['avg_stats_raw']['yellowCards']
for src, src_name in [(bet365, 'bet365'), (pin, 'pinnacle')]:
    for stat_key, total, label in [('cornerKicks', ck_total, 'Córners'), ('yellowCards', yc_total, 'Tarjetas')]:
        for key, val in src.get(stat_key, {}).items():
            if not key.startswith(('over_', 'under_')):
                continue
            try:
                line = float(key.split('_')[1])
            except ValueError:
                continue
            side = 'over' if key.startswith('over') else 'under'
            model_p = poisson_over(total, line) if side == 'over' else poisson_under(total, line)
            e = edge(model_p, val)
            if e > 2:
                lab = f"{'O' if side == 'over' else 'U'}{line}"
                vbs.append({'market': label, 'pick': lab, 'cuota': round(val, 2),
                            'prob': round(model_p*100, 1), 'edge': round(e, 1), 'src': src_name,
                            'reliable': False})  # sin track record validado

vbs.sort(key=lambda x: x['edge'], reverse=True)

output = {
    'date': '2026-07-14',
    'model_reliable': model_reliable,
    'max_divergence_pp': round(max_divergence, 1),
    'ga_floor_used': ga_floor_used,
    'matches': {
        'Spain_vs_France': {'vbs': vbs}
    }
}
with open('data/vbs_bug_fixed.json', 'w') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

reliable_n = sum(1 for v in vbs if v['reliable'])
print(f"✅ {len(vbs)} value bets (reliable={reliable_n}, low-fi={len(vbs)-reliable_n}) -> data/vbs_bug_fixed.json")
