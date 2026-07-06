import json
cache = json.load(open("data/odds_cache.json"))
targets = ["portugal","spain","usa","belgium","argentina","egypt","switzerland","colombia"]
for k, v in cache.items():
    h = v.get("home", "")
    a = v.get("away", "")
    combined = (h + " " + a).lower()
    if any(t in combined for t in targets):
        print(f"\n{'='*60}")
        print(f"MATCH: {h} vs {a} | date={v.get('start')} | key={k}")
        odds = v.get("odds", {})
        for bookie in ["bet365", "pinnacle"]:
            b = odds.get(bookie, {})
            if not b:
                continue
            x12 = b.get("1x2", {})
            print(f"  [{bookie}] 1X2: H={x12.get('home')} D={x12.get('draw')} A={x12.get('away')}")
            for field in ["over_15","over_25","over_35","over_45","btts_yes","btts_no"]:
                if field in b:
                    print(f"  [{bookie}] {field}={b[field]}")
            ck = b.get("cornerKicks", {})
            if ck:
                print(f"  [{bookie}] CK: {json.dumps(ck)}")
            yc = b.get("yellowCards", {})
            if yc:
                print(f"  [{bookie}] YC: {json.dumps(yc)}")
