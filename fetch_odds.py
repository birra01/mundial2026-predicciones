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
    """Extrae solo los bookmakers que nos interesan"""
    result = {}
    bom = odds_data.get("bookmakerOdds", {})
    for slug in BOOKMAKERS:
        if slug in bom:
            markets = bom[slug].get("markets", {})
            if "101" in markets:
                outcomes = markets["101"].get("outcomes", {})
                result[slug] = {}
                for oid, o in outcomes.items():
                    label = MARKET_LABELS.get(oid, oid)
                    price = o.get("players", {}).get("0", {}).get("price")
                    result[slug][label] = price
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
