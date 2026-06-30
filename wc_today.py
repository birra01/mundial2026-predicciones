#!/usr/bin/env python3
"""Análisis de partidos de hoy + combinadas con cuotas reales."""
import sys, math, json, time, requests

sys.path.insert(0, 'src')
from worldcup.engine import WorldCupEngine

API_KEY = open('.oddspapi_key').read().strip()
BASE = 'https://api.oddspapi.io/v4'

# Equipos: (nombre_cache_odds, nombre_motor, hora_local_ET)
MATCHES = [
    ("Ivory Coast", "Côte d'Ivoire", "Norway", "Norway", "23:00"),
    ("France", "France", "Sweden", "Sweden", "03:00"),
    ("Mexico", "Mexico", "Ecuador", "Ecuador", "03:00"),
]

# Fixture IDs del cache
FIXTURE_IDS = {
    "Ivory Coast vs Norway": "id1000001653452561",
    "France vs Sweden": "id1000001653452543",
    "Mexico vs Ecuador": "id1000001653452563",
}

# Outcome ID -> significado
OUTCOME_MAP = {
    '101': 'home', '102': 'draw', '103': 'away',
    '106': 'over_05', '107': 'under_05',
    '108': 'over_15', '109': 'under_15',
    '1010': 'over_25', '1011': 'under_25',
    '1012': 'over_35', '1013': 'under_35',
    '104': 'btts_yes', '105': 'btts_no',
}

WANTED = ['101', '102', '103', '108', '109', '1010', '1011', '1012', '1013', '104', '105']


def poisson_prob(lam, k):
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def over_prob(lam, goals):
    cum = sum(poisson_prob(lam, i) for i in range(goals + 1))
    return 1 - cum


def fetch_odds(fixture_id):
    url = f"{BASE}/odds?apiKey={API_KEY}&fixtureId={fixture_id}"
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    if r.status_code != 200:
        return {}
    data = r.json()
    bm = data.get('bookmakerOdds', {})
    result = {}
    for bookmaker in ['bet365', 'pinnacle']:
        b = bm.get(bookmaker, {})
        markets = b.get('markets', {})
        book_odds = {}
        for mid_str, mdata in markets.items():
            outcomes = mdata.get('outcomes', {})
            for oid, odata in outcomes.items():
                players = odata.get('players', {})
                for pid, pdata in players.items():
                    price = pdata.get('price')
                    if oid in OUTCOME_MAP:
                        book_odds[OUTCOME_MAP[oid]] = price
        result[bookmaker] = book_odds
    return result


