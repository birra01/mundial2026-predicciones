#!/usr/bin/env python3
"""4 Combinadas diversificadas — 6 Julio 2026
   Todas con picks de edge positivo únicamente"""

# Value bets con edge+ (del análisis anterior)
# Format: (label, prob, cuota, match, market)
vbs = [
    ("PT Tarjetas U3.5", 0.886, 1.80, "Portugal vs España", "Tarjetas"),
    ("PT Tarjetas U2.5", 0.723, 2.25, "Portugal vs España", "Tarjetas"),
    ("PT 1X2 Portugal",  0.404, 4.20, "Portugal vs España", "1X2"),
    ("USA Tarjetas U3.5", 0.721, 1.80, "USA vs Bélgica", "Tarjetas"),
    ("USA Córners O9.5", 0.659, 1.80, "USA vs Bélgica", "Córners"),
    ("USA Tarjetas U2.5", 0.501, 2.25, "USA vs Bélgica", "Tarjetas"),
    ("USA 1X2 USA",       0.453, 2.50, "USA vs Bélgica", "1X2"),
    ("USA Goles O2.5",    0.649, 1.66, "USA vs Bélgica", "Goles"),
    ("PT BTTS No",        0.521, 2.05, "Portugal vs España", "BTTS"),
    ("USA Goles O3.5",    0.428, 2.50, "USA vs Bélgica", "Goles"),
    ("USA Goles O4.5",    0.245, 4.50, "USA vs Bélgica", "Goles"),
    ("USA Goles O1.5",    0.846, 1.20, "USA vs Bélgica", "Goles"),
]

def comb_prob(picks):
    p = 1.0
    for _, prob, _, _, _ in picks:
        p *= prob
    return p

def comb_cuota(picks):
    c = 1.0
    for _, _, cuota, _, _ in picks:
        c *= cuota
    return c

def comb_edge(picks):
    p = comb_prob(picks)
    c = comb_cuota(picks)
    return (p * c - 1) * 100

# ============================================================
# COMBINADA SEGURA — 3 picks alta prob, mercados distintos
# ============================================================
segura = [vbs[0], vbs[4], vbs[7]]  # PT Tarjetas U3.5 + USA CK O9.5 + USA Goles O2.5

# ============================================================
# COMBINADA MEDIA — 3 picks, mezcla mercados
# ============================================================
media = [vbs[0], vbs[3], vbs[8]]  # PT Tarjetas U3.5 + USA Tarjetas U3.5 + PT BTTS No

# ============================================================
# COMBINADA SOÑADORA — 3 picks, cuota alta
# ============================================================
sonadora = [vbs[2], vbs[6], vbs[0]]  # PT 1X2 + USA 1X2 + PT Tarjetas U3.5

# ============================================================
# COMBINADA VOLÁTIL — 3 picks, muy agresiva
# ============================================================
volatil = [vbs[2], vbs[9], vbs[1]]  # PT 1X2 + USA Goles O3.5 + PT Tarjetas U2.5

combos = [
    ("SEGURA", segura, "Alta probabilidad, mercados mixtos, riesgo bajo"),
    ("MEDIA", media, "Probabilidad media, diversificación por mercado"),
    ("SOÑADORA", sonadora, "Cuota alta, ambos favoritos + seguro"),
    ("VOLÁTIL", volatil, "Agresiva, máximos edges, alto riesgo"),
]

print("=" * 80)
print("COMBINADAS — 6 JULIO 2026")
print("=" * 80)

for name, picks, desc in combos:
    p = comb_prob(picks)
    c = comb_cuota(picks)
    e = comb_edge(picks)
    print(f"\n{'='*60}")
    print(f"  {name} | Cuota: {c:.2f} | Prob: {p*100:.1f}% | EV: {e:+.1f}%")
    print(f"  {desc}")
    print(f"{'='*60}")
    for label, prob, cuota, match, market in picks:
        edg = (prob * cuota - 1) * 100
        print(f"    {label:<25} | P={prob*100:5.1f}% | @ {cuota:.2f} | Edge={edg:+.1f}% | {match}")

print("\n" + "=" * 80)
print("RESUMEN")
print("=" * 80)
for name, picks, _ in combos:
    p = comb_prob(picks)
    c = comb_cuota(picks)
    e = comb_edge(picks)
    print(f"  {name:<12} @ {c:5.2f}  |  Prob: {p*100:5.1f}%  |  EV: {e:+6.1f}%")
