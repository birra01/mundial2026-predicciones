#!/usr/bin/env python3
"""
genera_preview_hoy.py — Crea hoy_preview.html con el analisis de hoy
(value bets + narrativa) desde data/hoy_analysis.json. SIN combinadas.
"""
import json, os
from pathlib import Path

BASE = Path(__file__).parent
data = json.load(open(BASE / "data" / "hoy_analysis.json"))

DISPLAY = {
    "Norway": "Noruega", "England": "Inglaterra",
    "Argentina": "Argentina", "Switzerland": "Suiza",
}

def disp(n):
    return DISPLAY.get(n, n)

def bet_icon(e):
    return "🟢" if e > 15 else "🟡" if e > 5 else "🔵"

cards = []
for key, m in data["matches"].items():
    home, away = key.split("_vs_")
    h = disp(home); a = disp(away)
    prob = m["probabilities"]
    xg = m["expected_goals"]
    vbs = m["value_bets"]
    rows = "".join(
        f"<tr><td>{bet_icon(v['edge'])}</td><td>{v['market']}</td><td>{v['pick']}</td>"
        f"<td class='cuota'>{v['cuota']:.2f}</td><td>{v['prob']:.1f}%</td>"
        f"<td class='{'pos' if v['edge']>0 else 'neg'}'>+{v['edge']:.1f}%</td>"
        f"<td class='src'>{v['src']}</td></tr>"
        for v in vbs
    )
    cards.append(f"""
    <div class="match-card">
      <div class="match-head">
        <span class="home">{h}</span><span class="vs">vs</span><span class="away">{a}</span>
      </div>
      <div class="prob-bar">
        <span>H {prob['home']:.0f}%</span><span>E {prob['draw']:.0f}%</span><span>A {prob['away']:.0f}%</span>
      </div>
      <div class="xg">xG: {h} {xg['home']:.2f} - {xg['away']:.2f} {a} &nbsp;|&nbsp; Pred: {m['prediction']} ({m['confidence']})</div>
      <div class="narr">{m['narrative']}</div>
      <h3>🎯 Value Bets ({len(vbs)})</h3>
      <table class="vb">
        <thead><tr><th></th><th>Mercado</th><th>Apuesta</th><th>Cuota</th><th>Prob</th><th>Edge</th><th>Fuente</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>""")

html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>Análisis Mundial 2026 — 11 julio</title>
<style>
body{{background:#0a0e27;color:#e8ecf5;font-family:system-ui,Arial;margin:0;padding:24px;}}
h1{{color:#f0c040;text-align:center;}}
.note{{text-align:center;color:#9aa;margin-bottom:20px;}}
.match-card{{background:#151a35;border:1px solid #2a3155;border-radius:12px;padding:18px;margin:18px auto;max-width:880px;}}
.match-head{{display:flex;justify-content:center;gap:14px;font-size:22px;font-weight:700;}}
.home{{color:#3fd07a;}} .away{{color:#ff6b6b;}} .vs{{color:#889;}}
.prob-bar{{display:flex;justify-content:center;gap:18px;margin:10px 0;color:#cdd;}}
.xg{{text-align:center;color:#bcd;font-size:14px;margin:6px 0;}}
.narr{{background:#0e1330;border-left:3px solid #e09020;padding:10px 12px;margin:10px 0;border-radius:6px;font-size:13px;color:#cde;}}
h3{{color:#f0c040;margin:14px 0 8px;}}
table.vb{{width:100%;border-collapse:collapse;font-size:13px;}}
table.vb th{{color:#9ab;text-align:left;padding:6px;border-bottom:1px solid #2a3155;}}
table.vb td{{padding:6px;border-bottom:1px solid #1c2244;}}
.cuota{{color:#f0c040;font-weight:700;}}
.pos{{color:#3fd07a;}} .neg{{color:#ff6b6b;}} .src{{color:#778;font-size:11px;}}
</style></head><body>
<h1>⚽ Análisis Mundial 2026 — 11 julio</h1>
<div class="note">Solo análisis (value bets). Las combinadas se arman tras tu aprobación.</div>
{''.join(cards)}
</body></html>"""

out = BASE / "hoy_preview.html"
out.write_text(html, encoding="utf-8")
print(f"✅ Generado: {out}  ({len(data['matches'])} partidos)")
