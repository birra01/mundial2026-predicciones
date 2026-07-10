#!/usr/bin/env python3
"""
World Cup 2026 — Predicciones Web
Genera HTML premium con analisis del partido (10 julio 2026)
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
from worldcup.tracker import BetTracker, MARKET_TYPES
from value_bets import build_value_bets, load_all_matches, build_matchup_narrative, compute_team_averages, load_real_stats, compare_predictions, build_comparison_html, adjusted_prediction, PREDICTABLE_STATS

# ─── Nombres en español para mostrar ───────────────────────────────────
DISPLAY_NAMES = {
    "Côte d'Ivoire": "Costa de Marfil",
    "South Korea": "Corea del Sur",
    "USA": "EE.UU.",
    "Czechia": "República Checa",
    "Netherlands": "Países Bajos",
    "DR Congo": "RD Congo",
    "Bosnia & Herzegovina": "Bosnia",
    "Senegal": "Senegal",
    "Belgium": "Bélgica",
    "England": "Inglaterra",
}

def display_name(name):
    """Traduce nombres de equipos al español para mostrar en la web"""
    return DISPLAY_NAMES.get(name, name)

# ─── Cuotas reales (OddsPapi) ───────────────────────────────────────────

def load_odds_cache():
    """Carga el caché de cuotas de OddsPapi"""
    cache_path = Path(__file__).parent / "data" / "odds_cache.json"
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)
    return {}

def get_sportdb_extra_odds(home_team, away_team):
    """Lee cuotas bet365 de sportdb (incluye líneas decimales tipo O2.25, O3.25)"""
    files = {
        'Portugal': 'sportdb_Portugal_vs_Spain.json',
        'USA': 'sportdb_USA_vs_Belgium.json',
    }
    fname = files.get(home_team)
    if not fname:
        return {}
    fpath = Path(__file__).parent / "data" / fname
    if not fpath.exists():
        return {}
    with open(fpath) as f:
        raw = json.load(f)
    odds_list = raw.get("odds", [])
    b365_odds = [o for o in odds_list if o.get("bookmakerId") == 16 and o.get("bettingScope") == "FULL_TIME"]
    
    extra = {}
    for o in b365_odds:
        bt = o.get("bettingType")
        if bt == "OVER_UNDER":
            for v in o.get("odds", []):
                hcap = v.get("handicap") or {}
                line = hcap.get("value")
                sel = v.get("selection", "")
                val = v.get("value")
                if line and sel and val:
                    # Map to key like over_2_25
                    line_safe = line.replace(".", "_")
                    key = f"{sel.lower()}_{line_safe}"
                    extra[key] = float(val)
        elif bt == "HOME_DRAW_AWAY":
            # 1X2 with implied IDs
            for v in o.get("odds", []):
                eid = v.get("eventParticipantId")
                val = v.get("value")
                if val and eid is None:
                    extra["draw"] = float(val)
    return extra

def get_match_odds(cache, home_team, away_team):
    """Busca las cuotas de un partido por nombres de equipo (fuzzy match)"""
    # Alias: motor usa nombres FIFA, el caché puede tener variantes
    aliases = {
        "côte d'ivoire": "ivory coast",
        "south korea": "korea republic",
        "dr congo": "congo dr",
        "bosnia & herzegovina": "bosnia and herzegovina",
    }
    home_raw = home_team.lower().strip()
    away_raw = away_team.lower().strip()
    home_variants = {home_raw, aliases.get(home_raw, home_raw)}
    away_variants = {away_raw, aliases.get(away_raw, away_raw)}

    for fid, info in cache.items():
        ch = info.get("home", "").lower().strip()
        ca = info.get("away", "").lower().strip()
        # Intentar con todas las variantes (alias + original)
        h_match = any(ch == v or v in ch or ch in v for v in home_variants)
        a_match = any(ca == v or v in ca or ca in v for v in away_variants)
        if h_match and a_match:
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
            # Añadir cuotas de sportdb (líneas decimales)
            sportdb_extra = get_sportdb_extra_odds(home_team, away_team)
            for k, v in sportdb_extra.items():
                if k not in merged:
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
    """P(X > goals) = 1 - sum_{i=0}^{floor(goals)} P(X=i)"""
    return round(1 - sum(poisson_prob(lam, i) for i in range(int(goals) + 1)), 4)

def btts_prob(xg_home, xg_away):
    """Probabilidad de ambos marcan (con correlación negativa ajustada)"""
    p_h = 1 - math.exp(-xg_home)
    p_a = 1 - math.exp(-xg_away)
    raw = p_h * p_a
    # Ajuste correlación (equipos que marcan muchos goles también encajan más)
    return raw * (1 - 0.15 * (1 - raw))

def build_combinadas(predictions, odds_cache):
    """Carga combinadas desde data/vbs_bug_fixed.json (generado por analysis_6julio_v4.py).
    Formato: SINGLE(1 pick), SEGURA(2), MEDIA(2), SOÑADORA(3), VOLÁTIL(4)."""
    data_path = Path(__file__).parent / "data" / "vbs_bug_fixed.json"
    if not data_path.exists():
        return []
    with open(data_path) as f:
        vbs_data = json.load(f)

    tier_map = {
        '🏆 SINGLE BET': {'icon': '🏆', 'css': 'single', 'key': 'SINGLE'},
        '🛡️ SEGURA':     {'icon': '🛡️', 'css': 'segura', 'key': 'SEGURA'},
        '⚡ MEDIA':       {'icon': '⚡', 'css': 'media', 'key': 'MEDIA'},
        '🌙 SOÑADORA':   {'icon': '🌙', 'css': 'sonadora', 'key': 'SOÑADORA'},
        '🔥 VOLÁTIL':    {'icon': '🔥', 'css': 'volatil', 'key': 'VOLÁTIL'},
    }

    result = []
    for match_key, match_data in vbs_data.get('matches', {}).items():
        parts = match_key.split('_vs_')
        label = f"{parts[0]} vs {parts[1]}" if len(parts) == 2 else match_key

        combis_list = []
        for c in match_data.get('combinadas', []):
            tm = tier_map.get(c['name'], {'icon': '🎯', 'css': 'media', 'key': c['name']})
            legs = []
            for p in c.get('picks', []):
                pick_prob = p['prob']
                implied = 100.0 / p['cuota']
                pick_edge = pick_prob - implied
                legs.append({
                    'text': f"{label}: {p['pick']}",
                    'cuota': p['cuota'],
                    'prob': pick_prob / 100.0,
                    'edge': round(pick_edge, 1),
                })
            combis_list.append({
                'tier': tm['key'],
                'icon': tm['icon'],
                'css': tm['css'],
                'desc': c.get('desc', ''),
                'legs': legs,
            })
        result.append((label, combis_list))

    return result

# ─── Integración sportdb.dev ──────────────────────────────────────────

def load_sportdb_details():
    """Carga los datos de sportdb.dev de los partidos guardados localmente"""
    data_dir = Path(__file__).parent / "data"
    files = {
        'Portugal': 'sportdb_Portugal_vs_Spain.json',
        'USA': 'sportdb_USA_vs_Belgium.json',
    }
    result = {}
    for team_key, fname in files.items():
        fpath = data_dir / fname
        if not fpath.exists():
            continue
        with open(fpath) as f:
            raw = json.load(f)
        d = raw.get("details", {})
        result[team_key] = {
            "home": {
                "id": d.get("homeId"),
                "name": d.get("homeName"),
                "slug": d.get("homeSlug"),
                "logo": d.get("homeLogo"),
            },
            "away": {
                "id": d.get("awayId"),
                "name": d.get("awayName"),
                "slug": d.get("awaySlug"),
                "logo": d.get("awayLogo"),
            },
            "referee": d.get("referee"),
            "venue": d.get("venue"),
            "venue_city": d.get("venueCity"),
            "capacity": d.get("capacity"),
        }
    return result


def get_sportdb_odds(match_key):
    """Extrae las cuotas bet365 (bookmakerId=16) de sportdb para un partido"""
    data_dir = Path(__file__).parent / "data"
    files = {
        'Portugal': 'sportdb_Portugal_vs_Spain.json',
        'USA': 'sportdb_USA_vs_Belgium.json',
    }
    fname = files.get(match_key)
    if not fname:
        return {}
    fpath = data_dir / fname
    if not fpath.exists():
        return {}
    with open(fpath) as f:
        raw = json.load(f)
    
    odds_list = raw.get("odds", [])
    bet365_odds = [o for o in odds_list if o.get("bookmakerId") == 16]
    
    result = {}
    for o in bet365_odds:
        bt = o["bettingType"]
        scope = o["bettingScope"]
        if scope != "FULL_TIME":
            continue
        values = []
        for od in o.get("odds", []):
            val = od.get("value")
            if val:
                sel = od.get("selection", "")
                hcap = od.get("handicap")
                sel_key = sel or ""
                if hcap and isinstance(hcap, dict) and hcap.get("value"):
                    sel_key = f"{hcap['value']}_{sel}"
                values.append({"selection": sel_key, "value": float(val)})
        
        if bt == "HOME_DRAW_AWAY":
            parts = values
            if len(parts) >= 3:
                result["sportdb_home"] = parts[0]["value"]
                result["sportdb_draw"] = parts[2]["value"]
                result["sportdb_away"] = parts[1]["value"]
        elif bt == "OVER_UNDER":
            for v in values:
                sel = v["selection"]
                if "0.5_OVER" in sel or sel == "OVER" and v["value"] <= 1.1:
                    result["sportdb_ou_05"] = v["value"]
                elif "1.5_OVER" in sel:
                    result["sportdb_ou_15"] = v["value"]
                elif "2.5_OVER" in sel:
                    result["sportdb_ou_25"] = v["value"]
                elif "3.5_OVER" in sel:
                    result["sportdb_ou_35"] = v["value"]
        elif bt == "BOTH_TEAMS_TO_SCORE":
            for v in values:
                if v["selection"] == "":
                    if v["value"] > 2.0:
                        result["sportdb_btts_yes"] = v["value"]
                    else:
                        result["sportdb_btts_no"] = v["value"]
        elif bt == "DOUBLE_CHANCE":
            result["sportdb_dc"] = values[0]["value"] if values else None
        elif bt == "ASIAN_HANDICAP":
            result["sportdb_asian_h"] = values[0]["value"] if values else None
    
    return result


def _build_value_bets_html():
    """Genera el HTML de la sección Value Bets - SOLO análisis exhaustivo (5 mercados)"""
    # Cargar el JSON del análisis exhaustivo
    all_vbs_path = Path(__file__).parent / "data" / "vbs_bug_fixed.json"
    extra_vbs = []
    if all_vbs_path.exists():
        with open(all_vbs_path) as f:
            raw = json.load(f)
        # Handle both old flat format and new nested format
        if isinstance(raw, dict) and 'matches' in raw:
            for match_key, match_data in raw['matches'].items():
                parts = match_key.split('_vs_')
                match_label = f"{parts[0]} vs {parts[1]}" if len(parts) == 2 else match_key
                for vb in match_data.get('vbs', []):
                    vb['match'] = match_label
                    extra_vbs.append(vb)
        elif isinstance(raw, list):
            extra_vbs = raw

    if not extra_vbs:
        return '<div class="no-value-bets">🔍 No se encontraron value bets para los próximos partidos.<br><small>Genera primero el análisis exhaustivo con value_bets.py</small></div>'

    html = '<div class="value-bets-intro">🎯 Predicciones de eventos (goles, córners, tarjetas, tiros, BTTS, 1X2). Edge = diferencia entre la probabilidad del modelo y la implícita de la cuota. 🟢 EV+ es value bet real.</div>\n'

    # ─── ÚNICA SECCIÓN: VALUE BETS EXHAUSTIVOS (5 mercados) ───
    html += '<h3 class="vb-section-title">📊 Value Bets — Análisis Exhaustivo (5 mercados)</h3>\n'
    html += '<div class="value-bets-grid">\n'
    # Ordenar por edge descendente
    extra_vbs_sorted = sorted(extra_vbs, key=lambda x: -x['edge'])
    for vb in extra_vbs_sorted:
        market = vb['market']
        match = vb['match']
        pick = vb['pick']
        cuota = vb['cuota']
        prob = vb['prob']
        edge = vb['edge']

        # Icono por mercado
        market_icons = {
            'Goles': '⚽',
            'BTTS': '🥅',
            'Córners': '🏳️',
            'Tarjetas': '🟨',
            '1X2': '🏆',
        }
        icon = market_icons.get(market, '📊')

        # Clase por edge
        if edge >= 15:
            edge_class = 'edge-strong'
            edge_icon = '🔥'
        elif edge >= 5:
            edge_class = 'edge-mild'
            edge_icon = '🟢'
        else:
            edge_class = 'edge-flat'
            edge_icon = '🟡'

        ev = (prob / 100) * cuota * 100  # EV%
        edge_sign = '+' if edge >= 0 else ''

        html += f'''        <div class="value-bet-card {edge_class}">
            <div class="value-bet-header">
                <span class="value-bet-match">⚽ {match}</span>
                <span class="value-bet-market">{icon} {market} — {pick}</span>
            </div>
            <div class="value-bet-body">
                <div class="value-bet-stat highlight">
                    <div class="stat-num">{prob:.1f}%</div>
                    <div class="stat-label">Prob. modelo</div>
                </div>
                <div class="value-bet-stat">
                    <div class="stat-num">{cuota:.2f}</div>
                    <div class="stat-label">Cuota bet365</div>
                </div>
                <div class="value-bet-stat">
                    <div class="stat-num">{100/cuota:.1f}%</div>
                    <div class="stat-label">Implícita</div>
                </div>
                <div class="value-bet-verdict {edge_class}">
                    <div class="edge-badge">{edge_icon} {edge_sign}{edge:.1f}%</div>
                    <div class="edge-label">EDGE · EV {edge_sign}{(ev-100):.0f}%</div>
                </div>
            </div>
        </div>
'''
    html += '</div>\n'
    return html


def build_tracker_section(report):
    """Genera HTML para la sección de aprendizaje del motor."""
    o = report['overall']
    by_market = report['by_market']
    calibration = report.get('calibration', {})
    learned = report.get('learned_weights', {})
    recommendations = calibration.get('recommendations', [])
    
    def roi_color(roi):
        if roi > 20: return '#00ff88'
        if roi > 5: return '#88ff88'
        if roi > 0: return '#ffff88'
        if roi > -10: return '#ffaa88'
        return '#ff4444'
    
    def wr_color(wr):
        if wr > 55: return '#00ff88'
        if wr > 50: return '#88ff88'
        if wr > 45: return '#ffff88'
        return '#ff4444'
    
    html = '''
<div style="margin-top:40px;padding-top:30px;border-top:2px solid #1a2030">
<h2 style="color:#60f0a0;font-size:1.5em;margin-bottom:20px">🧠 Motor de Aprendizaje</h2>
<p style="color:#888;margin-bottom:20px">El motor registra cada predicción y la compara con el resultado real. Cuantos más partidos, más preciso.</p>
'''
    
    # KPIs
    profit_class = 'kpi-positive' if o['total_profit'] > 0 else 'kpi-negative'
    profit_sign = '+' if o['total_profit'] > 0 else ''
    roi_sign = '+' if o['roi'] > 0 else ''
    
    html += f'''
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0">
  <div style="background:#12161f;border:1px solid #1a2030;border-radius:10px;padding:15px;text-align:center">
    <div style="font-size:1.8em;font-weight:700;color:#f0c040">{o['total_matches']}</div>
    <div style="color:#888;font-size:0.8em">Partidos</div>
  </div>
  <div style="background:#12161f;border:1px solid #1a2030;border-radius:10px;padding:15px;text-align:center">
    <div style="font-size:1.8em;font-weight:700;color:#f0c040">{o['total_bets']}</div>
    <div style="color:#888;font-size:0.8em">Apuestas</div>
  </div>
  <div style="background:#12161f;border:1px solid #1a2030;border-radius:10px;padding:15px;text-align:center">
    <div style="font-size:1.8em;font-weight:700;color:{wr_color(o['win_rate'])}">{o['win_rate']}%</div>
    <div style="color:#888;font-size:0.8em">Win Rate</div>
  </div>
  <div style="background:#12161f;border:1px solid #1a2030;border-radius:10px;padding:15px;text-align:center">
    <div style="font-size:1.8em;font-weight:700;color:{profit_class}">{roi_sign}{o['roi']}%</div>
    <div style="color:#888;font-size:0.8em">ROI</div>
  </div>
  <div style="background:#12161f;border:1px solid #1a2030;border-radius:10px;padding:15px;text-align:center">
    <div style="font-size:1.8em;font-weight:700;color:{profit_class}">{profit_sign}{o['total_profit']}</div>
    <div style="color:#888;font-size:0.8em">Profit</div>
  </div>
</div>
'''
    
    # Tabla por mercado
    html += '''
<h3 style="color:#f0c040;margin:20px 0 10px">📊 Rendimiento por Mercado</h3>
<table style="width:100%;border-collapse:collapse">
<thead>
<tr style="background:#12161f">
  <th style="padding:10px;text-align:left;color:#f0c040;font-size:0.85em">MERCADO</th>
  <th style="padding:10px;text-align:center;color:#f0c040;font-size:0.85em">BETS</th>
  <th style="padding:10px;text-align:center;color:#f0c040;font-size:0.85em">WIN%</th>
  <th style="padding:10px;text-align:center;color:#f0c040;font-size:0.85em">ROI</th>
  <th style="padding:10px;text-align:center;color:#f0c040;font-size:0.85em">PROFIT</th>
</tr>
</thead>
<tbody>'''
    
    for m, s in sorted(by_market.items(), key=lambda x: x[1]['roi'], reverse=True):
        name = m.replace('_', ' ').title()
        roi = s['roi']
        wr = s['win_rate']
        bets = s['bets']
        profit = s['total_profit']
        
        roi_cls = 'color:#00ff88' if roi > 5 else 'color:#ff4444' if roi < -5 else 'color:#f0c040'
        profit_sign = '+' if profit > 0 else ''
        bar_w = min(100, max(5, abs(roi)))
        bar_c = roi_color(roi)
        
        html += f'''
<tr style="border-bottom:1px solid #1a2030">
  <td style="padding:10px;font-weight:600">{name}</td>
  <td style="padding:10px;text-align:center">{bets}</td>
  <td style="padding:10px;text-align:center;color:{wr_color(wr)}">{wr}%</td>
  <td style="padding:10px;text-align:center;{roi_cls}">{'+' if roi > 0 else ''}{roi}%</td>
  <td style="padding:10px;text-align:center;{roi_cls}">{profit_sign}{profit}</td>
</tr>'''
    
    html += '</tbody></table>'
    
    # Insights
    insights = []
    if 'corners_under' in by_market:
        cu = by_market['corners_under']
        if cu['roi'] > 10:
            insights.append(f"✅ <strong>Córners Under</strong> es el mercado más rentable: +{cu['roi']}% ROI en {cu['bets']} apuestas.")
    if 'cards_over' in by_market:
        co = by_market['cards_over']
        if co['roi'] > 5:
            insights.append(f"✅ <strong>Tarjetas Over</strong> tiene edge consistente: +{co['roi']}% ROI, {co['win_rate']}% acierto.")
    if 'corners_over' in by_market:
        co = by_market['corners_over']
        if co['roi'] < -5:
            insights.append(f"❌ <strong>Córners Over</strong> pierde dinero: {co['roi']}% ROI. El modelo predice demasiados córners.")
    
    if insights:
        html += '''
<h3 style="color:#f0c040;margin:20px 0 10px">💡 Insights</h3>'''
        for ins in insights:
            html += f'''
<div style="background:#12161f;border-left:4px solid #f0c040;border-radius:0 8px 8px 0;padding:12px 16px;margin:8px 0;color:#ccc">
  {ins}
</div>'''
    
    # Recomendaciones
    if recommendations:
        html += '''
<h3 style="color:#f0c040;margin:20px 0 10px">🔧 Recomendaciones Automáticas</h3>'''
        for rec in recommendations:
            arrow = '⬆️' if rec['action'] == 'increase_weight' else '⬇️'
            if rec['action'] == 'recalibrate_probabilities':
                arrow = '🔄'
            html += f'''
<div style="background:#12161f;border:1px solid #1a2030;border-radius:8px;padding:12px;margin:6px 0;display:flex;align-items:center;gap:10px">
  <span style="font-size:1.3em">{arrow}</span>
  <div>
    <div style="font-weight:600;color:#f0c040">{rec['market'].replace('_', ' ').title()}</div>
    <div style="color:#aaa;font-size:0.9em">{rec['reason']}</div>
  </div>
</div>'''
    
    html += '</div>'
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
    
    # Cargar datos de sportdb.dev
    sportdb_details = load_sportdb_details()
    
    # Partidos de hoy 10 julio (Cuartos de final)
    matches_today = [
        ("Spain", "Belgium", "12:00"),
    ]
    
    predictions = []
    for home, away, time in matches_today:
        r = engine.predict_match(home, away)
        r['time'] = time
        # Cuotas reales
        b365, pinnacle = get_match_odds(odds_cache, home, away)
        r['odds_b365'] = b365
        r['odds_pinnacle'] = pinnacle
        
        # Datos sportdb.dev
        match_key = home
        sd = sportdb_details.get(match_key, {})
        r['sportdb'] = sd
        r['sportdb_odds'] = get_sportdb_odds(match_key)
        
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
    # Para la comparativa, también incluimos predicciones de partidos ya jugados
    # (ayer 1 julio: England, Belgium, USA) cargando de predictions_1jul.json
    yesterday_pred_path = Path(__file__).parent / "data" / "predictions_1jul.json"
    if yesterday_pred_path.exists():
        with open(yesterday_pred_path) as f:
            yesterday_preds = json.load(f)
        # Asegurar que tienen value_bets para que compare_predictions las use
        for yp in yesterday_preds:
            if 'value_bets' not in yp:
                vb_list = []
                for stat_key in PREDICTABLE_STATS:
                    pred_h, pred_a = adjusted_prediction(team_stats_narrative, yp['home_team'], yp['away_team'], stat_key)
                    if pred_h > 0 or pred_a > 0:
                        vb_list.append({
                            'stat_key': stat_key,
                            'total_pred': round(pred_h + pred_a, 2),
                            'pred_home': pred_h,
                            'pred_away': pred_a,
                            'ev_pct': 0,
                        })
                yp['value_bets'] = vb_list
        all_predictions_for_comparison = predictions + yesterday_preds
    else:
        all_predictions_for_comparison = predictions
    comparisons = compare_predictions(all_predictions_for_comparison, real_stats)
    comparison_html = build_comparison_html(comparisons)
    
    # ─── TRACKER DE APRENDIZAJE ───
    tracker = BetTracker()
    # Registrar predicciones de hoy
    for r in predictions:
        match_name = f"{r['home_team']} vs {r['away_team']}"
        tracker.log_prediction(match_name, r['home_team'], r['away_team'], r.get('value_bets', []))
    # Intentar registrar resultados de partidos ya jugados
    for r in predictions:
        match_key = f"{r['home_team']} vs {r['away_team']}"
        # Buscar stats reales
        real = real_stats.get(match_key)
        if not real:
            for rk, rv in real_stats.items():
                if rk.startswith('_'):
                    continue
                if rk.lower() == match_key.lower():
                    real = rv
                    break
        if real:
            tracker.log_result(match_key, real)
    tracker_report = tracker.get_report()
    tracker_html = build_tracker_section(tracker_report)
    
    # Construir HTML
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mundial 2026 — Predicciones 10 Julio</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            background: #0a0e27;
            color: #e0e0e0;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{ max-width: 1100px; margin: 0 auto; }}
        
        /* ─── HEADER ─── */
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
        .header .subtitle {{ color: #8890b0; font-size: 1.1em; }}
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
        .tab-btn:hover {{ color: #a0a8c0; background: #151a35; }}
        .tab-btn.active {{
            background: linear-gradient(135deg, #1a2f50, #152040);
            color: #e0e0e0;
            box-shadow: 0 2px 12px rgba(0,0,0,0.3);
        }}
        .tab-panel {{ display: none; }}
        .tab-panel.active {{ display: block; }}
        
        /* ─── MATCH CARD ─── */
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
        .vs {{ color: #5a6080; font-size: 1em; font-weight: 400; }}
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
        
        /* ─── BARRAS DE PROBABILIDAD ─── */
        .probabilities {{ display: flex; gap: 12px; margin-bottom: 24px; }}
        .prob-bar {{ flex: 1; text-align: center; }}
        .prob-bar .label {{ font-size: 0.8em; color: #8890b0; margin-bottom: 6px; font-weight: 500; }}
        .prob-bar .value {{ font-size: 1.8em; font-weight: 800; margin-bottom: 6px; }}
        .prob-bar.home .value {{ color: #60f0a0; }}
        .prob-bar.draw .value {{ color: #f0e060; }}
        .prob-bar.away .value {{ color: #f060a0; }}
        .bar-track {{
            height: 8px;
            background: #1e2445;
            border-radius: 4px;
            overflow: hidden;
        }}
        .bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s; }}
        .bar-fill.home {{ background: linear-gradient(90deg, #30a050, #60f0a0); }}
        .bar-fill.draw {{ background: linear-gradient(90deg, #909030, #f0e060); }}
        .bar-fill.away {{ background: linear-gradient(90deg, #a03050, #f060a0); }}
        
        /* ─── TABLA COMPARATIVA CUOTAS ─── */
        .odds-section {{
            background: #0d1030;
            border-radius: 12px;
            padding: 18px 20px;
            margin-bottom: 20px;
            border: 1px solid #2a2f4a;
        }}
        .odds-section h3 {{
            font-size: 0.78em;
            font-weight: 700;
            color: #f0c040;
            margin-bottom: 14px;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}
        .odds-row {{
            display: flex;
            gap: 8px;
            margin-bottom: 8px;
        }}
        .odds-label {{
            width: 90px;
            font-size: 0.72em;
            color: #6a70a0;
            font-weight: 600;
            padding: 8px 0;
            flex-shrink: 0;
        }}
        .odds-cells {{ display: flex; gap: 8px; flex: 1; }}
        .odds-cell {{
            flex: 1;
            text-align: center;
            background: #101530;
            border-radius: 8px;
            padding: 8px 6px;
            border: 1px solid #1e2450;
        }}
        .odds-cell .odd-value {{ font-weight: 800; font-size: 1em; }}
        .odds-cell .odd-edge {{ font-size: 0.7em; margin-top: 1px; font-weight: 600; }}
        .odds-cell .odd-edge.value-strong {{ color: #60f0a0; }}
        .odds-cell .odd-edge.value-mild {{ color: #f0c040; }}
        .odds-cell .odd-edge.value-flat {{ color: #8890b0; }}
        .odds-cell .odd-edge.value-negative {{ color: #f06090; }}
        .odds-cell .odd-implied {{ font-size: 0.65em; color: #5860a0; margin-top: 1px; }}
        .odds-cell .odd-source-name {{ font-size: 0.6em; color: #4a5080; margin-top: 1px; }}
        .odds-source {{
            font-size: 0.62em;
            color: #4a5080;
            text-align: right;
            margin-top: 6px;
        }}
        
        /* ─── ESTADÍSTICAS ─── */
        .stats-section {{ margin-bottom: 16px; }}
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
        
        /* ─── NARRATIVA ─── */
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
        .matchup-narrative strong {{ color: #80b0f0; }}
        
        /* ─── MODEL BREAKDOWN ─── */
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
        .model-chip span {{ color: #e09020; font-weight: 700; }}
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
        .model-legend-toggle:hover {{ color: #e09020; border-color: #e09020; }}
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
        .model-legend.show {{ display: block; }}
        .model-legend strong {{ color: #e0e0e0; }}
        .model-legend .legend-elo {{ color: #60f0a0; }}
        .model-legend .legend-stats {{ color: #f0c040; }}
        .model-legend .legend-poisson {{ color: #60a0f0; }}
        
        /* ─── COMBINADAS ─── */
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
        .combi-row {{ display: flex; gap: 16px; }}
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
        .combi-card h3 {{ font-size: 1em; margin-bottom: 4px; text-align: center; }}
        .combi-card.segura h3 {{ color: #60f0a0; }}
        .combi-card.media h3 {{ color: #f0c040; }}
        .combi-card.sonadora h3 {{ color: #f060a0; }}
        .combi-card.volatil {{ border-color: #e74c3c; }}
        .combi-card.volatil::before {{ background: linear-gradient(90deg, #e74c3c, #f39c12); }}
        .combi-card.volatil h3 {{ color: #e74c3c; }}
        .combi-card.single {{ border-color: #f0c040; }}
        .combi-card.single::before {{ background: linear-gradient(90deg, #f0c040, #fff7b0); }}
        .combi-card.single h3 {{ color: #f0c040; }}
        .combi-card.single .stat-num {{ color: #f0c040; }}
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
        .combi-stat {{ text-align: center; }}
        .combi-stat .stat-num {{ font-size: 1.4em; font-weight: 800; }}
        .combi-card.segura .stat-num {{ color: #60f0a0; }}
        .combi-card.media .stat-num {{ color: #f0c040; }}
        .combi-card.sonadora .stat-num {{ color: #f060a0; }}
        .combi-card.volatil .stat-num {{ color: #e74c3c; }}
        .combi-stat .stat-label {{ color: #6a70a0; font-size: 0.85em; margin-top: 2px; }}
        .combi-legs {{ font-size: 0.78em; color: #a0b0d0; }}
        .combi-leg {{
            padding: 6px 0;
            border-bottom: 1px solid #1a1f3a;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .combi-leg:last-child {{ border-bottom: none; }}
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
        .combi-payout strong {{ color: #e0e0e0; font-size: 1.15em; }}
        
        /* ─── VALUE BETS ─── */
        .value-bets-intro {{
            text-align: center;
            color: #8890b0;
            margin-bottom: 20px;
            font-size: 0.9em;
        }}
        .vb-section-title {{
            color: #f0c040;
            font-size: 1.3em;
            font-weight: 700;
            margin: 28px 0 16px 0;
            padding-bottom: 8px;
            border-bottom: 1px solid #2a2f4a;
        }}
        .value-bets-grid {{ display: grid; gap: 16px; }}
        .value-bet-card {{
            background: linear-gradient(145deg, #151a35 0%, #111530 100%);
            border-radius: 12px;
            padding: 18px 20px;
            border: 1px solid #2a2f4a;
            transition: transform 0.2s;
            position: relative;
            overflow: hidden;
        }}
        .value-bet-card:hover {{ transform: translateY(-2px); }}
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
        .value-bet-card.no-odds::before {{ background: #606070; }}
        .value-bet-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .value-bet-match {{ font-weight: 700; font-size: 1.05em; color: #e0e0e0; }}
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
        .value-bet-stat .stat-num {{ font-size: 1.3em; font-weight: 800; color: #e0e0e0; }}
        .value-bet-stat .stat-label {{ font-size: 0.7em; color: #6a70a0; margin-top: 3px; }}
        .value-bet-stat.highlight {{ border: 1px solid #2a4a3a; }}
        .value-bet-stat.highlight .stat-num {{ color: #60f0a0; }}
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
        .value-bet-verdict .edge-badge {{ font-size: 1.6em; font-weight: 800; }}
        .value-bet-verdict .edge-label {{ font-size: 0.7em; color: #6a70a0; }}
        .edge-strong .edge-badge {{ color: #60f0a0; }}
        .edge-mild .edge-badge {{ color: #f0c040; }}
        .edge-flat .edge-badge {{ color: #8890b0; }}
        .edge-negative .edge-badge {{ color: #f06090; }}
        .no-odds .edge-badge {{ color: #9090b0; }}
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
        .value-bet-context span {{ display: inline-flex; align-items: center; gap: 4px; }}
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
        .comparison-match-name {{ font-size: 1.2em; font-weight: bold; color: #f0c040; }}
        .comparison-avg-acc {{ font-size: 1.1em; font-weight: bold; }}
        .comparison-grid {{ display: flex; flex-direction: column; gap: 12px; }}
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
        .comp-pred {{ color: #60a0f0; }}
        .comp-vs {{ color: #5a6080; }}
        .comp-real {{ color: #60f0a0; }}
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
        .comparison-bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s ease; }}
        .comparison-acc {{
            font-weight: bold;
            min-width: 60px;
            text-align: right;
            font-size: 0.92em;
        }}
        
        /* ─── FOOTER ─── */
        .footer {{
            text-align: center;
            padding: 30px;
            color: #5a6080;
            font-size: 0.8em;
        }}
        .footer a {{ color: #e09020; text-decoration: none; }}
        
        /* ─── RESPONSIVE ─── */
        @media (max-width: 768px) {{
            .match-header {{ flex-wrap: wrap; }}
            .teams {{ order: 3; width: 100%; }}
            .match-time, .prediction-badge {{ font-size: 0.75em; }}
            .prob-bar .value {{ font-size: 1.3em; }}
            .combi-row {{ flex-direction: column; }}
            .value-bet-body {{ flex-direction: column; }}
            .odds-row {{ flex-direction: column; gap: 4px; }}
            .odds-label {{ width: 100%; text-align: center; padding: 4px 0; }}
            .odds-cells {{ gap: 4px; }}
            .odds-cell {{ padding: 6px 4px; }}
            .odds-cell .odd-value {{ font-size: 0.85em; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏆 Mundial 2026 — Cuartos de Final</h1>
            <div class="subtitle">Predicciones basadas en 72 partidos · 48 equipos · Estadísticas reales de Sofascore + sportdb.dev</div>
            <div class="badge">📅 10 de julio de 2026 · 1 partido</div>
        </div>
        
        <!-- ─── PESTAÑAS ─── -->
        <div class="tabs-nav">
            <button class="tab-btn active" onclick="switchTab('partidos')">📊 Partidos</button>
            <button class="tab-btn" onclick="switchTab('combinadas')">🎰 Combinadas</button>
            <button class="tab-btn" onclick="switchTab('valuebets')">🎯 Value Bets</button>
            <button class="tab-btn" onclick="switchTab('aprendizaje')">🧠 Aprendizaje</button>
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
            pred_text = f"Gana {display_name(r['home_team'])}"
        elif r['prediction'] == 'AWAY':
            pred_text = f"Gana {display_name(r['away_team'])}"
        else:
            pred_text = "Empate"
        
        html += f"""
        <div class="match-card">
            <div class="match-header">
                <div class="match-time">⏰ {r['time']}</div>
                <div class="teams">
                    <span class="team">{display_name(r['home_team'])}</span>
                    <span class="vs">vs</span>
                    <span class="team">{display_name(r['away_team'])}</span>
                </div>
                <div>
                    <span class="prediction-badge {r['prediction']}">{pred_text}<span class="confidence">{r['confidence']}</span></span>
                </div>
            </div>
            
            <!-- ─── DATOS DEL PARTIDO (sportdb.dev) ─── -->
