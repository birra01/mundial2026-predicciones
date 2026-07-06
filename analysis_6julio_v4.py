#!/usr/bin/env python3
"""
Análisis completo 6 julio v4 — Portugal vs España + USA vs Bélgica
Usa: WorldCupEngine + OddsPapi (bet365/pinnacle corners/cards) + sportdb (venue/referee)
Genera: value bets + combinadas creativas (1 a 4 picks por combinada, SINGLE = 1 pick)
"""
import json, math, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from src.worldcup.engine import WorldCupEngine

engine = WorldCupEngine()
engine.load_data()

cache = json.load(open('data/odds_cache.json'))
sportdb_pt = json.load(open('data/sportdb_Portugal_vs_Spain.json'))
sportdb_us = json.load(open('data/sportdb_USA_vs_Belgium.json'))

pred_pt = engine.predict_match('Portugal', 'Spain')
pred_us = engine.predict_match('USA', 'Belgium')

# ─── HELPERS ─────────────────────────────────────────────
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

def parse_line(key):
    """Parse 'over_10.5' → ('over', 10.5), 'under_9.5' → ('under', 9.5)"""
    parts = key.split('_')
    if len(parts) != 2: return None, None
    try: return parts[0], float(parts[1])
    except: return None, None

def collect_value_bets(pred, odds_cache_id):
    """Collect all value bets for a match across all markets"""
    xg_h = pred['expected_goals']['home']
    xg_a = pred['expected_goals']['away']
    total_xg = xg_h + xg_a
    prob = pred['probabilities']
    ts_h = pred['team_stats']['home']
    ts_a = pred['team_stats']['away']
    
    odds = cache[odds_cache_id]['odds']
    bet365 = odds['bet365']
    pin = odds['pinnacle']
    
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
            side, line = parse_line(key)
            if side is None: continue
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
            side, line = parse_line(key)
            if side is None: continue
            model_p = poisson_over(yc_total, line) if side == 'over' else poisson_under(yc_total, line)
            e = edge(model_p, val)
            if e > 2:
                label = f"{'O' if side == 'over' else 'U'}{line}"
                vbs.append({'market': f'YC {label}', 'pick': label, 'cuota': val, 'prob': model_p*100, 'edge': e, 'src': src_name})
    
    vbs.sort(key=lambda x: x['edge'], reverse=True)
    return vbs

