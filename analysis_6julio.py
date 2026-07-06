#!/usr/bin/env python3
"""Análisis exhaustivo 5 mercados: Goles, BTTS, Córners, Tarjetas, 1X2
   Para Portugal vs Spain y USA vs Belgium — 6 Julio 2026"""
import json, math
from itertools import product as iprod

def poisson_pmf(lam, k):
    return (lam**k * math.exp(-lam)) / math.factorial(k)

def over_prob(lam, thresh):
    """P(X > thresh)"""
    return 1 - sum(poisson_pmf(lam, k) for k in range(int(thresh) + 1))

def btts_prob(lam_h, lam_a):
    """P(ambos marcan >= 1)"""
    p_h0 = poisson_pmf(lam_h, 0)
    p_a0 = poisson_pmf(lam_a, 0)
    return 1 - p_h0 - p_a0 + p_h0 * p_a0

def edge(model_prob, cuota):
    """Edge = model_prob - (1/cuota)"""
    if cuota is None or cuota <= 0:
        return None
    implied = 1.0 / cuota
    return (model_prob - implied) * 100  # percentage

def ev_pct(model_prob, cuota):
    """EV% = (model_prob * cuota - 1) * 100"""
    if cuota is None or cuota <= 0:
        return None
    return (model_prob * cuota - 1) * 100

# === ENGINE PREDICTIONS (from worldcup engine) ===
matches = [
    {
        "home": "Portugal", "away": "Spain",
        "home_es": "Portugal", "away_es": "España",
        "prob_h": 0.404, "prob_d": 0.275, "prob_a": 0.320,
        "xg_h": 1.0, "xg_a": 1.42,
        # Raw stats from engine
        "ck_h": 3.33, "ck_a": 6.0,  # Portugal corners avg, Spain corners avg
        "yc_h": 1.33, "yc_a": 0.5,  # Portugal YC avg, Spain YC avg
        "raw_ck_h": 3.33, "raw_ck_a": 6.0,
        "raw_yc_h": 1.33, "raw_yc_a": 0.5,
        # bet365 odds
        "b365": {
            "1x2_h": 4.2, "1x2_d": 3.6, "1x2_a": 1.85,
            "over_15": 1.25, "over_25": 1.8, "over_35": 3.0, "over_45": 5.5,
            "btts_yes": 1.7, "btts_no": 2.05,
            "ck_over_95": 1.83, "ck_under_95": 1.83,
            "yc_over_25": 1.57, "yc_under_25": 2.25,
            "yc_over_35": 1.9, "yc_under_35": 1.8,
        }
    },
    {
        "home": "USA", "away": "Belgium",
        "home_es": "USA", "away_es": "Bélgica",
        "prob_h": 0.453, "prob_d": 0.244, "prob_a": 0.304,
        "xg_h": 1.67, "xg_a": 1.67,
        "ck_h": 6.33, "ck_a": 4.67,
        "yc_h": 1.67, "yc_a": 1.0,
        "raw_ck_h": 6.33, "raw_ck_a": 4.67,
        "raw_yc_h": 1.67, "raw_yc_a": 1.0,
        "b365": {
            "1x2_h": 2.5, "1x2_d": 3.4, "1x2_a": 2.8,
            "over_15": 1.2, "over_25": 1.66, "over_35": 2.5, "over_45": 4.5,
            "btts_yes": 1.5, "btts_no": 2.5,
            "ck_over_95": 1.8, "ck_under_95": 1.9,
            "yc_over_25": 1.57, "yc_under_25": 2.25,
            "yc_over_35": 1.9, "yc_under_35": 1.8,
        }
    }
]

all_vbs = []