"""         
        sd = r.get('sportdb', {})
        if sd.get('venue'):
            venue_parts = [sd['venue']]
            if sd.get('venue_city'):
                venue_parts.append(f"({sd['venue_city']})")
            if sd.get('capacity'):
                venue_parts.append(f"· {sd['capacity']} esp.")
            venue_str = ' '.join(venue_parts)
            ref = sd.get('referee') or ''
            html += f'            <div style="text-align:center;margin-bottom:16px;font-size:0.82em;color:#6a70a0;">🏟️ {venue_str}{" · 🧑‍⚖️ " + ref if ref else ""}</div>\n'
        
        html += f"""
            <div class="probabilities">
                <div class="prob-bar home">
                    <div class="label">{display_name(r['home_team'])}</div>
                    <div class="value">{p['home']}%</div>
                    <div class="bar-track"><div class="bar-fill home" style="width:{p['home']}%"></div></div>
                </div>
                <div class="prob-bar draw">
                    <div class="label">Empate</div>
                    <div class="value">{p['draw']}%</div>
                    <div class="bar-track"><div class="bar-fill draw" style="width:{p['draw']}%"></div></div>
                </div>
                <div class="prob-bar away">
                    <div class="label">{display_name(r['away_team'])}</div>
                    <div class="value">{p['away']}%</div>
                    <div class="bar-track"><div class="bar-fill away" style="width:{p['away']}%"></div></div>
                </div>
            </div>
            
