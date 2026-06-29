#!/usr/bin/env python3
"""
World Cup 2026 — Predicciones Web
Genera HTML premium con analisis de los 3 partidos de octavos (29 junio 2026)
"""

import sys
import os
from pathlib import Path
import json
import webbrowser

# Añadir src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from worldcup.engine import WorldCupEngine

def generate_web():
    """Genera predicciones.html con diseño premium"""
    
    # Cargar motor
    engine = WorldCupEngine()
    engine.load_data()
    
    # Partidos de hoy
    matches_today = [
        ("Brazil", "Japan", "12:00"),
        ("Germany", "Paraguay", "16:30"),
        ("Netherlands", "Morocco", "19:00"),
    ]
    
    predictions = []
    for home, away, time in matches_today:
        r = engine.predict_match(home, away)
        r['time'] = time
        predictions.append(r)
    
    # Construir HTML
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mundial 2026 — Predicciones 29 Junio</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            background: #0a0e27;
            color: #e0e0e0;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        
        .header {{
            text-align: center;
            padding: 40px 20px 30px;
            background: linear-gradient(135deg, #1a1f3a 0%, #0f1330 100%);
            border-radius: 20px;
            margin-bottom: 30px;
            border: 1px solid #2a2f4a;
        }}
        
        .header h1 {{
            font-size: 2.4em;
            background: linear-gradient(135deg, #f0c040, #e09020);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
        }}
        
        .header .subtitle {{
            color: #8890b0;
            font-size: 1.1em;
        }}
        
        .header .badge {{
            display: inline-block;
            background: #e09020;
            color: #0a0e27;
            padding: 4px 16px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 0.85em;
            margin-top: 12px;
        }}
        
        .match-card {{
            background: linear-gradient(145deg, #151a35 0%, #111530 100%);
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 24px;
            border: 1px solid #2a2f4a;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .match-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        }}
        
        .match-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
            gap: 20px;
        }}
        
        .match-time {{
            background: #1e2445;
            padding: 8px 16px;
            border-radius: 10px;
            font-size: 0.9em;
            color: #a0a8c0;
            font-weight: 600;
            white-space: nowrap;
        }}
        
        .teams {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 20px;
            flex: 1;
        }}
        
        .team {{
            font-size: 1.5em;
            font-weight: 700;
            color: #ffffff;
            text-shadow: 0 0 20px rgba(255,255,255,0.1);
        }}
        
        .vs {{
            color: #5a6080;
            font-size: 1em;
            font-weight: 400;
        }}
        
        .prediction-badge {{
            padding: 8px 20px;
            border-radius: 12px;
            font-weight: 700;
            font-size: 0.85em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .prediction-badge.HOME {{ background: #1a4a2a; color: #60f0a0; border: 1px solid #2a6a3a; }}
        .prediction-badge.AWAY {{ background: #4a1a2a; color: #f060a0; border: 1px solid #6a2a4a; }}
        .prediction-badge.DRAW {{ background: #3a3a0a; color: #f0f060; border: 1px solid #5a5a2a; }}
        
        .confidence {{
            font-size: 0.8em;
            font-weight: 600;
            margin-left: 8px;
            opacity: 0.8;
        }}
        
        .probabilities {{
            display: flex;
            gap: 12px;
            margin-bottom: 24px;
        }}
        
        .prob-bar {{
            flex: 1;
            text-align: center;
        }}
        
        .prob-bar .label {{
            font-size: 0.8em;
            color: #8890b0;
            margin-bottom: 6px;
            font-weight: 500;
        }}
        
        .prob-bar .value {{
            font-size: 1.8em;
            font-weight: 800;
            margin-bottom: 6px;
        }}
        
        .prob-bar.home .value {{ color: #60f0a0; }}
        .prob-bar.draw .value {{ color: #f0e060; }}
        .prob-bar.away .value {{ color: #f060a0; }}
        
        .bar-track {{
            height: 8px;
            background: #1e2445;
            border-radius: 4px;
            overflow: hidden;
        }}
        
        .bar-fill {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s;
        }}
        
        .bar-fill.home {{ background: linear-gradient(90deg, #30a050, #60f0a0); }}
        .bar-fill.draw {{ background: linear-gradient(90deg, #909030, #f0e060); }}
        .bar-fill.away {{ background: linear-gradient(90deg, #a03050, #f060a0); }}
        
        .stats-section {{
            margin-bottom: 16px;
        }}
        
        .stats-section h3 {{
            font-size: 0.85em;
            font-weight: 700;
            color: #e09020;
            padding: 12px 0 6px;
            border-bottom: 1px solid #2a2f4a;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 12px;
        }}
        
        .stats-two-col {{
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            gap: 0;
            align-items: center;
        }}
        
        .stats-col-header {{
            padding: 8px 0;
            font-weight: 700;
            font-size: 1.1em;
            text-align: center;
            border-bottom: 2px solid #2a2f4a;
        }}
        
        .stats-col-header.home {{ color: #60f0a0; border-color: #1a4a2a; }}
        .stats-col-header.away {{ color: #f060a0; border-color: #4a1a2a; }}
        
        .stat-row {{
            display: contents;
        }}
        
        .stat-value-home {{
            text-align: center;
            font-weight: 600;
            font-size: 1.1em;
            color: #c0d0e0;
            padding: 6px 0;
        }}
        
        .stat-name-center {{
            text-align: center;
            color: #6a70a0;
            font-size: 0.78em;
            padding: 6px 12px;
            min-width: 120px;
        }}
        
        .stat-value-away {{
            text-align: center;
            font-weight: 600;
            font-size: 1.1em;
            color: #c0d0e0;
            padding: 6px 0;
        }}
        
        .narrative {{
            background: #0d1030;
            border-left: 3px solid #e09020;
            padding: 14px 18px;
            border-radius: 0 10px 10px 0;
            color: #a0b0d0;
            font-size: 0.9em;
            line-height: 1.5;
            margin-bottom: 16px;
        }}
        
        .model-breakdown {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            align-items: center;
        }}
        
        .model-chip {{
            background: #1a1f3a;
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 0.8em;
            color: #8890b0;
            border: 1px solid #2a2f4a;
        }}
        
        .model-chip span {{
            color: #e09020;
            font-weight: 700;
        }}
        
        .model-legend-toggle {{
            background: none;
            border: 1px solid #3a3f5a;
            color: #6a70a0;
            padding: 4px 12px;
            border-radius: 8px;
            font-size: 0.75em;
            cursor: pointer;
            margin-left: 8px;
        }}
        
        .model-legend-toggle:hover {{
            color: #e09020;
            border-color: #e09020;
        }}
        
        .model-legend {{
            display: none;
            background: #0d1030;
            border: 1px solid #2a2f4a;
            border-radius: 10px;
            padding: 14px 18px;
            margin-top: 12px;
            font-size: 0.8em;
            color: #8890b0;
            line-height: 1.6;
        }}
        
        .model-legend.show {{
            display: block;
        }}
        
        .model-legend strong {{
            color: #e0e0e0;
        }}
        
        .model-legend .legend-elo {{ color: #60f0a0; }}
        .model-legend .legend-stats {{ color: #f0c040; }}
        .model-legend .legend-poisson {{ color: #60a0f0; }}
        
        .combinadas-section {{
            background: linear-gradient(145deg, #151a35 0%, #111530 100%);
            border-radius: 16px;
            padding: 24px 30px;
            margin-bottom: 24px;
            border: 1px solid #2a2f4a;
        }}
        
        .combinadas-section h2 {{
            font-size: 1.3em;
            background: linear-gradient(135deg, #f0c040, #e09020);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 20px;
            text-align: center;
        }}
        
        .combi-row {{
            display: flex;
            gap: 16px;
            margin-bottom: 16px;
        }}
        
        .combi-card {{
            flex: 1;
            background: #0f1430;
            border-radius: 12px;
            padding: 16px;
            border: 1px solid #2a2f4a;
            position: relative;
            overflow: hidden;
        }}
        
        .combi-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
        }}
        
        .combi-card.segura::before {{ background: linear-gradient(90deg, #30a050, #60f0a0); }}
        .combi-card.media::before {{ background: linear-gradient(90deg, #e09020, #f0c040); }}
        .combi-card.sonadora::before {{ background: linear-gradient(90deg, #c03060, #f060a0); }}
        
        .combi-card h3 {{
            font-size: 1em;
            margin-bottom: 4px;
            text-align: center;
        }}
        
        .combi-card.segura h3 {{ color: #60f0a0; }}
        .combi-card.media h3 {{ color: #f0c040; }}
        .combi-card.sonadora h3 {{ color: #f060a0; }}
        
        .combi-card .combi-tagline {{
            font-size: 0.72em;
            color: #6a70a0;
            text-align: center;
            margin-bottom: 12px;
        }}
        
        .combi-stats {{
            display: flex;
            justify-content: space-around;
            margin-bottom: 12px;
            font-size: 0.8em;
        }}
        
        .combi-stat {{
            text-align: center;
        }}
        
        .combi-stat .stat-num {{
            font-size: 1.4em;
            font-weight: 800;
        }}
        
        .combi-card.segura .stat-num {{ color: #60f0a0; }}
        .combi-card.media .stat-num {{ color: #f0c040; }}
        .combi-card.sonadora .stat-num {{ color: #f060a0; }}
        
        .combi-stat .stat-label {{
            color: #6a70a0;
            font-size: 0.85em;
            margin-top: 2px;
        }}
        
        .combi-legs {{
            font-size: 0.78em;
            color: #a0b0d0;
        }}
        
        .combi-leg {{
            padding: 6px 0;
            border-bottom: 1px solid #1a1f3a;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .combi-leg:last-child {{
            border-bottom: none;
        }}
        
        .combi-leg-num {{
            background: #1e2445;
            color: #8890b0;
            width: 22px; height: 22px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8em;
            font-weight: 700;
            flex-shrink: 0;
        }}
        
        .combi-payout {{
            text-align: center;
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px solid #1a1f3a;
            font-size: 0.75em;
            color: #7880a0;
        }}
        
        .combi-payout strong {{
            color: #e0e0e0;
            font-size: 1.15em;
        }}
        
        .footer {{
            text-align: center;
            padding: 30px;
            color: #5a6080;
            font-size: 0.8em;
        }}
        
        .footer a {{
            color: #e09020;
            text-decoration: none;
        }}
        
        .round-badge {{
            background: #e09020;
            color: #0a0e27;
            padding: 3px 12px;
            border-radius: 10px;
            font-size: 0.75em;
            font-weight: 700;
            text-transform: uppercase;
        }}
        
        .key-stats {{
            font-size: 0.8em;
            color: #7880a0;
            margin-bottom: 6px;
            font-weight: 500;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏆 Mundial 2026 — Octavos de Final</h1>
            <div class="subtitle">Predicciones basadas en 72 partidos · 48 equipos · Estadísticas reales de Sofascore</div>
            <div class="badge">📅 29 de junio de 2026 · 3 partidos</div>
        </div>
"""
    
    for r in predictions:
        p = r['probabilities']
        elo = r['elo']
        eg = r['expected_goals']
        ts = r['team_stats']
        
        # Color del badge
        badge_class = r['prediction']
        
        # Predicción en texto
        if r['prediction'] == 'HOME':
            pred_text = f"Gana {r['home_team']}"
        elif r['prediction'] == 'AWAY':
            pred_text = f"Gana {r['away_team']}"
        else:
            pred_text = "Empate"
        
        html += f"""
        <div class="match-card">
            <div class="match-header">
                <div class="match-time">⏰ {r['time']}</div>
                <div class="teams">
                    <span class="team">{r['home_team']}</span>
                    <span class="vs">vs</span>
                    <span class="team">{r['away_team']}</span>
                </div>
                <div>
                    <span class="prediction-badge {r['prediction']}">{pred_text}<span class="confidence">{r['confidence']}</span></span>
                </div>
            </div>
            
            <div class="probabilities">
                <div class="prob-bar home">
                    <div class="label">{r['home_team']}</div>
                    <div class="value">{p['home']}%</div>
                    <div class="bar-track"><div class="bar-fill home" style="width:{p['home']}%"></div></div>
                </div>
                <div class="prob-bar draw">
                    <div class="label">Empate</div>
                    <div class="value">{p['draw']}%</div>
                    <div class="bar-track"><div class="bar-fill draw" style="width:{p['draw']}%"></div></div>
                </div>
                <div class="prob-bar away">
                    <div class="label">{r['away_team']}</div>
                    <div class="value">{p['away']}%</div>
                    <div class="bar-track"><div class="bar-fill away" style="width:{p['away']}%"></div></div>
                </div>
            </div>
            
            <div class="stats-section">
                <h3>📊 ESTADÍSTICAS CLAVE</h3>
                <div class="stats-two-col">
                    <div class="stats-col-header home">{r['home_team']}</div>
                    <div></div>
                    <div class="stats-col-header away">{r['away_team']}</div>
                    
                    <div class="stat-value-home">{eg['home']}</div>
                    <div class="stat-name-center">Goles esperados</div>
                    <div class="stat-value-away">{eg['away']}</div>
                    
                    <div class="stat-value-home">{elo['home']}</div>
                    <div class="stat-name-center">Rating Elo</div>
                    <div class="stat-value-away">{elo['away']}</div>
                    
                    <div class="stat-value-home">{ts['home']['avg_goals_for']:.1f} ⚽</div>
                    <div class="stat-name-center">Goles/partido</div>
                    <div class="stat-value-away">{ts['away']['avg_goals_for']:.1f} ⚽</div>
                    
                    <div class="stat-value-home">{ts['home']['wins']}W {ts['home']['draws']}D {ts['home']['losses']}L</div>
                    <div class="stat-name-center">Récord Mundial</div>
                    <div class="stat-value-away">{ts['away']['wins']}W {ts['away']['draws']}D {ts['away']['losses']}L</div>
"""
        
        # Top stats
        for s in r['top_stats'][:3]:
            label = engine._stat_label(s['key'])
            html += f"""
                    <div class="stat-value-home">{s['home']:.1f}</div>
                    <div class="stat-name-center">{label}</div>
                    <div class="stat-value-away">{s['away']:.1f}</div>"""
        
        html += f"""
                </div>
            </div>
            
            <div class="narrative">📊 {r['narrative']}</div>
            
            <div class="model-breakdown">
                <div class="model-chip">Elo: <span>{r['model_breakdown']['elo']}% local</span></div>
                <div class="model-chip">Estadístico: <span>{r['model_breakdown']['statistical']}% local</span></div>
                <div class="model-chip">Poisson: <span>{r['model_breakdown']['poisson']}% local</span></div>
                <button class="model-legend-toggle" onclick="this.nextElementSibling.classList.toggle('show');this.textContent=this.textContent=='¿Qué es esto?'?'Ocultar':'¿Qué es esto?'">¿Qué es esto?</button>
                <div class="model-legend">
                    <strong>Desglose de modelos:</strong> cada chip muestra qué porcentaje de victoria local predice cada modelo por separado. Luego el sistema los <strong>mezcla ponderadamente</strong> (40% Elo + 25% Stats + 25% Poisson + 10% forma) para dar la predicción final que ves arriba.<br><br>
                    <span class="legend-elo">● <strong>Elo:</strong></span> rating histórico basado en resultados y diferencia de goles. Mide la fuerza relativa "teórica" de cada selección.<br>
                    <span class="legend-stats">● <strong>Estadístico:</strong></span> compara TODAS las stats reales del torneo (xG, tiros, posesión, córners, duelos, pases...). El más "basado en datos duros".<br>
                    <span class="legend-poisson">● <strong>Poisson:</strong></span> modelo de goles esperados. Calcula la probabilidad de cada marcador posible según los goles que marcan y reciben ambos equipos. Suele ser el más conservador.
                </div>
            </div>
        </div>
"""
    
    html += f"""
        <div class="combinadas-section">
            <h2>🎰 COMBINADAS RECOMENDADAS</h2>
            <div class="combi-row">
                <div class="combi-card segura">
                    <h3>🟢 SEGURA</h3>
                    <div class="combi-tagline">3 over 1.5 — casi regalado</div>
                    <div class="combi-stats">
                        <div class="combi-stat">
                            <div class="stat-num">60.6%</div>
                            <div class="stat-label">Probabilidad</div>
                        </div>
                        <div class="combi-stat">
                            <div class="stat-num">2.22</div>
                            <div class="stat-label">Cuota bet365 🔥</div>
                        </div>
                    </div>
                    <div class="combi-legs">
                        <div class="combi-leg"><span class="combi-leg-num">1</span> Brazil vs Japan: +1.5 goles</div>
                        <div class="combi-leg"><span class="combi-leg-num">2</span> Germany vs Paraguay: +1.5 goles</div>
                        <div class="combi-leg"><span class="combi-leg-num">3</span> Netherlands vs Morocco: +1.5 goles</div>
                    </div>
                    <div class="combi-payout">💶 Con <strong>10€</strong> → <strong>~22.20€</strong> &nbsp; <span style="color:#2ecc71">EV +34.5% 🟢</span></div>
                </div>
                <div class="combi-card media">
                    <h3>🟠 MEDIA</h3>
                    <div class="combi-tagline">Valor esperado positivo 📈</div>
                    <div class="combi-stats">
                        <div class="combi-stat">
                            <div class="stat-num">25.6%</div>
                            <div class="stat-label">Probabilidad</div>
                        </div>
                        <div class="combi-stat">
                            <div class="stat-num">4.91</div>
                            <div class="stat-label">Cuota bet365</div>
                        </div>
                    </div>
                    <div class="combi-legs">
                        <div class="combi-leg"><span class="combi-leg-num">1</span> Brazil vs Japan: Over 2.5 goles (@2.10 · prob 58%)</div>
                        <div class="combi-leg"><span class="combi-leg-num">2</span> Germany GANA (@1.30 · prob real 62%)</div>
                        <div class="combi-leg"><span class="combi-leg-num">3</span> Netherlands vs Morocco: AMBOS marcan (@1.80 · prob 72%)</div>
                    </div>
                    <div class="combi-payout">💶 Con <strong>10€</strong> → <strong>~49.10€</strong></div>
                </div>
                <div class="combi-card sonadora">
                    <h3>🔴 SOÑADORA</h3>
                    <div class="combi-tagline">3 batacazos... si suena 🚀</div>
                    <div class="combi-stats">
                        <div class="combi-stat">
                            <div class="stat-num">5.9%</div>
                            <div class="stat-label">Probabilidad</div>
                        </div>
                        <div class="combi-stat">
                            <div class="stat-num">67.09</div>
                            <div class="stat-label">Cuota bet365</div>
                        </div>
                    </div>
                    <div class="combi-legs">
                        <div class="combi-leg"><span class="combi-leg-num">1</span> Japan GANA (@5.25)</div>
                        <div class="combi-leg"><span class="combi-leg-num">2</span> Paraguay o Empate (@3.55 · prob 38%)</div>
                        <div class="combi-leg"><span class="combi-leg-num">3</span> Morocco GANA (@3.60)</div>
                    </div>
                    <div class="combi-payout">💶 Con <strong>10€</strong> → <strong>~670.90€</strong></div>
                </div>
            </div>
        </div>

        <div class="footer">
            ⚡ Sistema de predicción basado en modelo compuesto (Elo + Estadísticas + Goles esperados)<br>
            Datos de Sofascore · 72 partidos analizados · 48 selecciones · {len(engine.team_stats)} con estadísticas completas<br>
            <small>Generado el 29 de junio de 2026 · Solo con fines informativos</small>
        </div>
    </div>
</body>
</html>"""
    
    # Guardar y abrir
    out_path = Path(__file__).parent / "index.html"
    with open(out_path, 'w') as f:
        f.write(html)
    
    # Abrir en navegador
    webbrowser.open(f"file://{out_path.absolute()}")
    
    print(f"✅ Web generada: {out_path}")
    print(f"   Tamaño: {len(html):,} bytes")
    print(f"   Partidos: {len(predictions)}")
    
    return out_path

if __name__ == '__main__':
    generate_web()