def build_combinadas(vbs, pred):
    """Build combinadas con lógica correcta: SEGURA(~2-3), MEDIA(~4-8), SOÑADORA(~8-15), VOLÁTIL(max edge)."""
    combinadas = []

    # Label mapping — pick legible
    def lbl(v):
        mkt = v['market']
        pick = v['pick']
        if mkt == '1X2':
            return f"Gana {pick}"
        if mkt == 'BTTS':
            return pick  # "BTTS Sí" / "BTTS No"
        if mkt.startswith('Goles'):
            return f"Goles {pick}"  # "Goles Menos de 2.5" / "Goles Más de 2.5"
        if mkt.startswith('CK'):
            side = 'Más de' if pick.startswith('O') else 'Menos de'
            line = pick[1:]
            return f"Córners {side} {line}"
        if mkt.startswith('YC'):
            side = 'Más de' if pick.startswith('O') else 'Menos de'
            line = pick[1:]
            return f"Tarjetas {side} {line}"
        return f"{mkt} {pick}"

    # Categorize picks by market type
    result_picks = [v for v in vbs if v['market'] in ['1X2', 'BTTS'] or v['market'].startswith('Goles')]
    ck_picks = [v for v in vbs if v['market'].startswith('CK')]
    yc_picks = [v for v in vbs if v['market'].startswith('YC')]

    def comb_cuota(picks):
        c = 1.0
        for p in picks: c *= p['cuota']
        return round(c, 2)

    def comb_prob(picks):
        p = 1.0
        for pick in picks: p *= pick['prob'] / 100.0
        return round(p * 100, 1)

    # ─── SEGURA: cuota ~2-3, probabilidad combinada máxima ───
    # Excluir picks triviales (cuota < 1.25 o prob > 92%) que inflan prob sin aportar
    meaningful = [v for v in vbs if v['cuota'] >= 1.25 and v['prob'] < 92]
    safe_pool = [v for v in meaningful if v['prob'] > 50]
    best_segura = None
    best_segura_prob = 0
    for i, a in enumerate(safe_pool):
        for b in safe_pool[i+1:]:
            if a['market'][:2] == b['market'][:2]:
                continue  # mercados distintos
            c = a['cuota'] * b['cuota']
            if 1.8 <= c <= 4.5:
                p = (a['prob'] / 100) * (b['prob'] / 100) * 100
                if p > best_segura_prob:
                    best_segura_prob = p
                    best_segura = [a, b]
    # Si no hay par bueno, usar 1 pick de mayor prob con cuota 1.5-3.5
    if not best_segura:
        singles = [v for v in meaningful if 1.5 <= v['cuota'] <= 3.5 and v['prob'] > 60]
        if singles:
            best_segura = [max(singles, key=lambda x: x['prob'])]

    if best_segura:
        combinadas.append({
            'name': '🛡️ SEGURA',
            'picks': [{'pick': lbl(p), 'cuota': p['cuota'], 'prob': p['prob']} for p in best_segura],
            'cuota': comb_cuota(best_segura),
            'desc': f"{len(best_segura)} picks · Prob combinada {comb_prob(best_segura)}% · Máxima fiabilidad",
            'n_picks': len(best_segura)
        })

    # ─── MEDIA: cuota ~4-8, mercados mixtos ───
    media_pool = [v for v in meaningful if v['prob'] > 40]
    best_media = None
    best_media_score = 0
    for i, a in enumerate(media_pool):
        for b in media_pool[i+1:]:
            if a['market'][:2] == b['market'][:2]:
                continue
            c = a['cuota'] * b['cuota']
            if 3.5 <= c <= 10:
                # Score = edge total × prob combinada
                score = (a['edge'] + b['edge']) * ((a['prob']/100) * (b['prob']/100))
                if score > best_media_score:
                    best_media_score = score
                    best_media = [a, b]

    if best_media:
        combinadas.append({
            'name': '⚡ MEDIA',
            'picks': [{'pick': lbl(p), 'cuota': p['cuota'], 'prob': p['prob']} for p in best_media],
            'cuota': comb_cuota(best_media),
            'desc': f"{len(best_media)} picks · Mercados mixtos · Prob {comb_prob(best_media)}%",
            'n_picks': len(best_media)
        })

    # ─── SOÑADORA: cuota ~8-20, 3 picks de mercados distintos ───
    sona_pool = sorted(vbs, key=lambda x: x['edge'], reverse=True)
    sonadora = []
    seen_mkt = set()
    for v in sona_pool:
        mkt_type = v['market'][:2]
        if mkt_type not in seen_mkt:
            sonadora.append(v)
            seen_mkt.add(mkt_type)
        if len(sonadora) >= 3:
            break
    if len(sonadora) < 3:
        for v in sona_pool:
            if v not in sonadora:
                sonadora.append(v)
            if len(sonadora) >= 3:
                break

    if len(sonadora) >= 3:
        combinadas.append({
            'name': '🌙 SOÑADORA',
            'picks': [{'pick': lbl(p), 'cuota': p['cuota'], 'prob': p['prob']} for p in sonadora[:3]],
            'cuota': comb_cuota(sonadora[:3]),
            'desc': f"3 mercados distintos · Prob {comb_prob(sonadora[:3])}% · Cuota alta",
            'n_picks': 3
        })

    # ─── VOLÁTIL: máximo edge total, picks de mercados distintos ───
    volatil_sorted = sorted(vbs, key=lambda x: x['edge'], reverse=True)
    volatil = []
    seen_v = set()
    for v in volatil_sorted:
        mkt_type = v['market'][:2]
        if mkt_type not in seen_v:
            volatil.append(v)
            seen_v.add(mkt_type)
        if len(volatil) >= 4:
            break
    # Si no hay4 tipos, rellenar con los que queden de mayor edge
    for v in volatil_sorted:
        if v not in volatil:
            volatil.append(v)
        if len(volatil) >= 4:
            break
    if len(volatil) >= 2:
        total_edge = sum(v['edge'] for v in volatil)
        combinadas.append({
            'name': '🔥 VOLÁTIL',
            'picks': [{'pick': lbl(p), 'cuota': p['cuota'], 'prob': p['prob']} for p in volatil],
            'cuota': comb_cuota(volatil),
            'desc': f"Max edge total (+{total_edge:.0f}%) · {len(volatil)} picks · Alta varianza",
            'n_picks': len(volatil)
        })

    return combinadas