"""
        
        # ─── Sección de cuotas reales ───
        b365 = r.get('odds_b365') or {}
        pinn = r.get('odds_pinnacle') or {}
        
        # ─── COMPARATIVA UNIFICADA: Modelo vs OddsPapi vs sportdb.dev ───
        so = r.get('sportdb_odds', {})
        tiene_sportdb = so.get('sportdb_home', 0) > 0
        
        if b365 or pinn or tiene_sportdb:
            html += """            <div class="odds-section">
                <h3>💰 COMPARATIVA CUOTAS: Modelo vs bet365 vs Pinnacle</h3>
"""
            # ── Fila 1: Modelo (%)
            html += f"""                <div class="odds-row">
                    <div class="odds-label">Modelo</div>
                    <div class="odds-cells">
                        <div class="odds-cell"><div class="odd-value" style="color:#60f0a0">{p['home']}%</div><div class="odd-implied">{display_name(r['home_team'])}</div></div>
                        <div class="odds-cell"><div class="odd-value" style="color:#f0e060">{p['draw']}%</div><div class="odd-implied">Empate</div></div>
                        <div class="odds-cell"><div class="odd-value" style="color:#f060a0">{p['away']}%</div><div class="odd-implied">{display_name(r['away_team'])}</div></div>
                    </div>
                </div>
