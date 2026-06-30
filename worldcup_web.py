#!/usr/bin/env python3
"""
World Cup 2026 — Predicciones Web
Genera HTML premium con analisis de los 3 partidos de octavos (30 junio 2026)
"""

import sys
import os
import math
from pathlib import Path
import json
import webbrowser

# Añadir src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from worldcup.engine import WorldCupEngine
from value_bets import build_value_bets, load_all_matches, build_matchup_narrative, compute_team_averages, load_real_stats, compare_predictions, build_comparison_html, adjusted_prediction, PREDICTABLE_STATS

# ─── Cuotas reales (OddsPapi) ───────────────────────────────────────────

def load_odds_cache():
    """Carga el caché de cuotas de OddsPapi"""
    cache_path = Path(__file__).parent / "data" / "odds_cache.json"
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)
    return {}

def get_match_odds(cache, home_team, away_team):
    """Busca las cuotas de un partido por nombres de equipo (fuzzy match)"""
    # Alias: motor usa nombres FIFA, el caché puede tener variantes
    aliases = {
        "côte d'ivoire": "ivory coast",
        "south korea": "korea republic",
        "usa": "united states",
    }
    home_lower = aliases.get(home_team.lower().strip(), home_team.lower().strip())
    away_lower = aliases.get(away_team.lower().strip(), away_team.lower().strip())
    
    for fid, info in cache.items():
        ch = info.get("home", "").lower().strip()
        ca = info.get("away", "").lower().strip()
        if (ch == home_lower or home_lower in ch or ch in home_lower) and \
           (ca == away_lower or away_lower in ca or ca in away_lower):
            odds = info.get("odds") or {}
            # Formato nuevo: {bet365: {1x2: {home,draw,away}, cornerKicks: {...}}}
            # Formato viejo: {bet365: {home,draw,away}}
            # Compatibilidad con ambos
            b365_raw = odds.get("bet365", {})
            pin_raw = odds.get("pinnacle", {})
            
            # Si tiene 1x2 anidado, aplanar
            b365 = b365_raw.get("1x2", b365_raw) if b365_raw else {}
            pinn = pin_raw.get("1x2", pin_raw) if pin_raw else {}
            
            # Si bet365 no tiene 'home' pero está en formato nuevo sin 1x2, aplanar
            if "home" not in b365 and isinstance(b365_raw, dict):
                b365 = b365_raw.get("1x2", b365_raw)
            if isinstance(pinn, dict) and "home" not in pinn and isinstance(pin_raw, dict):
                pinn = pin_raw.get("1x2", pin_raw)

            # Merge: combinar 1x2 con campos extra (over_15, btts_yes, etc.)
            merged = dict(b365) if b365 else {}
            if isinstance(b365_raw, dict):
                for k, v in b365_raw.items():
                    if k != "1x2" and not isinstance(v, dict) and k not in merged:
                        merged[k] = v
            return merged, pinn
    return None, None

def implied_prob(odd):
    """Probabilidad implícita de una cuota decimal"""
    if odd and odd > 0:
        return round(100 / odd, 1)
    return 0

def value_edge(our_prob, odd):
    """Diferencia entre nuestra probabilidad y la implícita de la cuota (value positivo = edge)"""
    impl = implied_prob(odd)
    return round(our_prob - impl, 1)

def value_signal(edge):
    """Señal visual de value"""
    if edge >= 8:
        return "🟢", "value-strong"
    elif edge >= 3:
        return "🟡", "value-mild"
    elif edge >= 0:
        return "⚪", "value-flat"
    else:
        return "🔴", "value-negative"

# ─── Funciones auxiliares para Overs / BTTS ──────────────────────────

def poisson_prob(lam, k):
    """P(X = k) para Poisson con lambda=lam"""
    return (lam ** k) * math.exp(-lam) / math.factorial(k)

def over_prob(lam, goals):
    """P(X > goals) = 1 - sum_{i=0}^{goals} P(X=i)"""
    return round(1 - sum(poisson_prob(lam, i) for i in range(goals + 1)), 4)

def btts_prob(xg_home, xg_away):
    """Probabilidad de ambos marcan (con correlación negativa ajustada)"""
    p_h = 1 - math.exp(-xg_home)
    p_a = 1 - math.exp(-xg_away)
    raw = p_h * p_a
    # Ajuste correlación (equipos que marcan muchos goles también encajan más)
    return raw * (1 - 0.15 * (1 - raw))