# ─── RUN ─────────────────────────────────────────────────
print("=" * 60)
print("🇵🇹🇪🇸 PORTUGAL vs ESPAÑA — 19:00")
print("=" * 60)

det_pt = sportdb_pt.get('details', {})
print(f"📍 {det_pt.get('venue','?')} ({det_pt.get('venueCity','?')}), cap. {det_pt.get('capacity','?')}")
print(f"👨‍⚖️ Árbitro: {det_pt.get('referee','?')}")

prob = pred_pt['probabilities']
xg_h = pred_pt['expected_goals']['home']
xg_a = pred_pt['expected_goals']['away']
ts_h = pred_pt['team_stats']['home']
ts_a = pred_pt['team_stats']['away']

print(f"\n📊 Motor: H={prob['home']:.1f}% D={prob['draw']:.1f}% A={prob['away']:.1f}%")
print(f"⚽ xG: {xg_h:.2f} - {xg_a:.2f} (total {xg_h+xg_a:.2f})")
print(f"📈 Portugal: {ts_h['games']}P {ts_h['wins']}W {ts_h['draws']}D {ts_h['losses']}L — GF {ts_h['avg_goals_for']:.1f} GA {ts_h['avg_goals_against']:.1f}")
print(f"   CK {ts_h['avg_stats_raw']['cornerKicks']:.1f} YC {ts_h['avg_stats_raw']['yellowCards']:.1f} Fouls {ts_h['avg_stats_raw']['fouls']:.1f}")
print(f"📈 España:   {ts_a['games']}P {ts_a['wins']}W {ts_a['draws']}D {ts_a['losses']}L — GF {ts_a['avg_goals_for']:.1f} GA {ts_a['avg_goals_against']:.1f}")
print(f"   CK {ts_a['avg_stats_raw']['cornerKicks']:.1f} YC {ts_a['avg_stats_raw']['yellowCards']:.1f} Fouls {ts_a['avg_stats_raw']['fouls']:.1f}")

vb_pt = collect_value_bets(pred_pt, 'id1000001653452513')
comb_pt = build_combinadas(vb_pt, pred_pt)

print(f"\n{'─'*60}")
print(f"🎯 VALUE BETS ({len(vb_pt)})")
print(f"{'─'*60}")
for vb in vb_pt:
    icon = '🟢' if vb['edge'] > 15 else '🟡' if vb['edge'] > 5 else '🔵'
    print(f"  {icon} {vb['market']:15s} {vb['pick']:15s} @ {vb['cuota']:.2f}  Prob {vb['prob']:.1f}%  Edge +{vb['edge']:.1f}%  ({vb['src']})")

print(f"\n{'─'*60}")
print(f"🎰 COMBINADAS ({len(comb_pt)})")
print(f"{'─'*60}")
for c in comb_pt:
    print(f"\n  {c['name']}  ({c['n_picks']} pick{'s' if c['n_picks']>1 else ''})  |  Cuota: {c['cuota']:.2f}")
    print(f"  💡 {c['desc']}")
    for i, p in enumerate(c['picks']):
        sym = '└' if i == len(c['picks'])-1 else '├'
        print(f"     {sym} {p['pick']} @ {p['cuota']:.2f} (Prob {p['prob']:.1f}%)")

# ─── USA vs BÉLGICA ──────────────────────────────────────
print(f"\n{'='*60}")
print("🇺🇸🇧🇪 USA vs BÉLGICA — 00:00")
print("=" * 60)

