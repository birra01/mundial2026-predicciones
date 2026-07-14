#!/usr/bin/env python3
"""
backtest_mundial.py — Balance de acierto del motor sobre partidos YA JUGADOS.

NO usa cuotas. Solo responde: "de las apuestas que el bot HABRIA hecho, ¿cuales
se ganaron y cuales no?" -> win rate por mercado.

Para cada partido real en data/real_stats.json:
  1. Filtra all_matches.json a partidos ANTERIORES (sin data leakage / look-ahead).
  2. Calcula fuerzas de equipo con compute_team_averages (solo datos previos).
  3. Para cada mercado predice total y elige el lado (Over/Under) con mas conviccion.
  4. Compara con el resultado real -> acierto o no.
  5. Acumula por mercado.

Genera data/learning/backtest_winrate.json y learning_dashboard.html.
"""
import json, math, sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent / "src"))
from value_bets import (
    compute_team_averages, adjusted_prediction, over_prob,
    PREDICTABLE_STATS, EVALUATION_LINES,
)

DATA = Path(__file__).parent / "data"
ALL = json.load(open(DATA / "worldcup" / "all_matches.json"))
REAL = json.load(open(DATA / "real_stats.json"))

# Separar partidos reales jugados
REAL_MATCHES = {k: v for k, v in REAL.items()
                if not k.startswith("_") and not v.get("_blocked")}

# Map: nombre de partido real -> timestamp del partido en all_matches
match_ts = {}
for m in ALL:
    key = f"{m['home_team']} vs {m['away_team']}"
    match_ts[key] = m.get("start_timestamp", 0)


def norm(s):
    return (s.lower()
            .replace("é", "e").replace("á", "a").replace("í", "i")
            .replace("ó", "o").replace("ú", "u").replace(" vs ", " vs ").strip())


def find_match_ts(home, away):
    """Busca el timestamp del partido real en all_matches (con alias minimo)."""
    for key, ts in match_ts.items():
        kh, ka = key.split(" vs ")
        if norm(kh) == norm(home) and norm(ka) == norm(away):
            return ts
        if norm(kh) == norm(away) and norm(ka) == norm(home):
            return ts
    return None


def real_total_for(stat_key, real):
    """Devuelve el TOTAL real del stat para comparar con la linea."""
    block = real.get(stat_key)
    if isinstance(block, dict) and "total" in block:
        return block["total"]
    return None


def pick_side(total_pred, line):
    """Elige Over/Under segun la conviccion del modelo para esa linea."""
    p_over = over_prob(total_pred, line)  # 0..1
    p_under = 1 - p_over
    if p_over >= p_under:
        return "over", round(p_over * 100, 1), line
    return "under", round(p_under * 100, 1), line


# Acumuladores por mercado
stats_acc = defaultdict(lambda: {"bets": 0, "wins": 0, "detail": []})


def main():
    for mname, real in REAL_MATCHES.items():
        home, away = mname.split(" vs ")
        ts = find_match_ts(home, away)
        if ts is None:
            print(f"  [skip] sin timestamp en all_matches: {mname}")
            continue

        # 1. Solo partidos ANTERIORES
        prev = [m for m in ALL if m.get("start_timestamp", 0) < ts]
        if len(prev) < 3:
            print(f"  [skip] pocos partidos previos ({len(prev)}): {mname}")
            continue

        team_stats = compute_team_averages(prev)

        if home not in team_stats or away not in team_stats:
            print(f"  [skip] equipo sin datos previos: {mname}")
            continue

        # 2-3. Por cada mercado, elegir lado con mas conviccion
        for stat_key, sinfo in PREDICTABLE_STATS.items():
            rt = real_total_for(stat_key, real)
            if rt is None:
                continue  # no hay resultado real de este stat

            pred_h, pred_a = adjusted_prediction(team_stats, home, away, stat_key)
            total_pred = pred_h + pred_a
            if total_pred < 0.5:
                continue

            # Elegir la linea donde el modelo tenga MAYOR conviccion (mayor |p-50|)
            best = None
            for line in EVALUATION_LINES.get(stat_key, []):
                side, prob, ln = pick_side(total_pred, line)
                conv = abs(prob - 50.0)
                if best is None or conv > best["conv"]:
                    best = {"side": side, "prob": prob, "line": ln, "conv": conv}

            if best is None:
                continue

            # 4. Comparar con resultado real
            # Over/Under sobre el TOTAL del partido
            won = (best["side"] == "over" and rt > best["line"]) or \
                  (best["side"] == "under" and rt < best["line"])
            # Empate exacto en la linea (raro en .5) -> no cuenta como acierto
            if rt == best["line"]:
                won = False

            acc = stats_acc[stat_key]
            acc["bets"] += 1
            if won:
                acc["wins"] += 1
            acc["detail"].append({
                "match": mname,
                "line": best["line"],
                "side": best["side"],
                "prob": best["prob"],
                "real_total": rt,
                "won": won,
            })

    # 5. Reporte
    print("\n" + "=" * 60)
    print("  BACKTEST MUNIAL 2026 — BALANCE DE ACIERTO (sin cuotas)")
    print("=" * 60)
    total_bets = sum(a["bets"] for a in stats_acc.values())
    total_wins = sum(a["wins"] for a in stats_acc.values())
    print(f"  Partidos evaluados: {len(REAL_MATCHES)}")
    print(f"  Apuestas simuladas: {total_bets}")
    print(f"  Aciertos:           {total_wins}")
    print(f"  Win rate global:    {total_wins/total_bets*100:.1f}%" if total_bets else "  n/a")
    print(f"\n  {'MERCADO':<16}{'APUESTAS':>9}{'ACIERTOS':>10}{'WIN%':>8}")
    print("  " + "-" * 43)
    for sk, acc in sorted(stats_acc.items(), key=lambda x: -x[1]["wins"]/max(x[1]["bets"],1)):
        label = PREDICTABLE_STATS.get(sk, {}).get("label", sk)
        wr = acc["wins"] / acc["bets"] * 100 if acc["bets"] else 0
        icon = "✅" if wr >= 50 else "❌"
        print(f"  {icon} {label:<14}{acc['bets']:>9}{acc['wins']:>10}{wr:>7.1f}%")

    # Guardar JSON
    out = {
        "total_bets": total_bets,
        "total_wins": total_wins,
        "global_winrate": round(total_wins / total_bets * 100, 1) if total_bets else 0,
        "by_market": {
            sk: {
                "bets": acc["bets"],
                "wins": acc["wins"],
                "win_rate": round(acc["wins"] / acc["bets"] * 100, 1) if acc["bets"] else 0,
                "detail": acc["detail"],
            }
            for sk, acc in stats_acc.items()
        },
    }
    (DATA / "learning").mkdir(exist_ok=True)
    with open(DATA / "learning" / "backtest_winrate.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n  Guardado: data/learning/backtest_winrate.json")

    return out


if __name__ == "__main__":
    main()