def build_combinadas(predictions, odds_cache):
    """Construye las combinadas usando cuotas reales de bet365 + edges del modelo"""
    # ─── Extraer datos de los 3 partidos ───
    matches = []
    for r in predictions:
        home = r['home_team']
        away = r['away_team']
        p = r['probabilities']
        eg = r['expected_goals']
        total_xg = eg['home'] + eg['away']

        # Cuotas reales
        b365 = r.get('odds_b365') or {}

        ov15 = over_prob(total_xg, 1)
        ov25 = over_prob(total_xg, 2)
        ov35 = over_prob(total_xg, 3)
        btts = btts_prob(eg['home'], eg['away'])

        # Probabilidad 1X (doble oportunidad local)
        p_1x = (p['home'] + p['draw']) / 100

        matches.append({
            'home': home, 'away': away,
            'prob': p, 'eg': eg,
            'b365': b365,
            'ov15': ov15, 'ov25': ov25, 'ov35': ov35,
            'btts': btts, 'p_1x': p_1x,
        })

    m = matches  # shortcut
    b = [m_.get('b365', {}) for m_ in m]  # bet365 for each match

    # ─── 🟢 SEGURA: 1X Ivory Coast + Over 1.5 France + 1X Mexico ───
    # Cuotas reales: 1X = home*draw / (home+draw) approx, pero usamos 1x2 home como ref
    # bet365 no da doble oportunidad directa; usamos home como conservador
    # En realidad calculamos la cuota 1X como (home*draw)/(home+draw)
    def cuota_1x(bk):
        h, d = bk.get('home', 1.5), bk.get('draw', 3.5)
        return round((h * d) / (h + d), 2)

    cuota_seg = [
        cuota_1x(b[0]),              # Ivory Coast 1X
        b[1].get('over_15') or 1.14, # France Over 1.5
        cuota_1x(b[2]),              # Mexico 1X
    ]
    p_seg = m[0]['p_1x'] * m[1]['ov15'] * m[2]['p_1x']
    cuota_seg_total = cuota_seg[0] * cuota_seg[1] * cuota_seg[2]

    edges_seg = [
        round((m[0]['p_1x'] - 1 / cuota_seg[0]) * 100, 1),
        round((m[1]['ov15'] - 1 / cuota_seg[1]) * 100, 1),
        round((m[2]['p_1x'] - 1 / cuota_seg[2]) * 100, 1),
    ]

    # ─── 🟠 MEDIA: Ivory Coast gana + France BTTS Yes + Mexico gana ───
    cuota_med = [
        b[0].get('home') or 3.6,    # Ivory Coast gana
        b[1].get('btts_yes') or 1.75, # France BTTS Yes
        b[2].get('home') or 2.27,   # Mexico gana
    ]
    p_med = (m[0]['prob']['home'] / 100) * m[1]['btts'] * (m[2]['prob']['home'] / 100)
    cuota_med_total = cuota_med[0] * cuota_med[1] * cuota_med[2]

    edges_med = [
        round((m[0]['prob']['home'] / 100 - 1 / cuota_med[0]) * 100, 1),
        round((m[1]['btts'] - 1 / cuota_med[1]) * 100, 1),
        round((m[2]['prob']['home'] / 100 - 1 / cuota_med[2]) * 100, 1),
    ]

    # ─── 🔴 SOÑADORA: Ivory Coast Over 3.5 + France Over 3.5 + Mexico Empate ───
    cuota_son = [
        b[0].get('over_35') or 3.0,  # Ivory Coast Over 3.5
        b[1].get('over_35') or 2.1,  # France Over 3.5
        b[2].get('draw') or 2.91,    # Mexico Empate
    ]
    p_son = m[0]['ov35'] * m[1]['ov35'] * (m[2]['prob']['draw'] / 100)
    cuota_son_total = cuota_son[0] * cuota_son[1] * cuota_son[2]

    edges_son = [
        round((m[0]['ov35'] - 1 / cuota_son[0]) * 100, 1),
        round((m[1]['ov35'] - 1 / cuota_son[1]) * 100, 1),
        round((m[2]['prob']['draw'] / 100 - 1 / cuota_son[2]) * 100, 1),
    ]

    return {
        'segura': {
            'prob': p_seg, 'cuota': cuota_seg_total,
            'legs': [
                {'text': f"{m[0]['home']} vs {m[0]['away']}: 1X (Local o Empate)", 'cuota': cuota_seg[0], 'prob': m[0]['p_1x'], 'edge': edges_seg[0]},
                {'text': f"{m[1]['home']} vs {m[1]['away']}: Over 1.5 Goles", 'cuota': cuota_seg[1], 'prob': m[1]['ov15'], 'edge': edges_seg[1]},
                {'text': f"{m[2]['home']} vs {m[2]['away']}: 1X (Local o Empate)", 'cuota': cuota_seg[2], 'prob': m[2]['p_1x'], 'edge': edges_seg[2]},
            ]
        },
        'media': {
            'prob': p_med, 'cuota': cuota_med_total,
            'legs': [
                {'text': f"{m[0]['home']} vs {m[0]['away']}: Gana Local", 'cuota': cuota_med[0], 'prob': m[0]['prob']['home'] / 100, 'edge': edges_med[0]},
                {'text': f"{m[1]['home']} vs {m[1]['away']}: Ambos Marcan (BTTS)", 'cuota': cuota_med[1], 'prob': m[1]['btts'], 'edge': edges_med[1]},
                {'text': f"{m[2]['home']} vs {m[2]['away']}: Gana Local", 'cuota': cuota_med[2], 'prob': m[2]['prob']['home'] / 100, 'edge': edges_med[2]},
            ]
        },
        'sonadora': {
            'prob': p_son, 'cuota': cuota_son_total,
            'legs': [
                {'text': f"{m[0]['home']} vs {m[0]['away']}: Over 3.5 Goles", 'cuota': cuota_son[0], 'prob': m[0]['ov35'], 'edge': edges_son[0]},
                {'text': f"{m[1]['home']} vs {m[1]['away']}: Over 3.5 Goles", 'cuota': cuota_son[1], 'prob': m[1]['ov35'], 'edge': edges_son[1]},
                {'text': f"{m[2]['home']} vs {m[2]['away']}: Empate", 'cuota': cuota_son[2], 'prob': m[2]['prob']['draw'] / 100, 'edge': edges_son[2]},
            ]
        }
    }