"""
            # ── Fila 2: bet365 (solo OddsPapi) ──
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
                    <div class="odds-label" style="color:#00a650">bet365</div>
                    <div class="odds-cells">
                        <div class="odds-cell"><div class="odd-value" style="color:#60f0a0">{h_odd}</div><div class="odd-edge {hc}">{hs} {he:+}%</div></div>
                        <div class="odds-cell"><div class="odd-value" style="color:#f0e060">{d_odd}</div><div class="odd-edge {dc}">{ds} {de:+}%</div></div>
                        <div class="odds-cell"><div class="odd-value" style="color:#f060a0">{a_odd}</div><div class="odd-edge {ac}">{as_} {ae:+}%</div></div>
                    </div>
                </div>
"""
            # ── Fila 3: Pinnacle ──
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
                        <div class="odds-cell"><div class="odd-value" style="color:#60f0a0">{ph_odd}</div><div class="odd-edge {phc}">{phs} {phe:+}%</div><div class="odd-implied">impl. {implied_prob(ph_odd)}%</div></div>
                        <div class="odds-cell"><div class="odd-value" style="color:#f0e060">{pd_odd}</div><div class="odd-edge {pdc}">{pds} {pde:+}%</div><div class="odd-implied">impl. {implied_prob(pd_odd)}%</div></div>
                        <div class="odds-cell"><div class="odd-value" style="color:#f060a0">{pa_odd}</div><div class="odd-edge {pac}">{pas_} {pae:+}%</div><div class="odd-implied">impl. {implied_prob(pa_odd)}%</div></div>
                    </div>
                </div>
