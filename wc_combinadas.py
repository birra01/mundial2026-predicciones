#!/usr/bin/env python3
"""Combinadas con motor v2 (stats ajustadas por rival) + cuotas reales bet365"""
import sys, math
sys.path.insert(0, 'src')
from worldcup.engine import WorldCupEngine

engine = WorldCupEngine()
engine.load_data()

# Partidos
r_br = engine.predict_match("Brazil", "Japan")
r_ge = engine.predict_match("Germany", "Paraguay")
r_ne = engine.predict_match("Netherlands", "Morocco")

p_br = r_br['probabilities']
p_ge = r_ge['probabilities']
p_ne = r_ne['probabilities']

eg_br = r_br['expected_goals']
eg_ge = r_ge['expected_goals']
eg_ne = r_ne['expected_goals']

def poisson(lam, k):
    return (lam**k) * math.exp(-lam) / math.factorial(k)

def p_over(lam, thresh):
    return 1 - sum(poisson(lam, k) for k in range(thresh + 1))

# ─── CUOTAS REALES BET365 ───
# Brazil-Japan
CUOTA_BR_OVER15 = 1.12
CUOTA_JP_WIN = 5.25
# Germany-Paraguay
CUOTA_GE_OVER15 = 1.22
CUOTA_GE_OVER35 = 2.75
CUOTA_GE_WIN = 1.30
CUOTA_PY_DOBLE = 3.55  # Paraguay o empate
# Netherlands-Morocco
CUOTA_NE_OVER15 = 1.15
CUOTA_NE_AM = 1.80
CUOTA_MA_WIN = 3.60

# ─── PROBABILIDADES REALES (motor v2) ───
# +1.5 goles (Poisson)
br_p15 = p_over(eg_br['home'] + eg_br['away'], 1)
ge_p15 = p_over(eg_ge['home'] + eg_ge['away'], 1)
ne_p15 = p_over(eg_ne['home'] + eg_ne['away'], 1)
# ─── Probabilidades extra ───
br_over25_prob = p_over(eg_br['home'] + eg_br['away'], 2)
ge_p25 = p_over(eg_ge['home'] + eg_ge['away'], 2)
ge_p35 = p_over(eg_ge['home'] + eg_ge['away'], 3)
ne_btts_prob = (1-poisson(eg_ne['home'], 0)) * (1-poisson(eg_ne['away'], 0))
CUOTA_BR_OVER25 = 2.10

# Probabilidad Germany GANA + Over 2.5 (con correlación)
ge_win_over25 = (p_ge['home'] / 100) * ge_p25 * 0.85

# Doble oportunidad Paraguay
py_doble = (p_ge['away'] + p_ge['draw']) / 100

# ─── 🟢 SEGURA: Over 1.5 en los 3 ───
p_seg = br_p15 * ge_p15 * ne_p15
cuota_seg = CUOTA_BR_OVER15 * CUOTA_GE_OVER15 * CUOTA_NE_OVER15

# ─── 🟠 MEDIA: Over 2.5 Br-Jp + Germany WIN + Ambos marcan NL-MA ───
CUOTA_BR_OVER25 = 2.10
ge_win_over25 = (p_ge['home'] / 100) * ge_p25 * 0.85
p_med = br_over25_prob * (p_ge['home'] / 100) * ne_btts_prob
cuota_med = CUOTA_BR_OVER25 * CUOTA_GE_WIN * CUOTA_NE_AM

# ─── 🔴 SOÑADORA: Over 2.5 Br-Jp + Over 3.5 Germ + Morocco GANA ───
p_son = br_over25_prob * ge_p35 * (p_ne['away'] / 100)
cuota_son = CUOTA_BR_OVER25 * CUOTA_GE_OVER35 * CUOTA_MA_WIN

print("=" * 80)
print("  COMBINADAS CON CUOTAS BET365 — MOTOR V2 (stats ajustadas por rival)")
print("=" * 80)

for nombre, prob, cuota, emoji, patas in [
    ("SEGURA", p_seg, cuota_seg, "🟢", [
        (f"Brazil vs Japan: +1.5 goles", CUOTA_BR_OVER15, f"P={br_p15*100:.0f}%"),
        (f"Germany vs Paraguay: +1.5 goles", CUOTA_GE_OVER15, f"P={ge_p15*100:.0f}%"),
        (f"Netherlands vs Morocco: +1.5 goles", CUOTA_NE_OVER15, f"P={ne_p15*100:.0f}%"),
    ]),
    ("MEDIA", p_med, cuota_med, "🟠", [
        (f"Brazil vs Japan: Over 2.5 goles", CUOTA_BR_OVER25, f"P={br_over25_prob*100:.0f}%"),
        (f"Germany GANA", CUOTA_GE_WIN, f"Prob real {p_ge['home']:.0f}%"),
        (f"Netherlands vs Morocco: AMBOS marcan", CUOTA_NE_AM, f"P={ne_btts_prob*100:.0f}%"),
    ]),
    ("SOÑADORA", p_son, cuota_son, "🔴", [
        (f"Brazil vs Japan: Over 2.5 goles", CUOTA_BR_OVER25, f"P={br_over25_prob*100:.0f}%"),
        (f"Germany vs Paraguay: Over 3.5 goles", CUOTA_GE_OVER35, f"P={ge_p35*100:.0f}%"),
        (f"Morocco GANA", CUOTA_MA_WIN, f"Prob real {p_ne['away']:.0f}%"),
    ]),
]:
    print(f"\n{'─'*80}")
    print(f"  {emoji} {nombre:12} | Prob: {prob*100:.1f}% | Cuota bet365: {cuota:.2f} | 10€ → ~{10*cuota:.0f}€")
    print(f"{'─'*80}")
    for i, (texto, cuota_pata, detalle) in enumerate(patas, 1):
        print(f"  {i}. {texto} (@{cuota_pata})  [{detalle}]")

print(f"\n{'='*80}")
print(f"| {'COMBINADA':^15} | {'PROB':^8} | {'CUOTA':^8} | {'10€ →':^12} |")
print("|" + "-"*16 + "|" + "-"*10 + "|" + "-"*10 + "|" + "-"*14 + "|")
print(f"| {'🟢 Segura':^15} | {p_seg*100:>6.1f}% | {cuota_seg:>6.2f} | {10*cuota_seg:>10.0f}€ |")
print(f"| {'🟠 Media':^15} | {p_med*100:>6.1f}% | {cuota_med:>6.2f} | {10*cuota_med:>10.0f}€ |")
print(f"| {'🔴 Soñadora':^15} | {p_son*100:>6.1f}% | {cuota_son:>6.2f} | {10*cuota_son:>10.0f}€ |")
print(f"{'='*80}")