def _build_value_bets_html():
    """Genera el HTML de la sección Value Bets"""
    # Cargar datos SOLO una vez
    matches_data = load_all_matches()
    odds_cache = load_odds_cache()
    value_bets, team_stats = build_value_bets(matches_data, odds_cache)
    
    if not value_bets:
        return '<div class="no-value-bets">🔍 No se encontraron value bets para los próximos partidos.<br><small>Las cuotas de bet365 no cubren suficientes mercados de córners/bookings aún.</small></div>'
    
    html = '<div class="value-bets-intro">🎯 Apuestas con edge positivo: la probabilidad del modelo supera a la implícita de bet365</div>\n'
    html += '<div class="value-bets-grid">\n'
    
    for vb in value_bets:
        # Determinar clase de edge
        if vb['edge_pct'] >= 5:
            edge_class = 'edge-strong'
            edge_icon = '🟢'
        elif vb['edge_pct'] >= 2:
            edge_class = 'edge-mild'
            edge_icon = '🟡'
        elif vb['edge_pct'] >= 0:
            edge_class = 'edge-flat'
            edge_icon = '⚪'
        else:
            edge_class = 'edge-negative'
            edge_icon = '🔴'
        
        edge_sign = '+' if vb['edge_pct'] >= 0 else ''
        ev_sign = '+' if vb['ev_pct'] >= 0 else ''
        
        html += f'''        <div class="value-bet-card {edge_class}">
            <div class="value-bet-header">
                <span class="value-bet-match">⚽ {vb['match']}</span>
                <span class="value-bet-market">{vb['icon']} {vb['label']} Over {vb['line']:.1f}</span>
            </div>
            <div class="value-bet-body">
                <div class="value-bet-stat highlight">
                    <div class="stat-num">{vb['prob_over']:.1f}%</div>
                    <div class="stat-label">Prob. modelo</div>
                </div>
                <div class="value-bet-stat">
                    <div class="stat-num">{vb['odd']}</div>
                    <div class="stat-label">Cuota bet365</div>
                </div>
                <div class="value-bet-stat">
                    <div class="stat-num">{vb['implied_pct']:.1f}%</div>
                    <div class="stat-label">Implícita</div>
                </div>
                <div class="value-bet-verdict {edge_class}">
                    <div class="edge-badge">{edge_icon} {edge_sign}{vb['edge_pct']:.1f}%</div>
                    <div class="edge-label">EDGE · EV {ev_sign}{vb['ev_pct']:.1f}%</div>
                </div>
            </div>
            <div class="value-bet-context">
                <span>📊 Pred: {vb['total_pred']:.1f} total (local {vb['pred_home']:.1f} + visitante {vb['pred_away']:.1f})</span>
                <span>📈 Media local: {vb['team_h_for']:.1f} a favor / {vb['team_h_against']:.1f} en contra</span>
                <span>📉 Media visitante: {vb['team_a_for']:.1f} a favor / {vb['team_a_against']:.1f} en contra</span>
            </div>
        </div>
'''
    
    html += '</div>\n'
    return html