"""
            
            if b365:
                html += '                <div class="odds-source">📡 OddsPapi · ' + \
                         (odds_cache.get(list(odds_cache.keys())[0], {}).get('updated', 'hoy') 
                          if odds_cache else 'hoy') + '</div>\n'
            
            html += '            </div>\n\n'
        
        html += f"""
            <div class="stats-section">
                <h3>📊 ESTADÍSTICAS CLAVE</h3>
                <div class="stats-two-col">
                    <div class="stats-col-header home">{display_name(r['home_team'])}</div>
                    <div></div>
                    <div class="stats-col-header away">{display_name(r['away_team'])}</div>
                    
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
        # Aplicar traducción de nombres al narrative
        for orig, disp in DISPLAY_NAMES.items():
            html = html.replace(orig, disp)
        mm_narrative = build_matchup_narrative(r['home_team'], r['away_team'], team_stats_narrative)
        for orig, disp in DISPLAY_NAMES.items():
            mm_narrative = mm_narrative.replace(orig, disp)
        html += mm_narrative
        html += f"""
            <div class="model-breakdown">
                <div class="model-chip">Elo: <span>{r['model_breakdown']['elo']}% {display_name(r['home_team'])}</span></div>
                <div class="model-chip">Estadístico: <span>{r['model_breakdown']['statistical']}% {display_name(r['home_team'])}</span></div>
                <div class="model-chip">Poisson: <span>{r['model_breakdown']['poisson']}% {display_name(r['home_team'])}</span></div>
                <button class="model-legend-toggle" onclick="this.nextElementSibling.classList.toggle('show');this.textContent=this.textContent=='¿Qué es esto?'?'Ocultar':'¿Qué es esto?'">¿Qué es esto?</button>
                <div class="model-legend">
                    <strong>Desglose de modelos:</strong> cada chip muestra qué porcentaje de victoria predice cada modelo por separado para {display_name(r['home_team'])}. Luego el sistema los <strong>mezcla ponderadamente</strong> (25% Elo + 25% Stats + 25% Poisson + 25% forma) para dar la predicción final que ves arriba.<br><br>
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
"""
    for match_label, combis_list in combinadas:
        html += f'            <h3 style="color:#f0c040;font-size:1.1em;margin:18px 0 8px;">⚽ {match_label}</h3>\n'
        html += '            <div class="combi-row">\n'
        for c in combis_list:
            tier = c['tier']
            icon = c['icon']
            css = c['css']
            desc = c['desc']
            legs = c['legs']
            cuota_total = 1.0
            prob_total = 1.0
            for leg in legs:
                cuota_total *= leg['cuota']
                prob_total *= leg['prob']
            ev = prob_total * cuota_total * 100
            ev_color = '#2ecc71' if tier != 'VOLÁTIL' else '#e74c3c'
            ev_suffix = '🟢' if tier != 'VOLÁTIL' else '🔥 ¡APUESTA DE VALOR!'
            html += f'                <div class="combi-card {css}">\n'
            html += f'                    <h3>{icon} {tier}</h3>\n'
            html += f'                    <div class="combi-tagline">{desc}</div>\n'
            html += f'                    <div class="combi-stats">\n'
            html += f'                        <div class="combi-stat"><div class="stat-num">{prob_total*100:.1f}%</div><div class="stat-label">Probabilidad</div></div>\n'
            html += f'                        <div class="combi-stat"><div class="stat-num">{cuota_total:.2f}</div><div class="stat-label">Cuota bet365</div></div>\n'
            html += f'                    </div>\n'
            html += f'                    <div class="combi-legs">\n'
            for i, leg in enumerate(legs, 1):
                edge_sign = '+' if leg['edge'] >= 0 else ''
                html += f'                        <div class="combi-leg"><span class="combi-leg-num">{i}</span> {leg["text"]} (@{leg["cuota"]:.2f} · P={leg["prob"]*100:.0f}% · edge {edge_sign}{leg["edge"]:.1f}%)</div>\n'
            html += f'                    </div>\n'
            html += f'                    <div class="combi-payout">💶 Con <strong>10€</strong> → <strong>~{10*cuota_total:.0f}€</strong> &nbsp; <span style="color:{ev_color}">EV +{ev-100:.1f}% {ev_suffix}</span></div>\n'
            html += f'                </div>\n'
        html += '            </div>\n'
    html += """
        </div>
        </div><!-- /tab-combinadas -->
        
        <div id="tab-valuebets" class="tab-panel">
""" + _build_value_bets_html() + """
        </div><!-- /tab-valuebets -->
        
        <div id="tab-aprendizaje" class="tab-panel">
""" + tracker_html + """
        </div><!-- /tab-aprendizaje -->
"""

    html += f"""
        <div class="footer">
            ⚡ Sistema de predicción basado en modelo compuesto (Elo + Estadísticas + Goles esperados)<br>
            Datos de Sofascore · 72 partidos analizados · 48 selecciones · {len(engine.team_stats)} con estadísticas completas<br>
            <small>Generado el 10 de julio de 2026 · Solo con fines informativos</small>
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
