#!/usr/bin/env python3
"""
analisis_hoy.py — Analisis de los partidos de HOY (11 julio 2026) usando el
motor (all_matches.json) + cuotas REALES de OddsPapi (odds_cache.json).

Partidos:
  - Norway vs England      (fixture id1000001653452529)
  - Argentina vs Switzerland (fixture id1000001653452531)

Reutiliza la logica de collect_value_bets de analysis_6julio_v4.py (mismo
patron "como siempre"). NO arma combinadas: solo analiza y muestra.
"""
import json, math, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from src.worldcup.engine import WorldCupEngine

engine = WorldCupEngine()
engine.load_data()

cache = json.load(open('data/odds_cache.json'))

TODAY = [
    ('Norway', 'England', 'id1000001653452529'),
    ('Argentina', 'Switzerland', 'id1000001653452531'),
]

# ─── Helpers Poisson (de analysis_6julio_v4.py) ─────────────
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

def collect_value_bets(pred, odds_cache_id):
    xg_h = pred['expected_goals']['home']
    xg_a = pred['expected_goals']['away']
    total_xg = xg_h + xg_a
    prob = pred['probabilities']
    ts_h = pred['team_stats']['home']
    ts_a = pred['team_stats']['away']

    odds = cache[odds_cache_id]['odds']
    bet365 = odds['bet365']
    pin = odds.get('pinnacle', {})

    vbs = []

    # 1X2 (bet365)
    for side, p, o in [
        (pred['home_team'], prob['home']/100, bet365['1x2']['home']),
        ('Empate', prob['draw']/100, bet365['1x2']['draw']),
        (pred['away_team'], prob['away']/100, bet365['1x2']['away']),
    ]:
        e = edge(p, o)
        if e > 0:
            vbs.append({'market': '1X2', 'pick': side, 'cuota': o, 'prob': p*100, 'edge': e, 'src': 'bet365'})

    # Goles (bet365)
    for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
        over_p = poisson_over(total_xg, line)
        under_p = poisson_under(total_xg, line)
        ok = f'over_{str(line).replace(".","")}'
        uk = f'under_{str(line).replace(".","")}'
        if ok in bet365:
            e = edge(over_p, bet365[ok])
            if e > 0:
                vbs.append({'market': f'Goles O{line}', 'pick': f'Over {line}', 'cuota': bet365[ok], 'prob': over_p*100, 'edge': e, 'src': 'bet365'})
        if uk in bet365:
            e = edge(under_p, bet365[uk])
            if e > 0:
                vbs.append({'market': f'Goles U{line}', 'pick': f'Under {line}', 'cuota': bet365[uk], 'prob': under_p*100, 'edge': e, 'src': 'bet365'})

    # BTTS (bet365)
    btts_p = poisson_btts(xg_h, xg_a)
    for side, key in [('Sí', 'btts_yes'), ('No', 'btts_no')]:
        p = btts_p if side == 'Sí' else 1 - btts_p
        e = edge(p, bet365[key])
        if e > 0:
            vbs.append({'market': 'BTTS', 'pick': f'BTTS {side}', 'cuota': bet365[key], 'prob': p*100, 'edge': e, 'src': 'bet365'})

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
                label = f"{'O' if side == 'over' else 'U'}{line}"
                vbs.append({'market': f'CK {label}', 'pick': label, 'cuota': val, 'prob': model_p*100, 'edge': e, 'src': src_name})

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
                label = f"{'O' if side == 'over' else 'U'}{line}"
                vbs.append({'market': f'YC {label}', 'pick': label, 'cuota': val, 'prob': model_p*100, 'edge': e, 'src': src_name})

    vbs.sort(key=lambda x: x['edge'], reverse=True)
    return vbs


def main():
    results = {}
    for home, away, fid in TODAY:
        print(f"\n{'='*64}\n  ANALISIS: {home} vs {away}  (fixture {fid})\n{'='*64}")
        if fid not in cache or not cache[fid].get('odds'):
            print("  [skip] sin cuotas en odds_cache")
            continue
        pred = engine.predict_match(home, away)
        if 'error' in pred:
            print("  [skip]", pred['error'])
            continue
        prob = pred['probabilities']
        xg_h = pred['expected_goals']['home']
        xg_a = pred['expected_goals']['away']
        ts_h = pred['team_stats']['home']
        ts_a = pred['team_stats']['away']

        print(f"  Motor H/D/A: {prob['home']:.1f}% / {prob['draw']:.1f}% / {prob['away']:.1f}%")
        print(f"  xG: {home} {xg_h:.2f} - {xg_a:.2f} {away}  (total {xg_h+xg_a:.2f})")
        print(f"  Prediccion: {pred['prediction']} ({pred['confidence']})")
        print(f"  Narrativa: {pred['narrative']}")
        print(f"  {home}: {ts_h['games']}P {ts_h['wins']}W {ts_h['draws']}D {ts_h['losses']}L | GF {ts_h['avg_goals_for']:.1f} GA {ts_h['avg_goals_against']:.1f} | CK {ts_h['avg_stats_raw']['cornerKicks']:.1f} YC {ts_h['avg_stats_raw']['yellowCards']:.1f}")
        print(f"  {away}: {ts_a['games']}P {ts_a['wins']}W {ts_a['draws']}D {ts_a['losses']}L | GF {ts_a['avg_goals_for']:.1f} GA {ts_a['avg_goals_against']:.1f} | CK {ts_a['avg_stats_raw']['cornerKicks']:.1f} YC {ts_a['avg_stats_raw']['yellowCards']:.1f}")

        vb = collect_value_bets(pred, fid)
        print(f"\n  🎯 VALUE BETS ({len(vb)}):")
        for v in vb:
            icon = '🟢' if v['edge'] > 15 else '🟡' if v['edge'] > 5 else '🔵'
            print(f"    {icon} {v['market']:12s} {v['pick']:14s} @ {v['cuota']:.2f}  Prob {v['prob']:.1f}%  Edge +{v['edge']:.1f}%  ({v['src']})")

        results[f"{home}_vs_{away}"] = {
            'fixture': fid,
            'probabilities': prob,
            'expected_goals': {'home': xg_h, 'away': xg_a},
            'prediction': pred['prediction'],
            'confidence': pred['confidence'],
            'narrative': pred['narrative'],
            'value_bets': vb,
        }

    out = {'date': '2026-07-11', 'matches': results}
    with open('data/hoy_analysis.json', 'w') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Guardado: data/hoy_analysis.json  ({len(results)} partidos analizados)")


if __name__ == '__main__':
    main()