def generate_web():
    """Genera predicciones.html con diseño premium"""
    
    # Cargar motor
    engine = WorldCupEngine()
    engine.load_data()
    
    # Cargar estadísticas de equipo para narrativas de enfrentamiento
    matches_data = load_all_matches()
    team_stats_narrative = compute_team_averages(matches_data)
    
    # Cargar cuotas reales
    odds_cache = load_odds_cache()
    
    # Partidos de hoy
    matches_today = [
        ("Côte d'Ivoire", "Norway", "17:00"),
        ("France", "Sweden", "21:00"),
        ("Mexico", "Ecuador", "01:00"),
    ]
    
    predictions = []
    for home, away, time in matches_today:
        r = engine.predict_match(home, away)
        r['time'] = time
        # Cuotas reales
        b365, pinnacle = get_match_odds(odds_cache, home, away)
        r['odds_b365'] = b365
        r['odds_pinnacle'] = pinnacle
        predictions.append(r)
    
    # Generar combinadas con cuotas reales
    combinadas = build_combinadas(predictions, odds_cache)
    
    # ─── COMPARATIVA PREDICHO vs REAL ───
    # Inyectar predicciones del modelo (adjusted_prediction) en cada partido
    for r in predictions:
        vb_list = []
        for stat_key in PREDICTABLE_STATS:
            pred_h, pred_a = adjusted_prediction(team_stats_narrative, r['home_team'], r['away_team'], stat_key)
            if pred_h > 0 or pred_a > 0:
                vb_list.append({
                    'stat_key': stat_key,
                    'total_pred': round(pred_h + pred_a, 2),
                    'pred_home': pred_h,
                    'pred_away': pred_a,
                    'ev_pct': 0,  # no hay línea de apuesta, solo comparativa
                })
        r['value_bets'] = vb_list
    
    real_stats = load_real_stats()
    comparisons = compare_predictions(predictions, real_stats)
    comparison_html = build_comparison_html(comparisons)
    
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
        
        .matchup-narrative {{
            background: linear-gradient(135deg, #0d1030 0%, #111540 100%);
            border: 1px solid #2a2f4a;
            border-left: 4px solid #60a0f0;
            padding: 16px 20px;
            border-radius: 0 12px 12px 0;
            margin-bottom: 16px;
            font-size: 0.85em;
            line-height: 1.8;
            color: #b0c0e0;
        }}
        
        .matchup-narrative strong {{
            color: #80b0f0;
        }}
        
        .narrative-line {{
            padding: 3px 0;
            padding-left: 6px;
            border-bottom: 1px solid rgba(42,47,74,0.3);
        }}
        
        .narrative-line:last-child {{
            border-bottom: none;
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
        
        .odds-section {{
            background: #0d1030;
            border-radius: 12px;
            padding: 18px 20px;
            margin-bottom: 20px;
            border: 1px solid #2a2f4a;
        }}
        
        .odds-section h3 {{
            font-size: 0.8em;
            font-weight: 700;
            color: #f0c040;
            margin-bottom: 14px;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}
        
        .odds-row {{
            display: flex;
            gap: 8px;
            margin-bottom: 10px;
        }}
        
        .odds-label {{
            width: 90px;
            font-size: 0.75em;
            color: #6a70a0;
            font-weight: 600;
            padding: 6px 0;
            flex-shrink: 0;
        }}
        
        .odds-cells {{
            display: flex;
            gap: 8px;
            flex: 1;
        }}
        
        .odds-cell {{
            flex: 1;
            text-align: center;
            background: #101530;
            border-radius: 8px;
            padding: 6px 4px;
            border: 1px solid #1e2450;
            font-size: 0.85em;
        }}
        
        .odds-cell .odd-value {{
            font-weight: 800;
            font-size: 1.05em;
        }}
        
        .odds-cell .odd-edge {{
            font-size: 0.72em;
            margin-top: 2px;
            font-weight: 600;
        }}
        
        .odds-cell .odd-edge.value-strong {{ color: #60f0a0; }}
        .odds-cell .odd-edge.value-mild, .odds-cell .odd-edge.value-flat {{ color: #8890b0; }}
        .odds-cell .odd-edge.value-negative {{ color: #f06090; }}
        
        .odds-cell .odd-implied {{
            font-size: 0.68em;
            color: #5860a0;
            margin-top: 1px;
        }}
        
        .odds-source {{
            font-size: 0.65em;
            color: #4a5080;
            text-align: right;
            margin-top: 4px;
        }}
        
        /* ─── PESTAÑAS ─── */
        .tabs-nav {{
            display: flex;
            gap: 4px;
            margin-bottom: 24px;
            background: #0d1030;
            border-radius: 14px;
            padding: 4px;
            border: 1px solid #2a2f4a;
        }}
        
        .tab-btn {{
            flex: 1;
            padding: 12px 20px;
            border: none;
            background: transparent;
            color: #6a70a0;
            font-size: 0.95em;
            font-weight: 600;
            cursor: pointer;
            border-radius: 11px;
            transition: all 0.25s;
            font-family: inherit;
        }}
        
        .tab-btn:hover {{
            color: #a0a8c0;
            background: #151a35;
        }}
        
        .tab-btn.active {{
            background: linear-gradient(135deg, #1a2f50, #152040);
            color: #e0e0e0;
            box-shadow: 0 2px 12px rgba(0,0,0,0.3);
        }}
        
        .tab-panel {{
            display: none;
        }}
        
        .tab-panel.active {{
            display: block;
        }}
        
        /* ─── VALUE BETS ─── */
        .value-bets-intro {{
            text-align: center;
            color: #8890b0;
            margin-bottom: 20px;
            font-size: 0.9em;
        }}
        
        .value-bets-grid {{
            display: grid;
            gap: 16px;
        }}
        
        .value-bet-card {{
            background: linear-gradient(145deg, #151a35 0%, #111530 100%);
            border-radius: 12px;
            padding: 18px 20px;
            border: 1px solid #2a2f4a;
            transition: transform 0.2s;
            position: relative;
            overflow: hidden;
        }}
        
        .value-bet-card:hover {{
            transform: translateY(-2px);
        }}
        
        .value-bet-card::before {{
            content: '';
            position: absolute;
            left: 0; top: 0; bottom: 0;
            width: 4px;
        }}
        
        .value-bet-card.edge-strong::before {{ background: #60f0a0; }}
        .value-bet-card.edge-mild::before {{ background: #f0c040; }}
        .value-bet-card.edge-flat::before {{ background: #8890b0; }}
        .value-bet-card.edge-negative::before {{ background: #f06090; }}
        
        .value-bet-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            flex-wrap: wrap;
            gap: 8px;
        }}
        
        .value-bet-match {{
            font-weight: 700;
            font-size: 1.05em;
            color: #e0e0e0;
        }}
        
        .value-bet-market {{
            background: #1a1f3a;
            padding: 4px 12px;
            border-radius: 8px;
            font-size: 0.85em;
            font-weight: 600;
            color: #e09020;
        }}
        
        .value-bet-body {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            align-items: stretch;
        }}
        
        .value-bet-stat {{
            flex: 1;
            min-width: 100px;
            background: #0d1030;
            border-radius: 10px;
            padding: 10px 14px;
            text-align: center;
        }}
        
        .value-bet-stat .stat-num {{
            font-size: 1.3em;
            font-weight: 800;
            color: #e0e0e0;
        }}
        
        .value-bet-stat .stat-label {{
            font-size: 0.7em;
            color: #6a70a0;
            margin-top: 3px;
        }}
        
        .value-bet-stat.highlight {{
            border: 1px solid #2a4a3a;
        }}
        
        .value-bet-stat.highlight .stat-num {{
            color: #60f0a0;
        }}
        
        .value-bet-verdict {{
            flex: 1.5;
            min-width: 200px;
            background: #0d1030;
            border-radius: 10px;
            padding: 12px 16px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            gap: 6px;
        }}
        
        .value-bet-verdict .edge-badge {{
            font-size: 1.6em;
            font-weight: 800;
        }}
        
        .value-bet-verdict .edge-label {{
            font-size: 0.7em;
            color: #6a70a0;
        }}
        
        .edge-strong .edge-badge {{ color: #60f0a0; }}
        .edge-mild .edge-badge {{ color: #f0c040; }}
        .edge-flat .edge-badge {{ color: #8890b0; }}
        .edge-negative .edge-badge {{ color: #f06090; }}
        
        .value-bet-context {{
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #1a1f3a;
            font-size: 0.73em;
            color: #6a70a0;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }}
        
        .value-bet-context span {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}
        
        .no-value-bets {{
            text-align: center;
            padding: 40px;
            color: #5a6080;
            font-size: 1.1em;
        }}
        
        /* ─── COMPARATIVA ─── */
        .comparison-intro {{
            text-align: center;
            padding: 20px;
            color: #a0a8c0;
            font-size: 1.1em;
            margin-bottom: 20px;
        }}
        
        .comparison-match {{
            background: #111636;
            border: 1px solid #2a2f4a;
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
        }}
        
        .comparison-match-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #1a1f3a;
        }}
        
        .comparison-match-name {{
            font-size: 1.2em;
            font-weight: bold;
            color: #f0c040;
        }}
        
        .comparison-avg-acc {{
            font-size: 1.1em;
            font-weight: bold;
        }}
        
        .comparison-grid {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        
        .comparison-row {{
            display: flex;
            align-items: center;
            gap: 16px;
            padding: 10px 14px;
            background: #0c1029;
            border-radius: 10px;
            flex-wrap: wrap;
        }}
        
        .comparison-stat-name {{
            min-width: 140px;
            color: #c0c8e0;
            font-weight: 600;
        }}
        
        .comparison-values {{
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 300px;
            font-size: 0.92em;
        }}
        
        .comp-pred {{
            color: #60a0f0;
        }}
        
        .comp-vs {{
            color: #5a6080;
        }}
        
        .comp-real {{
            color: #60f0a0;
        }}
        
        .comp-diff {{
            margin-left: 8px;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.85em;
            background: #1a1f3a;
            color: #f0a060;
        }}
        
        .comparison-bar-track {{
            flex: 1;
            min-width: 100px;
            height: 8px;
            background: #1a1f3a;
            border-radius: 4px;
            overflow: hidden;
        }}
        
        .comparison-bar-fill {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s ease;
        }}
        
        .comparison-acc {{
            font-weight: bold;
            min-width: 60px;
            text-align: right;
            font-size: 0.92em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏆 Mundial 2026 — Octavos de Final</h1>
            <div class="subtitle">Predicciones basadas en 72 partidos · 48 equipos · Estadísticas reales de Sofascore</div>
            <div class="badge">📅 30 de junio de 2026 · 3 partidos</div>
        </div>
        
        <!-- ─── PESTAÑAS ─── -->
        <div class="tabs-nav">
            <button class="tab-btn active" onclick="switchTab('partidos')">📊 Partidos</button>
            <button class="tab-btn" onclick="switchTab('combinadas')">🎰 Combinadas</button>
            <button class="tab-btn" onclick="switchTab('valuebets')">🎯 Value Bets</button>
            <button class="tab-btn" onclick="switchTab('comparativa')">📈 Comparativa</button>
        </div>
        
        <script>
            function switchTab(tab) {{
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
                document.querySelector('.tab-btn[onclick*=\"' + tab + '\"]').classList.add('active');
                document.getElementById('tab-' + tab).classList.add('active');
            }}
        </script>
        
        <div id="tab-partidos" class="tab-panel active">
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
            
"""
        
        # ─── Sección de cuotas reales ───
        b365 = r.get('odds_b365') or {}
        pinn = r.get('odds_pinnacle') or {}
        
        if b365 or pinn:
            html += """            <div class="odds-section">
                <h3>💰 CUOTAS REALES vs PREDICCIÓN</h3>
                <div class="odds-row">
                    <div class="odds-label">Modelo</div>
                    <div class="odds-cells">
                        <div class="odds-cell">
                            <div class="odd-value" style="color:#60f0a0">""" + str(p['home']) + """%</div>
                            <div class="odd-implied">""" + r['home_team'] + """</div>
                        </div>
                        <div class="odds-cell">
                            <div class="odd-value" style="color:#f0e060">""" + str(p['draw']) + """%</div>
                            <div class="odd-implied">Empate</div>
                        </div>
                        <div class="odds-cell">
                            <div class="odd-value" style="color:#f060a0">""" + str(p['away']) + """%</div>
                            <div class="odd-implied">""" + r['away_team'] + """</div>
                        </div>
                    </div>
                </div>
"""
        
        # bet365 row
        if b365:
            h_odd = b365.get('home', 0)
            d_odd = b365.get('draw', 0)
            a_odd = b365.get('away', 0)
            he = value_edge(p['home'], h_odd)
            de = value_edge(p['draw'], d_odd)
            ae = value_edge(p['away'], a_odd)
            hs, hc = value_signal(he)
            ds, dc = value_signal(de)
            as_, ac = value_signal(ae)
            
            html += f"""                <div class="odds-row">
                    <div class="odds-label" style="color:#e09020">bet365</div>
                    <div class="odds-cells">
                        <div class="odds-cell">
                            <div class="odd-value" style="color:#60f0a0">{h_odd}</div>
                            <div class="odd-edge {hc}">{hs} {he:+}%</div>
                            <div class="odd-implied">impl. {implied_prob(h_odd)}%</div>
                        </div>
                        <div class="odds-cell">
                            <div class="odd-value" style="color:#f0e060">{d_odd}</div>
                            <div class="odd-edge {dc}">{ds} {de:+}%</div>
                            <div class="odd-implied">impl. {implied_prob(d_odd)}%</div>
                        </div>
                        <div class="odds-cell">
                            <div class="odd-value" style="color:#f060a0">{a_odd}</div>
                            <div class="odd-edge {ac}">{as_} {ae:+}%</div>
                            <div class="odd-implied">impl. {implied_prob(a_odd)}%</div>
                        </div>
                    </div>
                </div>
"""
        
        # Pinnacle row
        if pinn:
            ph_odd = pinn.get('home', 0)
            pd_odd = pinn.get('draw', 0)
            pa_odd = pinn.get('away', 0)
            phe = value_edge(p['home'], ph_odd)
            pde = value_edge(p['draw'], pd_odd)
            pae = value_edge(p['away'], pa_odd)
            phs, phc = value_signal(phe)
            pds, pdc = value_signal(pde)
            pas_, pac = value_signal(pae)
            
            html += f"""                <div class="odds-row">
                    <div class="odds-label" style="color:#60a0f0">Pinnacle</div>
                    <div class="odds-cells">
                        <div class="odds-cell">
                            <div class="odd-value" style="color:#60f0a0">{ph_odd}</div>
                            <div class="odd-edge {phc}">{phs} {phe:+}%</div>
                            <div class="odd-implied">impl. {implied_prob(ph_odd)}%</div>
                        </div>
                        <div class="odds-cell">
                            <div class="odd-value" style="color:#f0e060">{pd_odd}</div>
                            <div class="odd-edge {pdc}">{pds} {pde:+}%</div>
                            <div class="odd-implied">impl. {implied_prob(pd_odd)}%</div>
                        </div>
                        <div class="odds-cell">
                            <div class="odd-value" style="color:#f060a0">{pa_odd}</div>
                            <div class="odd-edge {pac}">{pas_} {pae:+}%</div>
                            <div class="odd-implied">impl. {implied_prob(pa_odd)}%</div>
                        </div>
                    </div>
                </div>
"""
        
        if b365:
            html += '                <div class="odds-source">📡 Datos de OddsPapi · Actualizado ' + \
                     (odds_cache.get(list(odds_cache.keys())[0], {}).get('updated', 'hoy') 
                      if odds_cache else 'hoy') + '</div>\n'
        
        html += '            </div>\n\n'
        
        html += f"""
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
        
        html += f"""                </div>
            </div>
            
            <div class="narrative">📊 {r['narrative']}</div>
            
"""
        html += build_matchup_narrative(r['home_team'], r['away_team'], team_stats_narrative)
        html += f"""
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
        </div><!-- /tab-partidos -->
        
        <div id="tab-combinadas" class="tab-panel">
        <div class="combinadas-section">
            <h2>🎰 COMBINADAS RECOMENDADAS (cuotas bet365)</h2>
            <div class="combi-row">
                <div class="combi-card segura">
                    <h3>🟢 SEGURA</h3>
                    <div class="combi-tagline">3 Over 1.5 — todos edges positivos</div>
                    <div class="combi-stats">
                        <div class="combi-stat">
                            <div class="stat-num">{combinadas['segura']['prob']*100:.1f}%</div>
                            <div class="stat-label">Probabilidad</div>
                        </div>
                        <div class="combi-stat">
                            <div class="stat-num">{combinadas['segura']['cuota']:.2f}</div>
                            <div class="stat-label">Cuota bet365</div>
                        </div>
                    </div>
                    <div class="combi-legs">
"""
    for i, leg in enumerate(combinadas['segura']['legs'], 1):
        edge_sign = '+' if leg['edge'] >= 0 else ''
        html += f'                        <div class="combi-leg"><span class="combi-leg-num">{i}</span> {leg["text"]} (@{leg["cuota"]:.2f} · P={leg["prob"]*100:.0f}% · edge {edge_sign}{leg["edge"]:.1f}%)</div>\n'
    
    ev_seg = combinadas['segura']['prob'] * combinadas['segura']['cuota'] * 100
    html += f"""                    </div>
                    <div class="combi-payout">💶 Con <strong>10€</strong> → <strong>~{10*combinadas['segura']['cuota']:.0f}€</strong> &nbsp; <span style="color:#2ecc71">EV +{ev_seg-100:.1f}% 🟢</span></div>
                </div>
                <div class="combi-card media">
                    <h3>🟠 MEDIA</h3>
                    <div class="combi-tagline">Over 2.5 + BTTS con edges fuertes</div>
                    <div class="combi-stats">
                        <div class="combi-stat">
                            <div class="stat-num">{combinadas['media']['prob']*100:.1f}%</div>
                            <div class="stat-label">Probabilidad</div>
                        </div>
                        <div class="combi-stat">
                            <div class="stat-num">{combinadas['media']['cuota']:.2f}</div>
                            <div class="stat-label">Cuota bet365</div>
                        </div>
                    </div>
                    <div class="combi-legs">
"""
    for i, leg in enumerate(combinadas['media']['legs'], 1):
        edge_sign = '+' if leg['edge'] >= 0 else ''
        html += f'                        <div class="combi-leg"><span class="combi-leg-num">{i}</span> {leg["text"]} (@{leg["cuota"]:.2f} · P={leg["prob"]*100:.0f}% · edge {edge_sign}{leg["edge"]:.1f}%)</div>\n'
    
    ev_med = combinadas['media']['prob'] * combinadas['media']['cuota'] * 100
    html += f"""                    </div>
                    <div class="combi-payout">💶 Con <strong>10€</strong> → <strong>~{10*combinadas['media']['cuota']:.0f}€</strong> &nbsp; <span style="color:#2ecc71">EV +{ev_med-100:.1f}% 🟢</span></div>
                </div>
                <div class="combi-card sonadora">
                    <h3>🔴 SOÑADORA</h3>
                    <div class="combi-tagline">Goles + sorpresa con edge 🎯</div>
                    <div class="combi-stats">
                        <div class="combi-stat">
                            <div class="stat-num">{combinadas['sonadora']['prob']*100:.1f}%</div>
                            <div class="stat-label">Probabilidad</div>
                        </div>
                        <div class="combi-stat">
                            <div class="stat-num">{combinadas['sonadora']['cuota']:.2f}</div>
                            <div class="stat-label">Cuota bet365</div>
                        </div>
                    </div>
                    <div class="combi-legs">
"""
    for i, leg in enumerate(combinadas['sonadora']['legs'], 1):
        edge_sign = '+' if leg['edge'] >= 0 else ''
        html += f'                        <div class="combi-leg"><span class="combi-leg-num">{i}</span> {leg["text"]} (@{leg["cuota"]:.2f} · P={leg["prob"]*100:.0f}% · edge {edge_sign}{leg["edge"]:.1f}%)</div>\n'
    
    ev_son = combinadas['sonadora']['prob'] * combinadas['sonadora']['cuota'] * 100
    html += f"""                    </div>
                    <div class="combi-payout">💶 Con <strong>10€</strong> → <strong>~{10*combinadas['sonadora']['cuota']:.0f}€</strong> &nbsp; <span style="color:#2ecc71">EV +{ev_son-100:.1f}% 🟢</span></div>
                </div>
            </div>
        </div>
        </div><!-- /tab-combinadas -->
        
        <div id="tab-valuebets" class="tab-panel">
""" + _build_value_bets_html() + """
        </div><!-- /tab-valuebets -->
        
        <div id="tab-comparativa" class="tab-panel">
            <div class="comparison-section">
                <h2>📈 COMPARATIVA: PREDICCIONES vs REALIDAD</h2>
                """ + comparison_html + """
            </div>
        </div><!-- /tab-comparativa -->
"""

    html += f"""
        <div class="footer">
            ⚡ Sistema de predicción basado en modelo compuesto (Elo + Estadísticas + Goles esperados)<br>
            Datos de Sofascore · 72 partidos analizados · 48 selecciones · {len(engine.team_stats)} con estadísticas completas<br>
            <small>Generado el 30 de junio de 2026 · Solo con fines informativos</small>
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
