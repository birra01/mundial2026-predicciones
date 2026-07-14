#!/usr/bin/env python3
"""
completa_all_matches.py — Rellena data/worldcup/all_matches.json con los partidos
REALES de España y Francia en el Mundial 2026 usando la API de Sofascore
(que ya usa el motor). No usa web_search ni datos a mano.

Para cada partido: descarga marcador (event/{id}) y estadísticas
(event/{id}/statistics) y los escribe en el formato que espera engine.py.
Mezcla con lo existente (no borra nada) y salva backup.
"""
import json, os, shutil, time, requests
from pathlib import Path

BASE = Path(__file__).parent
MATCHES = BASE / "data" / "worldcup" / "all_matches.json"
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
TID, SID = 16, 58210
TARGETS = {"Spain", "France"}

# Mapa de nombres Sofascore -> clave interna del motor
NAME_MAP = {
    "Spain": "Spain", "France": "France",
}


def get_all_events():
    events = []
    seen = set()
    for page in list(range(5)) + ["next"]:
        try:
            if page == "next":
                url = f"https://api.sofascore.com/api/v1/unique-tournament/{TID}/season/{SID}/events/next/0"
            else:
                url = f"https://api.sofascore.com/api/v1/unique-tournament/{TID}/season/{SID}/events/last/{page}"
            r = requests.get(url, headers=H, timeout=15)
            if r.status_code != 200:
                if page == "next":
                    break
                continue
            evs = r.json().get("events", [])
            if not evs and page != "next":
                break
            for e in evs:
                if e["id"] not in seen:
                    seen.add(e["id"])
                    events.append(e)
        except Exception as ex:
            print(f"  ⚠️ page {page}: {ex}")
        time.sleep(0.3)
    return events


def fetch_event(eid):
    r = requests.get(f"https://api.sofascore.com/api/v1/event/{eid}", headers=H, timeout=15)
    if r.status_code != 200:
        return None
    return r.json().get("event", {})


def fetch_stats(eid):
    r = requests.get(f"https://api.sofascore.com/api/v1/event/{eid}/statistics", headers=H, timeout=15)
    if r.status_code != 200:
        return None
    return r.json().get("statistics", [])


def main():
    events = get_all_events()
    print(f"Eventos del torneo obtenidos: {len(events)}")

    # Filtrar partidos de España/Francia
    target_events = [
        e for e in events
        if e.get("homeTeam", {}).get("name") in NAME_MAP
        and e.get("awayTeam", {}).get("name") in NAME_MAP
    ]
    print(f"Partidos España/Francia: {len(target_events)}")

    # Cargar existentes
    existing = json.load(open(MATCHES)) if MATCHES.exists() else []
    by_id = {m.get("id"): m for m in existing}

    added = 0
    for e in target_events:
        eid = e["id"]
        home = e["homeTeam"]["name"]
        away = e["awayTeam"]["name"]
        # ¿ya existe con stats?
        if eid in by_id and by_id[eid].get("statistics"):
            print(f"  ✓ ya existe con stats: {home} vs {away}")
            continue
        ev = fetch_event(eid)
        if not ev:
            continue
        hs = ev.get("homeScore", {}).get("normaltime")
        aw = ev.get("awayScore", {}).get("normaltime")
        status = ev.get("status", {}).get("description")
        if hs is None or aw is None:
            print(f"  ⏭ sin marcador aún: {home} vs {away} ({status})")
            time.sleep(0.3)
            continue
        stats = fetch_stats(eid)
        entry = {
            "id": eid,
            "home_team": home,
            "away_team": away,
            "home_score": hs,
            "away_score": aw,
            "start_timestamp": ev.get("startTimestamp", e.get("startTimestamp")),
            "round": ev.get("roundInfo", {}).get("round"),
            "status": status,
            "statistics": stats if stats else [],
        }
        by_id[eid] = entry
        added += 1
        print(f"  + {home} {hs}-{aw} {away} (stats: {'SÍ' if stats else 'NO'})")
        time.sleep(0.5)  # rate limiting

    # Backup y guardado
    if added:
        backup = MATCHES.with_suffix(".json.bak_api")
        shutil.copy(MATCHES, backup)
        allm = list(by_id.values())
        json.dump(allm, open(MATCHES, "w"), ensure_ascii=False, indent=1)
        print(f"\n✅ Añadidos {added} partidos reales. Total en all_matches: {len(allm)}")
        print(f"   Backup: {backup.name}")
    else:
        print("\nNada que añadir (todos ya presentes con stats).")

    # Resumen forma por equipo
    for eq in TARGETS:
        ps = [m for m in by_id.values() if m.get("home_team") == eq or m.get("away_team") == eq]
        print(f"\n{eq}: {len(ps)} partidos en all_matches")
        for m in ps:
            print(f"  {m.get('home_team')} {m.get('home_score')}-{m.get('away_score')} {m.get('away_team')} | stats:{'SÍ' if m.get('statistics') else 'NO'}")


if __name__ == "__main__":
    main()
