#!/usr/bin/env python3
"""8 Combinadas — 4 por partido, mercados de UN solo partido cada una
   6 Julio 2026 — Portugal vs España + USA vs Bélgica"""

def edge(prob, cuota):
    return round((prob * cuota - 1) * 100, 1)

# ================================================================
# PORTUGAL vs ESPAÑA — picks disponibles (edge+)
# ================================================================
# PT Tarj U3.5  (88.6%, 1.80)  edge +33.1
# PT Tarj U2.5  (72.3%, 2.25)  edge +27.8
# PT 1X2        (40.4%, 4.20)  edge +16.6
# PT BTTS No    (52.1%, 2.05)  edge +6.8
# PT O2.5       (55.2%, 1.75)  edge ~-3.6 (NO value, skip)
# PT O1.5       (79.3%, 1.25)  edge ~-0.9 (marginal, skip)

# COMBINADAS PORTUGAL-ESPAÑA:
pt_segura = [
    ("Tarjetas U3.5", 0.886, 1.80),
    ("BTTS No",        0.521, 2.05),
]
pt_media = [
    ("Tarjetas U2.5",  0.723, 2.25),
    ("BTTS No",        0.521, 2.05),
]
pt_sonadora = [
    ("1X2 Portugal",   0.404, 4.20),
    ("Tarjetas U3.5",  0.886, 1.80),
]
pt_volatil = [
    ("1X2 Portugal",   0.404, 4.20),
    ("Tarjetas U2.5",  0.723, 2.25),
]

# ================================================================
# USA vs BÉLGICA — picks disponibles (edge+)
# ================================================================
# USA Tarj U3.5  (72.1%, 1.80)  edge +16.5
# USA CK O9.5    (65.9%, 1.80)  edge +10.4
# USA Tarj U2.5  (50.1%, 2.25)  edge +5.7
# USA 1X2 USA    (45.3%, 2.50)  edge +5.3
# USA O2.5       (64.9%, 1.66)  edge +4.6
# USA O3.5       (42.8%, 2.50)  edge +2.8

# COMBINADAS USA-BÉLGICA:
usa_segura = [
    ("Córners O9.5",   0.659, 1.80),
    ("Tarjetas U3.5",  0.721, 1.80),
]
usa_media = [
    ("Tarjetas U3.5",  0.721, 1.80),
    ("Tarjetas U2.5",  0.501, 2.25),
]
usa_sonadora = [
    ("1X2 USA",        0.453, 2.50),
    ("Tarjetas U3.5",  0.721, 1.80),
]
usa_volatil = [
    ("1X2 USA",        0.453, 2.50),
    ("Goles O3.5",     0.428, 2.50),
]

combos = [
    ("PORTUGAL-ESPAÑA", [
        ("SEGURA",   pt_segura,   "Alta prob, mercados mixtos"),
        ("MEDIA",    pt_media,    "Doble under, riesgo moderado"),
        ("SOÑADORA", pt_sonadora, "Portugal gana + seguro tarjetas"),
        ("VOLÁTIL",  pt_volatil,  "Portugal gana + under tarjetas agresivo"),
    ]),
    ("USA-BÉLGICA", [
        ("SEGURA",   usa_segura,  "Córners + tarjetas, alta prob"),
        ("MEDIA",    usa_media,   "Doble under tarjetas"),
        ("SOÑADORA", usa_sonadora,"USA gana + tarjetas"),
        ("VOLÁTIL",  usa_volatil, "USA gana + goles altos"),
    ]),
]

print("=" * 70)
print("COMBINADAS — 6 JULIO 2026 (una por partido)")
print("=" * 70)

for match_name, tiers in combos:
    print(f"\n{'─'*70}")
    print(f"  ⚽ {match_name}")
    print(f"{'─'*70}")
    for tier_name, picks, desc in tiers:
        cuota = 1.0
        prob = 1.0
        for _, p, c in picks:
            cuota *= c
            prob *= p
        ev = edge(prob, cuota)
        
        icon = {"SEGURA": "🟢", "MEDIA": "🟠", "SOÑADORA": "🔴", "VOLÁTIL": "🔥"}[tier_name]
        print(f"\n  {icon} {tier_name:<10} @ {cuota:5.2f} | Prob: {prob*100:5.1f}% | EV: {ev:+.1f}%")
        print(f"     {desc}")
        for label, p, c in picks:
            e = edge(p, c)
            print(f"       • {label:<18} {p*100:5.1f}% @ {c:.2f}  (edge {e:+.1f}%)")

print(f"\n{'='*70}")
print("RESUMEN RÁPIDO")
print("=" * 70)
for match_name, tiers in combos:
    print(f"\n  {match_name}:")
    for tier_name, picks, _ in tiers:
        cuota = 1.0
        prob = 1.0
        for _, p, c in picks:
            cuota *= c
            prob *= p
        ev = edge(prob, cuota)
        print(f"    {tier_name:<10} @ {cuota:5.2f}  Prob: {prob*100:5.1f}%  EV: {ev:+.1f}%")