def main():
    engine = WorldCupEngine()
    engine.load_data()

    all_data = []

    for cache_home, engine_home, cache_away, engine_away, hora in MATCHES:
        match_name = f"{cache_home} vs {cache_away}"
        fid = FIXTURE_IDS[match_name]

        print(f"\n{'='*60}")
        print(f"  {match_name} ({hora} CET)")
        print(f"{'='*60}")

        # Predicción del motor
        r = engine.predict_match(engine_home, engine_away)
        p = r['probabilities']
        eg = r['expected_goals']
        total_xg = eg['home'] + eg['away']

        # Probabilidades del modelo para Over/BTTS
        ov15 = over_prob(total_xg, 1)
        ov25 = over_prob(total_xg, 2)
        ov35 = over_prob(total_xg, 3)

        btts_h = 1 - math.exp(-eg['home'])
        btts_a = 1 - math.exp(-eg['away'])
        btts = btts_h * btts_a
        btts_adj = btts * (1 - 0.15 * (1 - btts))

        print(f"  xG: {eg['home']:.2f} - {eg['away']:.2f} (total {total_xg:.2f})")
        print(f"  1X2 modelo: H={p['home']:.1f}% D={p['draw']:.1f}% A={p['away']:.1f}%")
        print(f"  Narrativa: {r.get('narrative', '?')}")

        # Cuotas reales
        odds = fetch_odds(fid)
        time.sleep(1.5)

        b365 = odds.get('bet365', {})
        pin = odds.get('pinnacle', {})

        print(f"\n  Cuotas bet365:")
        if b365:
            print(f"    1X2: {b365.get('home','?')} / {b365.get('draw','?')} / {b365.get('away','?')}")
            print(f"    Over 1.5: {b365.get('over_15','?')} | Over 2.5: {b365.get('over_25','?')} | Over 3.5: {b365.get('over_35','?')}")
            print(f"    BTTS Yes: {b365.get('btts_yes','?')} | BTTS No: {b365.get('btts_no','?')}")

        # Edges vs bet365
        print(f"\n  EDGES vs bet365:")
        model_probs = {
            'home': p['home'] / 100, 'draw': p['draw'] / 100, 'away': p['away'] / 100,
            'over_15': ov15, 'over_25': ov25, 'over_35': ov35,
            'btts_yes': btts_adj,
        }
        odds_map = {
            'home': 'home', 'draw': 'draw', 'away': 'away',
            'over_15': 'over_15', 'over_25': 'over_25', 'over_35': 'over_35',
            'btts_yes': 'btts_yes',
        }
        labels = {
            'home': f'{cache_home} gana', 'draw': 'Empate', 'away': f'{cache_away} gana',
            'over_15': 'Over 1.5 goles', 'over_25': 'Over 2.5 goles', 'over_35': 'Over 3.5 goles',
            'btts_yes': 'BTTS Yes',
        }

        edges = {}
        for key, okey in odds_map.items():
            our_p = model_probs[key]
            book_odds = b365.get(okey)
            if book_odds and our_p > 0:
                implied = 1 / book_odds
                edge = (our_p - implied) * 100
                edges[key] = edge
                flag = '🟢VALUE' if edge > 5 else ('🟡' if edge > 2 else ('🔴' if edge < -5 else '⚪'))
                print(f"    {labels[key]}: modelo={our_p*100:.1f}% cuota={book_odds} edge={edge:+.1f}% {flag}")

        all_data.append({
            'match_name': match_name,
            'cache_home': cache_home,
            'cache_away': cache_away,
            'hora': hora,
            'probabilities': p,
            'expected_goals': eg,
            'model_probs': model_probs,
            'odds_bet365': b365,
            'odds_pinnacle': pin,
            'edges': edges,
            'narrative': r.get('narrative', ''),
        })

    # ===== COMBINADAS =====
    print(f"\n{'='*60}")
    print(f"  COMBINADAS")
    print(f"{'='*60}")

    # Para cada combinada, seleccionamos patas con edges positivos
    # SEGURA: dobles oportunidades + over 1.5 (alta probabilidad)
    # MEDIA: resultados 1X2 + over 2.5 (probabilidad media)
    # SOÑADORA: resultados arriesgados + over 3.5 / BTTS (baja probabilidad)

    for combo_name, risk_level in [("SEGURA", "safe"), ("MEDIA", "medium"), ("SOÑADORA", "dream")]:
        legs = []
        total_prob = 1.0
        total_odds = 1.0

        for md in all_data:
            b365 = md['odds_bet365']
            edges = md['edges']
            mp = md['model_probs']

            if risk_level == "safe":
                # Doble oportunidad (favorito) o Over 1.5
                best_edge = -999
                best_bet = None
                best_odds = None
                best_prob = 0

                # Opción 1: Over 1.5
                if 'over_15' in edges and b365.get('over_15'):
                    if edges['over_15'] > best_edge:
                        best_edge = edges['over_15']
                        best_bet = f"Over 1.5 goles"
                        best_odds = b365['over_15']
                        best_prob = mp['over_15']

                # Opción 2: Doble oportunidad (1X o X2 según favorito)
                if mp['home'] > mp['away']:
                    # 1X
                    home_odds = b365.get('home', 0)
                    draw_odds = b365.get('draw', 0)
                    if home_odds and draw_odds:
                        dx_odds = (home_odds * draw_odds) / (home_odds + draw_odds)
                        dx_prob = mp['home'] + mp['draw']
                        dx_edge = (dx_prob - 1/dx_odds) * 100
                        if dx_edge > best_edge:
                            best_edge = dx_edge
                            best_bet = f"Doble oportunidad 1X"
                            best_odds = dx_odds
                            best_prob = dx_prob
                else:
                    # X2
                    away_odds = b365.get('away', 0)
                    draw_odds = b365.get('draw', 0)
                    if away_odds and draw_odds:
                        dx_odds = (away_odds * draw_odds) / (away_odds + draw_odds)
                        dx_prob = mp['away'] + mp['draw']
                        dx_edge = (dx_prob - 1/dx_odds) * 100
                        if dx_edge > best_edge:
                            best_edge = dx_edge
                            best_bet = f"Doble oportunidad X2"
                            best_odds = dx_odds
                            best_prob = dx_prob

                if best_bet:
                    legs.append({
                        'match': md['match_name'],
                        'bet': best_bet,
                        'odds': round(best_odds, 2),
                        'prob': best_prob,
                        'edge': best_edge,
                    })
                    total_prob *= best_prob
                    total_odds *= best_odds

            elif risk_level == "medium":
                # Resultado 1X2 del favorito + Over 2.5
                best_edge = -999
                best_bet = None
                best_odds = None
                best_prob = 0

                # Opción 1: Favorito gana
                if mp['home'] > mp['away']:
                    if 'home' in edges and b365.get('home'):
                        if edges['home'] > best_edge:
                            best_edge = edges['home']
                            best_bet = f"{md['cache_home']} gana"
                            best_odds = b365['home']
                            best_prob = mp['home']
                else:
                    if 'away' in edges and b365.get('away'):
                        if edges['away'] > best_edge:
                            best_edge = edges['away']
                            best_bet = f"{md['cache_away']} gana"
                            best_odds = b365['away']
                            best_prob = mp['away']

                # Opción 2: Over 2.5
                if 'over_25' in edges and b365.get('over_25'):
                    if edges['over_25'] > best_edge:
                        best_edge = edges['over_25']
                        best_bet = "Over 2.5 goles"
                        best_odds = b365['over_25']
                        best_prob = mp['over_25']

                # Opción 3: BTTS Yes
                if 'btts_yes' in edges and b365.get('btts_yes'):
                    if edges['btts_yes'] > best_edge:
                        best_edge = edges['btts_yes']
                        best_bet = "BTTS Yes"
                        best_odds = b365['btts_yes']
                        best_prob = mp['btts_yes']

                if best_bet:
                    legs.append({
                        'match': md['match_name'],
                        'bet': best_bet,
                        'odds': round(best_odds, 2),
                        'prob': best_prob,
                        'edge': best_edge,
                    })
                    total_prob *= best_prob
                    total_odds *= best_odds

            elif risk_level == "dream":
                # Underdog gana o Over 3.5 o BTTS
                best_edge = -999
                best_bet = None
                best_odds = None
                best_prob = 0

                # Opción 1: Underdog gana
                if mp['home'] <= mp['away']:
                    if 'home' in edges and b365.get('home'):
                        if edges['home'] > best_edge:
                            best_edge = edges['home']
                            best_bet = f"{md['cache_home']} gana (sorpresa)"
                            best_odds = b365['home']
                            best_prob = mp['home']
                else:
                    if 'away' in edges and b365.get('away'):
                        if edges['away'] > best_edge:
                            best_edge = edges['away']
                            best_bet = f"{md['cache_away']} gana (sorpresa)"
                            best_odds = b365['away']
                            best_prob = mp['away']

                # Opción 2: Over 3.5
                if 'over_35' in edges and b365.get('over_35'):
                    if edges['over_35'] > best_edge:
                        best_edge = edges['over_35']
                        best_bet = "Over 3.5 goles"
                        best_odds = b365['over_35']
                        best_prob = mp['over_35']

                # Opción 3: Empate
                if 'draw' in edges and b365.get('draw'):
                    if edges['draw'] > best_edge:
                        best_edge = edges['draw']
                        best_bet = "Empate"
                        best_odds = b365['draw']
                        best_prob = mp['draw']

                if best_bet:
                    legs.append({
                        'match': md['match_name'],
                        'bet': best_bet,
                        'odds': round(best_odds, 2),
                        'prob': best_prob,
                        'edge': best_edge,
                    })
                    total_prob *= best_prob
                    total_odds *= best_odds

        ev = (total_prob * total_odds - 1) * 100 if total_odds > 0 else 0
        print(f"\n  🔵 {combo_name} (cuota {total_odds:.2f}, prob {total_prob*100:.1f}%, EV {ev:+.1f}%)")
        for leg in legs:
            print(f"    {leg['match']}: {leg['bet']} @ {leg['odds']} (edge {leg['edge']:+.1f}%)")
        print(f"    10€ -> {total_odds*10:.2f}€")

    # Guardar datos para la web
    with open('data/today_analysis.json', 'w') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    print(f"\nDatos guardados en data/today_analysis.json")


if __name__ == '__main__':
    main()