for m in matches:
    label = f"{m['home_es']} vs {m['away_es']}"
    b = m["b365"]
    
    # === GOLES (Poisson) ===
    lam_h = m["xg_h"]
    lam_a = m["xg_a"]
    lam_total = lam_h + lam_a
    
    goals_markets = [
        ("Goles O1.5", over_prob(lam_total, 1), b.get("over_15")),
        ("Goles O2.5", over_prob(lam_total, 2), b.get("over_25")),
        ("Goles O3.5", over_prob(lam_total, 3), b.get("over_35")),
        ("Goles O4.5", over_prob(lam_total, 4), b.get("over_45")),
    ]
    
    for mk, prob, cuota in goals_markets:
        if cuota:
            e = edge(prob, cuota)
            ev = ev_pct(prob, cuota)
            all_vbs.append({"match": label, "market": mk, "pick": mk, "prob": prob, "cuota": cuota, "edge": e, "ev": ev})
    
    # === BTTS ===
    p_btts = btts_prob(lam_h, lam_a)
    btts_markets = [
        ("BTTS Sí", p_btts, b.get("btts_yes")),
        ("BTTS No", 1 - p_btts, b.get("btts_no")),
    ]
    for mk, prob, cuota in btts_markets:
        if cuota:
            e = edge(prob, cuota)
            ev = ev_pct(prob, cuota)
            all_vbs.append({"match": label, "market": mk, "pick": mk, "prob": prob, "cuota": cuota, "edge": e, "ev": ev})
    
    # === 1X2 ===
    x12_markets = [
        ("1X2 " + m["home_es"], m["prob_h"], b.get("1x2_h")),
        ("1X2 Empate", m["prob_d"], b.get("1x2_d")),
        ("1X2 " + m["away_es"], m["prob_a"], b.get("1x2_a")),
    ]
    for mk, prob, cuota in x12_markets:
        if cuota:
            e = edge(prob, cuota)
            ev = ev_pct(prob, cuota)
            all_vbs.append({"match": label, "market": mk, "pick": mk, "prob": prob, "cuota": cuota, "edge": e, "ev": ev})
    
    # === CÓRNERS (Poisson on raw stats) ===
    ck_total = m["raw_ck_h"] + m["raw_ck_a"]
    ck_markets = [
        ("Córners O9.5", over_prob(ck_total, 9), b.get("ck_over_95")),
        ("Córners U9.5", 1 - over_prob(ck_total, 9), b.get("ck_under_95")),
    ]
    for mk, prob, cuota in ck_markets:
        if cuota:
            e = edge(prob, cuota)
            ev = ev_pct(prob, cuota)
            all_vbs.append({"match": label, "market": mk, "pick": mk, "prob": prob, "cuota": cuota, "edge": e, "ev": ev})
    
    # === TARJETAS (Poisson on raw stats) ===
    yc_total = m["raw_yc_h"] + m["raw_yc_a"]
    yc_markets = [
        ("Tarjetas O2.5", over_prob(yc_total, 2), b.get("yc_over_25")),
        ("Tarjetas U2.5", 1 - over_prob(yc_total, 2), b.get("yc_under_25")),
        ("Tarjetas O3.5", over_prob(yc_total, 3), b.get("yc_over_35")),
        ("Tarjetas U3.5", 1 - over_prob(yc_total, 3), b.get("yc_under_35")),
    ]
    for mk, prob, cuota in yc_markets:
        if cuota:
            e = edge(prob, cuota)
            ev = ev_pct(prob, cuota)
            all_vbs.append({"match": label, "market": mk, "pick": mk, "prob": prob, "cuota": cuota, "edge": e, "ev": ev})

# Sort by edge descending
all_vbs.sort(key=lambda x: x["edge"] if x["edge"] is not None else -999, reverse=True)

# Print all
print("=" * 80)
print("ANÁLISIS EXHAUSTIVO — 6 JULIO 2026 — PORTUGAL-ESPAÑA + USA-BÉLGICA")
print("=" * 80)
print(f"\n{'Rank':<5} {'Match':<22} {'Market':<18} {'Prob%':<8} {'Cuota':<7} {'Edge%':<8} {'EV%':<8}")
print("-" * 80)
for i, vb in enumerate(all_vbs, 1):
    print(f"{i:<5} {vb['match']:<22} {vb['market']:<18} {vb['prob']*100:<7.1f}% {vb['cuota']:<7.2f} {vb['edge']:+7.1f}% {vb['ev']:+7.1f}%")

# Market distribution
markets = {}
for vb in all_vbs:
    mkt = vb["market"].split(" ")[0]  # "Goles", "BTTS", "1X2", "Córners", "Tarjetas"
    markets[mkt] = markets.get(mkt, 0) + 1
print(f"\nDistribución por mercado: {markets}")
print(f"Total value bets: {len(all_vbs)}")

# Filter positive edge only
pos = [v for v in all_vbs if v["edge"] > 0]
print(f"\nCon edge positivo: {len(pos)}")
for i, vb in enumerate(pos, 1):
    print(f"  {i}. {vb['match']} | {vb['market']} | P={vb['prob']*100:.1f}% | Cuota={vb['cuota']} | Edge={vb['edge']:+.1f}% | EV={vb['ev']:+.1f}%")

# Save JSON for web
json_vbs = []
for vb in all_vbs:
    json_vbs.append({
        "match": vb["match"],
        "market": vb["market"],
        "pick": vb["pick"],
        "prob": round(vb["prob"], 4),
        "cuota": vb["cuota"],
        "edge": round(vb["edge"], 2),
        "ev": round(vb["ev"], 2),
        "bookie": "bet365"
    })

with open("data/vbs_6julio.json", "w") as f:
    json.dump(json_vbs, f, indent=2, ensure_ascii=False)
print(f"\n✅ Guardado: data/vbs_6julio.json ({len(json_vbs)} bets)")
