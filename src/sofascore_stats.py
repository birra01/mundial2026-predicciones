"""
sofascore_stats.py — Cliente para obtener estadísticas reales de partidos
desde la API de Sofascore (usada ya por engine.py).

Uso:
    from sofascore_stats import SofascoreStatsClient
    
    client = SofascoreStatsClient()
    
    # Obtener IDs de partidos de una fecha
    matches = client.get_matches_by_date('2026-06-29')
    # => [{'id': 12813012, 'home': 'Brazil', 'away': 'Japan', ...}, ...]
    
    # Obtener estadísticas de un partido
    stats = client.get_match_stats(12813012)
    # => {'cornerKicks': {'home': 6, 'away': 2, 'total': 8}, ...}
"""
import json
import time
import requests
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "data" / "sofascore_cache"
SOFASCORE_BASE = "https://api.sofascore.com/api/v1"
TOURNAMENT_ID = 16
SEASON_ID = 58210
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

# Mapeo de keys de Sofascore → nuestras keys internas
STAT_KEY_MAP = {
    'cornerKicks': 'cornerKicks',
    'yellowCards': 'yellowCards',
    'totalShots': 'totalShotsOnGoal',
    'onTargetShots': 'shotsOnGoal',
    'fouls': 'fouls',
    'expectedGoals': 'expectedGoals',
    'ballPossession': 'ballPossession',
}


class SofascoreStatsClient:
    """Cliente con caché para estadísticas de partidos de Sofascore."""
    
    def __init__(self, cache_dir=None):
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _cache_path(self, event_id):
        return self.cache_dir / f"event_{event_id}.json"
    
    def _load_cache(self, event_id):
        path = self._cache_path(event_id)
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                # Caché válida 1 hora
                if time.time() - data.get('_cached_at', 0) < 3600:
                    return data.get('stats')
            except (json.JSONDecodeError, KeyError):
                pass
        return None
    
    def _save_cache(self, event_id, stats):
        with open(self._cache_path(event_id), 'w') as f:
            json.dump({'_cached_at': time.time(), 'stats': stats}, f)
    
    def get_matches_by_date(self, date_str):
        """
        Obtiene los partidos de una fecha desde Sofascore.
        date_str: '2026-06-29'
        Retorna lista de {id, home_team, away_team, time, round}
        """
        url = f"{SOFASCORE_BASE}/unique-tournament/{TOURNAMENT_ID}/season/{SEASON_ID}/events/next/0"
        
        # Intentar last/0 primero (partidos ya jugados)
        all_events = []
        for page in range(3):  # last/0, last/1, last/2
            try:
                resp = requests.get(
                    f"{SOFASCORE_BASE}/unique-tournament/{TOURNAMENT_ID}/season/{SEASON_ID}/events/last/{page}",
                    headers=HEADERS, timeout=10
                )
                if resp.status_code != 200:
                    break
                events = resp.json().get('events', [])
                if not events:
                    break
                all_events.extend(events)
            except Exception:
                break
            time.sleep(0.3)
        
        # También probar next/0
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                next_events = resp.json().get('events', [])
                all_events.extend(next_events)
        except Exception:
            pass
        
        matches = []
        seen_ids = set()
        for e in all_events:
            eid = e.get('id')
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            
            ts = e.get('startTimestamp', 0)
            dt = datetime.fromtimestamp(ts)
            if dt.strftime('%Y-%m-%d') == date_str:
                matches.append({
                    'id': eid,
                    'home_team': e.get('homeTeam', {}).get('name', '?'),
                    'away_team': e.get('awayTeam', {}).get('name', '?'),
                    'time': dt.strftime('%H:%M'),
                    'round': e.get('roundInfo', {}).get('round', '?'),
                    'status': e.get('status', {}).get('description', '?'),
                })
        
        return matches
    
    def get_match_stats(self, event_id, force_refresh=False):
        """
        Obtiene estadísticas de un partido desde Sofascore.
        
        Retorna dict con todas las stats mapeadas:
        {
            'cornerKicks': {'home': 6, 'away': 2, 'total': 8},
            'yellowCards': {'home': 2, 'away': 3, 'total': 5},
            'totalShotsOnGoal': {'home': 19, 'away': 5, 'total': 24},
            'shotsOnGoal': {'home': 7, 'away': 2, 'total': 9},
            'fouls': {'home': 4, 'away': 13, 'total': 17},
            'expectedGoals': {'home': 2.07, 'away': 0.33, 'total': 2.40},
            'ballPossession': {'home': 62, 'away': 38},
            # ... y cualquier otra stat que devuelva la API
        }
        
        Retorna None si el partido está bloqueado (403) o no tiene estadísticas.
        """
        # Intentar caché primero
        if not force_refresh:
            cached = self._load_cache(event_id)
            if cached is not None:
                return cached
        
        url = f"{SOFASCORE_BASE}/event/{event_id}/statistics"
        
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
        except requests.RequestException as e:
            print(f"  ⚠️ Error de red para event {event_id}: {e}")
            return None
        
        if resp.status_code == 403:
            print(f"  🔒 Event {event_id} bloqueado (403 Forbidden) — posible restricción geográfica")
            return None
        
        if resp.status_code != 200:
            print(f"  ⚠️ Event {event_id}: HTTP {resp.status_code}")
            return None
        
        data = resp.json()
        statistics = data.get('statistics', [])
        
        if not statistics:
            print(f"  ⚡ Event {event_id}: sin datos de estadísticas")
            return None
        
        result = {}
        
        for period in statistics:
            if period.get('period') != 'ALL':
                continue
            
            for group in period.get('groups', []):
                for item in group.get('statisticsItems', []):
                    key = item.get('key', '')
                    home_val = item.get('homeValue')
                    away_val = item.get('awayValue')
                    
                    # Guardar con key original
                    if home_val is not None or away_val is not None:
                        hv = home_val if home_val is not None else 0
                        av = away_val if away_val is not None else 0
                        total = hv + av if isinstance(hv, (int, float)) and isinstance(av, (int, float)) else None
                        result[key] = {
                            'home': hv,
                            'away': av,
                            'total': total
                        }
        
        # Guardar en caché
        self._save_cache(event_id, result)
        
        return result
    
    def get_match_stats_mapped(self, event_id, force_refresh=False):
        """
        Como get_match_stats pero devuelve solo las stats que nos interesan,
        mapeadas a nuestras keys internas.
        """
        raw = self.get_match_stats(event_id, force_refresh)
        if not raw:
            return None
        
        mapped = {}
        for sofascore_key, our_key in STAT_KEY_MAP.items():
            if sofascore_key in raw:
                mapped[our_key] = raw[sofascore_key]
        
        return mapped


# ─── Función de conveniencia ────────────────────────────────────────
def fetch_match_stats_for_date(date_str='2026-06-29'):
    """
    Obtiene estadísticas de todos los partidos de una fecha.
    Retorna {match_id: {stats_mapped, home_team, away_team}}
    """
    client = SofascoreStatsClient()
    matches = client.get_matches_by_date(date_str)
    
    results = {}
    for m in matches:
        eid = m['id']
        stats = client.get_match_stats_mapped(eid)
        results[eid] = {
            'home_team': m['home_team'],
            'away_team': m['away_team'],
            'time': m['time'],
            'status': m['status'],
            'stats': stats
        }
        time.sleep(0.5)  # rate limiting
    
    return results
