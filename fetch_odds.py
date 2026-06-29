#!/usr/bin/env python3
"""
fetch_odds.py — Obtiene cuotas reales de OddsPapi para el Mundial 2026
Guarda caché en data/odds_cache.json

Uso: python fetch_odds.py
       — trae todas las cuotas (31 fixtures) ~32 peticiones
     python fetch_odds.py --today
       — solo partidos de hoy/mañana

Gasta ~30 peticiones/mes si se ejecuta 1 vez al día (de 250 disponibles).
"""

import json
import sys
import os
import time
from pathlib import Path
from datetime import date, timedelta
import requests

BASE_DIR = Path(__file__).parent
KEY_FILE = BASE_DIR / ".oddspapi_key"
CACHE_FILE = BASE_DIR / "data" / "odds_cache.json"
TOURNAMENT_ID = 16  # World Cup
BASE_URL = "https://api.oddspapi.io/v4"
BOOKMAKERS = ["bet365", "pinnacle"]  # Los que nos interesan

MARKET_LABELS = {"101": "home", "102": "draw", "103": "away"}

# Mercados de córners y bookings que nos interesan
# Corners Over/Under: IDs 10767-10843, Bookings Over/Under: IDs 10914-10970
CORNERS_OU_RANGE = range(10767, 10844)
BOOKINGS_OU_RANGE = range(10914, 10971)
EXTRA_MARKET_RANGES = [CORNERS_OU_RANGE, BOOKINGS_OU_RANGE]

# Córners 1X2 y Bookings 1X2 (si están disponibles)
EXTRA_MARKET_IDS = ['10764', '10911']

def market_id_to_line(market_id, base):
    """Convierte ID de mercado OddsPapi a línea (ej: 10803 → 9.5 para córners)"""
    return 0.5 + (int(market_id) - base) / 4

def market_id_info(market_id):
    """Devuelve (stat_key, line) o (None, None)"""
    mid = int(market_id)
    if mid in CORNERS_OU_RANGE:
        return 'cornerKicks', market_id_to_line(mid, 10767)
    elif mid in BOOKINGS_OU_RANGE:
        return 'yellowCards', market_id_to_line(mid, 10914)
    elif str(mid) in EXTRA_MARKET_IDS:
        return 'special', None
    return None, None


def load_key():
    if not KEY_FILE.exists():
        print(f"ERROR: No se encuentra {KEY_FILE}")
        print("Crea el archivo con tu API key de OddsPapi (sin espacios)")
        sys.exit(1)
    return KEY_FILE.read_text().strip()


def fetch_fixtures(api_key):
    """Obtiene todos los fixtures del Mundial"""
    url = f"{BASE_URL}/fixtures"
    params = {
        "apiKey": api_key,
        "tournamentId": TOURNAMENT_ID,
        "from": "2026-06-29",
        "to": "2026-07-20",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_odds(api_key, fixture_id):
    """Obtiene odds de un fixture"""
    url = f"{BASE_URL}/odds"
    params = {"apiKey": api_key, "fixtureId": fixture_id}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def extract_odds(odds_data):
    """Extrae solo los bookmakers que nos interesan (1X2 + córners + bookings)"""
    result = {}
    bom = odds_data.get("bookmakerOdds", {})
    for slug in BOOKMAKERS:
        if slug in bom:
            markets = bom[slug].get("markets", {})
            result[slug] = {}
            # 1X2
            if "101" in markets:
                outcomes = markets["101"].get("outcomes", {})
                result[slug]["1x2"] = {}
                for oid, o in outcomes.items():
                    label = MARKET_LABELS.get(oid, oid)
                    price = o.get("players", {}).get("0", {}).get("price")
                    result[slug]["1x2"][label] = price
            # Córners y Bookings Over/Under
            for mid, mdata in markets.items():
                stat_key, line = market_id_info(mid)
                if stat_key is None or line is None:
                    continue
                outcomes = mdata.get("outcomes", {})
                for oid, odata in outcomes.items():
                    oid_int = int(oid)
                    side = "over" if oid_int > int(mid) else "under"
                    price = odata.get("players", {}).get("0", {}).get("price")
                    if stat_key not in result[slug]:
                        result[slug][stat_key] = {}
                    line_str = f"{side}_{line}"
                    result[slug][stat_key][line_str] = price
    return result


def main():
    api_key = load_key()
    today_only = "--today" in sys.argv

    # Cargar caché existente
    cache = {}
    if CACHE_FILE.exists():
        cache = json.loads(CACHE_FILE.read_text())

    print("📡 Buscando fixtures del Mundial...")
    fixtures = fetch_fixtures(api_key)
    print(f"   {len(fixtures)} fixtures encontrados")

    if today_only:
        today_str = date.today().isoformat()
        tomorrow_str = (date.today() + timedelta(days=2)).isoformat()
        fixtures = [
            f
            for f in fixtures
            if today_str <= (f.get("startTime", "")[:10]) <= tomorrow_str
        ]
        print(f"   {len(fixtures)} en los próximos 2 días")

    fetched = 0
    skipped = 0
    total = len(fixtures)

    for f in fixtures:
        fid = f["fixtureId"]
        home = f.get("participant1Name", "?")
        away = f.get("participant2Name", "?")
        start = f.get("startTime", "")[:16]
        has_odds = f.get("hasOdds", False)

        # Guardar info básica del fixture siempre
        cache[fid] = {
            "home": home,
            "away": away,
            "start": start,
            "odds": cache.get(fid, {}).get("odds", None),
            "updated": cache.get(fid, {}).get("updated", None),
        }

        if not has_odds:
            print(f"   ⏳ {home} vs {away} — sin cuotas aún")
            skipped += 1
            continue

        print(f"   🔄 {home} vs {away}...", end=" ", flush=True)
        try:
            odds = fetch_odds(api_key, fid)
            extracted = extract_odds(odds)
            cache[fid]["odds"] = extracted
            cache[fid]["updated"] = date.today().isoformat()
            books = list(extracted.keys())
            print(f"OK ({len(odds.get('bookmakerOdds',{}))} books, {', '.join(books)})")
            fetched += 1
        except Exception as e:
            print(f"ERROR: {e}")
            skipped += 1
            time.sleep(2)  # Esperar tras error 429

        # Respetar rate limit: 1 petición/segundo
        time.sleep(1.5)

    # Guardar caché
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Listo: {fetched} actualizadas, {skipped} saltadas, {total} total")
    print(f"   Caché: {CACHE_FILE}")
    print(f"   Peticiones API gastadas: ~{fetched + 1} de 250/mes")


if __name__ == "__main__":
    main()