det_us = sportdb_us.get('details', {})
print(f"📍 {det_us.get('venue','?')} ({det_us.get('venueCity','?')}), cap. {det_us.get('capacity','?')}")
print(f"👨‍⚖️ Árbitro: {det_us.get('referee','?')}")

prob2 = pred_us['probabilities']
xg_h2 = pred_us['expected_goals']['home']
xg_a2 = pred_us['expected_goals']['away']
ts_h2 = pred_us['team_stats']['home']
ts_a2 = pred_us['team_stats']['away']

print(f"\n📊 Motor: H={prob2['home']:.1f}% D={prob2['draw']:.1f}% A={prob2['away']:.1f}%")
print(f"⚽ xG: {xg_h2:.2f} - {xg_a2:.2f} (total {xg_h2+xg_a2:.2f})")
print(f"📈 USA:     {ts_h2['games']}P {ts_h2['wins']}W {ts_h2['draws']}D {ts_h2['losses']}L — GF {ts_h2['avg_goals_for']:.1f} GA {ts_h2['avg_goals_against']:.1f}")
print(f"   CK {ts_h2['avg_stats_raw']['cornerKicks']:.1f} YC {ts_h2['avg_stats_raw']['yellowCards']:.1f} Fouls {ts_h2['avg_stats_raw']['fouls']:.1f}")
print(f"📈 Bélgica:  {ts_a2['games']}P {ts_a2['wins']}W {ts_a2['draws']}D {ts_a2['losses']}L — GF {ts_a2['avg_goals_for']:.1f} GA {ts_a2['avg_goals_against']:.1f}")
print(f"   CK {ts_a2['avg_stats_raw']['cornerKicks']:.1f} YC {ts_a2['avg_stats_raw']['yellowCards']:.1f} Fouls {ts_a2['avg_stats_raw']['fouls']:.1f}")

vb_us = collect_value_bets(pred_us, 'id1000001653452515')
comb_us = build_combinadas(vb_us, pred_us)

print(f"\n{'─'*60}")
print(f"🎯 VALUE BETS ({len(vb_us)})")
print(f"{'─'*60}")
for vb in vb_us:
    icon = '🟢' if vb['edge'] > 15 else '🟡' if vb['edge'] > 5 else '🔵'
    print(f"  {icon} {vb['market']:15s} {vb['pick']:15s} @ {vb['cuota']:.2f}  Prob {vb['prob']:.1f}%  Edge +{vb['edge']:.1f}%  ({vb['src']})")

print(f"\n{'─'*60}")
print(f"🎰 COMBINADAS ({len(comb_us)})")
print(f"{'─'*60}")
for c in comb_us:
    print(f"\n  {c['name']}  ({c['n_picks']} pick{'s' if c['n_picks']>1 else ''})  |  Cuota: {c['cuota']:.2f}")
    print(f"  💡 {c['desc']}")
    for i, p in enumerate(c['picks']):
        sym = '└' if i == len(c['picks'])-1 else '├'
        print(f"     {sym} {p['pick']} @ {p['cuota']:.2f} (Prob {p['prob']:.1f}%)")

# ─── SAVE ────────────────────────────────────────────────
output = {
    'date': '2026-07-06',
    'matches': {
        'Portugal_vs_Spain': {
            'value_bets': vb_pt,
            'combinadas': [{'name': c['name'], 'cuota': c['cuota'], 'picks': c['picks'], 'desc': c['desc'], 'n_picks': c['n_picks']} for c in comb_pt],
            'venue': det_pt,
        },
        'USA_vs_Belgium': {
            'value_bets': vb_us,
            'combinadas': [{'name': c['name'], 'cuota': c['cuota'], 'picks': c['picks'], 'desc': c['desc'], 'n_picks': c['n_picks']} for c in comb_us],
            'venue': det_us,
        }
    }
}

with open('data/vbs_6julio_v3.json', 'w') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n✅ Guardado en data/vbs_6julio_v3.json")
