#!/usr/bin/env python3
"""
learning_dashboard.py — Dashboard HTML del sistema de aprendizaje.
Genera un informe visual con ROI, calibración, evolución y recomendaciones.
"""
import sys, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / "src"))
from worldcup.tracker import BetTracker, MARKET_TYPES

OUTPUT = Path(__file__).parent / "learning_dashboard.html"

def generate_html():
    tracker = BetTracker()
    report = tracker.get_report()
    o = report['overall']
    by_market = report['by_market']
    calibration = report.get('calibration', {})
    learned = report.get('learned_weights', {})
    
    # Preparar datos para gráficos
    market_labels = []
    market_rois = []
    market_wrs = []
    market_bets = []
    for m, s in sorted(by_market.items(), key=lambda x: x[1]['roi'], reverse=True):
        market_labels.append(m.replace('_', ' ').title())
        market_rois.append(s['roi'])
        market_wrs.append(s['win_rate'])
        market_bets.append(s['bets'])
    
    # Histórico de apuestas por resultado
    all_bet_results = []
    for result in tracker.results:
        for br in result.get('bet_results', []):
            all_bet_results.append({
                'match': result.get('match', '?'),
                'market': br.get('market', '?'),
                'direction': br.get('direction', '?'),
                'line': br.get('line', 0),
                'prob': br.get('prob', 0),
                'odd': br.get('odd', 0),
                'edge': br.get('edge_pct', 0),
                'actual': br.get('actual_value', 0),
                'won': br.get('won', False),
                'profit': br.get('profit', 0),
            })
    
    # Acumulado de profit
    cumulative = []
    running = 0
    for br in all_bet_results:
        running += br['profit']
        cumulative.append(round(running, 2))
    
    # Recomendaciones
    recommendations = calibration.get('recommendations', [])
    
    # Color por ROI
    def roi_color(roi):
        if roi > 20: return '#00ff88'
        if roi > 5: return '#88ff88'
        if roi > 0: return '#ffff88'
        if roi > -10: return '#ffaa88'
        return '#ff4444'
    
    # Win rate bar color
    def wr_color(wr):
        if wr > 55: return '#00ff88'
        if wr > 50: return '#88ff88'
        if wr > 45: return '#ffff88'
        return '#ff4444'
    
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🧠 Motor de Aprendizaje — World Cup 2026</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0e14; color:#e0e0e0; font-family:'Segoe UI',system-ui,sans-serif; padding:20px; }}
.container {{ max-width:1200px; margin:0 auto; }}
h1 {{ color:#60f0a0; font-size:2em; margin-bottom:5px; }}
h2 {{ color:#f0c040; font-size:1.3em; margin:25px 0 15px; border-bottom:1px solid #223; padding-bottom:8px; }}
.subtitle {{ color:#888; margin-bottom:25px; }}

/* KPI Cards */
.kpi-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:15px; margin:20px 0; }}
.kpi {{ background:#12161f; border:1px solid #1a2030; border-radius:12px; padding:18px; text-align:center; }}
.kpi-value {{ font-size:2em; font-weight:700; }}
.kpi-label {{ color:#888; font-size:0.85em; margin-top:4px; }}
.kpi-positive {{ color:#00ff88; }}
.kpi-negative {{ color:#ff4444; }}
.kpi-neutral {{ color:#f0c040; }}

/* Table */
table {{ width:100%; border-collapse:collapse; margin:10px 0; }}
th {{ background:#12161f; color:#f0c040; padding:12px; text-align:left; font-size:0.85em; text-transform:uppercase; letter-spacing:1px; }}
td {{ padding:10px 12px; border-bottom:1px solid #1a2030; }}
tr:hover {{ background:#12161f; }}
.badge {{ display:inline-block; padding:2px 10px; border-radius:20px; font-size:0.8em; font-weight:600; }}
.badge-green {{ background:#00ff8822; color:#00ff88; }}
.badge-red {{ background:#ff444422; color:#ff4444; }}
.badge-yellow {{ background:#f0c04022; color:#f0c040; }}

/* ROI Bar */
.roi-bar {{ height:24px; border-radius:4px; position:relative; min-width:4px; }}
.roi-bar-bg {{ background:#1a2030; border-radius:4px; overflow:hidden; height:24px; }}
.roi-bar-fill {{ height:100%; border-radius:4px; transition:width 0.5s; display:flex; align-items:center; padding-left:8px; font-size:0.75em; font-weight:600; }}

/* Profit Chart (CSS-only) */
.chart-container {{ background:#12161f; border:1px solid #1a2030; border-radius:12px; padding:20px; margin:15px 0; }}
.chart-line {{ display:flex; align-items:flex-end; height:200px; gap:2px; padding:0 5px; }}
.chart-bar {{ flex:1; min-width:3px; border-radius:2px 2px 0 0; transition:height 0.3s; }}

/* Recomendaciones */
.rec-card {{ background:#12161f; border:1px solid #1a2030; border-radius:10px; padding:15px; margin:8px 0; display:flex; align-items:center; gap:12px; }}
.rec-icon {{ font-size:1.5em; }}
.rec-text {{ flex:1; }}
.rec-market {{ font-weight:600; color:#f0c040; }}
.rec-reason {{ color:#aaa; font-size:0.9em; }}

/* Bet History */
.bet-won {{ color:#00ff88; }}
.bet-lost {{ color:#ff4444; }}
.bet-detail {{ font-size:0.8em; color:#888; }}

/* Scrollable */
.scroll-x {{ overflow-x:auto; }}

/* Insights */
.insight {{ background:linear-gradient(135deg,#12161f,#1a2030); border-left:4px solid #f0c040; border-radius:0 10px 10px 0; padding:15px 20px; margin:10px 0; }}
.insight-title {{ color:#f0c040; font-weight:600; margin-bottom:5px; }}
</style>
</head>
<body>
<div class="container">
<h1>🧠 Motor de Aprendizaje</h1>
<p class="subtitle">World Cup 2026 — Tracking de predicciones vs resultados reales</p>

<h2>📊 Resumen General</h2>
<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-value kpi-neutral">{o['total_matches']}</div>
    <div class="kpi-label">Partidos analizados</div>
  </div>
  <div class="kpi">
    <div class="kpi-value kpi-neutral">{o['total_bets']}</div>
    <div class="kpi-label">Apuestas totales</div>
  </div>
  <div class="kpi">
    <div class="kpi-value" style="color:{wr_color(o['win_rate'])}">{o['win_rate']}%</div>
    <div class="kpi-label">Win Rate</div>
  </div>
  <div class="kpi">
    <div class="kpi-value {'kpi-positive' if o['roi'] > 0 else 'kpi-negative'}">{'+' if o['roi'] > 0 else ''}{o['roi']}%</div>
    <div class="kpi-label">ROI Global</div>
  </div>
  <div class="kpi">
    <div class="kpi-value {'kpi-positive' if o['total_profit'] > 0 else 'kpi-negative'}">{'+' if o['total_profit'] > 0 else ''}{o['total_profit']}</div>
    <div class="kpi-label">Profit (units)</div>
  </div>
</div>

<h2>📈 Evolución del Profit</h2>
<div class="chart-container">
  <div class="chart-line">"""
    
    # Profit chart bars
    if cumulative:
        min_p = min(min(cumulative), 0)
        max_p = max(max(cumulative), 1)
        range_p = max_p - min_p if max_p != min_p else 1
        for p in cumulative:
            height = max(4, int((p - min_p) / range_p * 180))
            color = '#00ff88' if p >= 0 else '#ff4444'
            html += f'\n    <div class="chart-bar" style="height:{height}px;background:{color}" title="{p}"></div>'
    
    html += f"""
  </div>
  <div style="display:flex;justify-content:space-between;color:#666;font-size:0.75em;padding:5px 5px 0">
    <span>Primera apuesta</span>
    <span>Profit acumulado: {'+' if o['total_profit'] > 0 else ''}{o['total_profit']} units</span>
    <span>Última apuesta</span>
  </div>
</div>

<h2>🎯 Rendimiento por Mercado</h2>
<div class="scroll-x">
<table>
<thead>
<tr><th>Mercado</th><th>Apuestas</th><th>Win Rate</th><th>ROI</th><th>Profit</th><th>Visual</th></tr>
</thead>
<tbody>"""
    
    for m, s in sorted(by_market.items(), key=lambda x: x[1]['roi'], reverse=True):
        name = m.replace('_', ' ').title()
        roi = s['roi']
        wr = s['win_rate']
        bets = s['bets']
        profit = s['total_profit']
        
        badge = 'badge-green' if roi > 5 else 'badge-red' if roi < -5 else 'badge-yellow'
        bar_width = min(100, max(5, abs(roi)))
        bar_color = roi_color(roi)
        
        html += f"""
<tr>
  <td><strong>{name}</strong></td>
  <td>{bets}</td>
  <td><span style="color:{wr_color(wr)}">{wr}%</span></td>
  <td><span class="badge {badge}">{'+' if roi > 0 else ''}{roi}%</span></td>
  <td style="color:{'#00ff88' if profit > 0 else '#ff4444'}">{'+' if profit > 0 else ''}{profit}</td>
  <td>
    <div class="roi-bar-bg">
      <div class="roi-bar-fill" style="width:{bar_width}%;background:{bar_color}">{roi}%</div>
    </div>
  </td>
</tr>"""
    
    html += """
</tbody>
</table>
</div>

<h2>💡 Insights del Motor</h2>
"""
    
    # Auto-generate insights
    insights = []
    if 'corners_under' in by_market:
        cu = by_market['corners_under']
        if cu['roi'] > 10:
            insights.append({
                'title': 'Córners Under = Edge real',
                'text': f"Con {cu['bets']} apuestas y {cu['win_rate']}% win rate, el modelo detecta bien los partidos con pocos córners. ROI de +{cu['roi']}%. Mantener o subir peso."
            })
    if 'cards_over' in by_market:
        co = by_market['cards_over']
        if co['roi'] > 5:
            insights.append({
                'title': 'Tarjetas Over = consistente',
                'text': f"{co['bets']} apuestas, {co['win_rate']}% acierto. El modelo sobreestima tarjetas en general, pero eso genera edge en Over porque las cuotas están ajustadas para más tarjetas."
            })
    if 'corners_over' in by_market:
        co = by_market['corners_over']
        if co['roi'] < -5:
            insights.append({
                'title': 'Córners Over = fuga de dinero',
                'text': f"ROI {co['roi']}% en {co['bets']} apuestas. El modelo predice demasiados córners. Reducir peso o invertir la dirección."
            })
    
    # Calibration insights
    for m, s in by_market.items():
        cal = s.get('calibration_error')
        if cal and cal > 15:
            name = m.replace('_', ' ').title()
            insights.append({
                'title': f'{name}: probabilidades poco fiables',
                'text': f"Error de calibración del {cal}% — cuando el modelo dice {s['avg_prob']}%, gana el {s['win_rate']}%. Las probabilidades del modelo no son confiables para este mercado."
            })
    
    if not insights:
        insights.append({'title': 'Pocos datos aún', 'text': 'Se necesitan más partidos para generar insights fiables. Cada jornada que pasa, el motor aprende más.'})
    
    for ins in insights:
        html += f"""
<div class="insight">
  <div class="insight-title">{ins['title']}</div>
  <div>{ins['text']}</div>
</div>"""
    
    html += f"""

<h2>🔧 Recomendaciones de Peso</h2>
"""
    
    if recommendations:
        for rec in recommendations:
            arrow = '⬆️' if rec['action'] == 'increase_weight' else '⬇️'
            action_text = 'Subir peso' if rec['action'] == 'increase_weight' else 'Bajar peso'
            if rec['action'] == 'recalibrate_probabilities':
                arrow = '🔄'
                action_text = 'Recalibrar probabilidades'
            
            html += f"""
<div class="rec-card">
  <div class="rec-icon">{arrow}</div>
  <div class="rec-text">
    <div class="rec-market">{rec['market'].replace('_', ' ').title()}</div>
    <div class="rec-reason">{action_text}: {rec['reason']}</div>
  </div>
</div>"""
    else:
        html += '<p style="color:#888">Sin recomendaciones automáticas aún (mínimo 10 apuestas por mercado).</p>'
    
    # Bet history
    html += f"""

<h2>📋 Historial de Apuestas ({len(all_bet_results)} total)</h2>
<div class="scroll-x">
<table>
<thead>
<tr><th>Partido</th><th>Mercado</th><th>Línea</th><th>Prob</th><th>Cuota</th><th>Real</th><th>Resultado</th><th>P/L</th></tr>
</thead>
<tbody>"""
    
    for br in all_bet_results[-50:]:  # últimas 50
        result_class = 'bet-won' if br['won'] else 'bet-lost'
        result_icon = '✅' if br['won'] else '❌'
        profit_str = f"+{br['profit']:.2f}" if br['profit'] > 0 else f"{br['profit']:.2f}"
        
        html += f"""
<tr>
  <td>{br['match']}</td>
  <td>{br['market'].replace('_', ' ')}</td>
  <td>{br['direction'].upper()} {br['line']}</td>
  <td>{br['prob']*100:.0f}%</td>
  <td>{br['odd']:.2f}</td>
  <td>{br['actual']}</td>
  <td class="{result_class}">{result_icon}</td>
  <td class="{result_class}">{profit_str}</td>
</tr>"""
    
    html += f"""
</tbody>
</table>
</div>

<div style="text-align:center;color:#444;padding:30px;font-size:0.8em">
  Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Motor de Aprendizaje v1.0
</div>

</div>
</body>
</html>"""
    
    return html


if __name__ == '__main__':
    html = generate_html()
    OUTPUT.write_text(html, encoding='utf-8')
    print(f"Dashboard generado: {OUTPUT}")
