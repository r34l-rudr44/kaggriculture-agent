"""Strategy fingerprint of both players in every recorded game (replayed exactly from the tapes).
python scout/fingerprint.py [WORKERS]  -> results/fingerprints.json (one row per player-game)"""
import collections, glob, json, os, sys
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREM = ("STRAWBERRY", "MILK", "WOOL", "MELON", "TOMATO", "EGG")
MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
IDLE = MOVES | {"PASS", "PICKUP", "DROP"}


def snapshot(farm):
    c = collections.Counter()
    for row in farm["tiles"]:
        for t in row:
            if isinstance(t, dict):
                if t.get("kind") == "PLANT":
                    c["plant_" + t["crop"]] += 1
                elif t.get("animal"):
                    c["animal_" + t["animal"]] += 1
    c["quads"] = len(farm.get("unlocked_quadrants", []))
    c["hands"] = len(farm.get("hands", []))
    c["money"] = farm["money"]
    return c


def game(ep, override=None):
    """override = (seat, agent path): that seat is played by our agent against the other seat's recording."""
    sys.path.insert(0, ROOT); os.chdir(ROOT)
    import fastsim, tapes, pinshops, ledger
    if not getattr(fastsim.K, "_ledger_on", False):
        ledger.install(); fastsim.K._ledger_on = True
    pinshops.install(fastsim.K)
    t = tapes.load(ep)
    snaps = {}
    a0, a1 = tapes.TapeAgent(ep, 0), tapes.TapeAgent(ep, 1)
    played = {0: [], 1: []}
    if override is not None:
        from tourney import load_agent
        seat_o, path = override
        mine = load_agent(path)

        def ours(obs, cfg=None):
            act = mine(obs, cfg); played[seat_o].append(act); return act
        if seat_o == 0:
            a0 = ours
        else:
            a1 = ours

    def spy(obs, cfg=None):
        if obs["step"] % 24 == 0 and obs["step"] // 24 in (1, 5, 10, 15, 20, 25):
            snaps[obs["step"] // 24] = [snapshot(obs["farms"][p]) for p in (0, 1)]
        return a0(obs, cfg)
    pinshops.pin(pinshops.recorded_shops(ep)); ledger.LOG.clear()
    r, st = fastsim.play(spy, a1, t["seed"]); pinshops.unpin()
    ids = [id(f) for f in st[0].observation.farms]
    rows = []
    for p in (0, 1):
        f = collections.Counter()
        f["coins"] = r[p]; f["win"] = int(r[p] > r[1 - p]); f["margin"] = r[p] - r[1 - p]
        for d, sn in snaps.items():
            for k, v in sn[p].items():
                f[f"{k}_d{d}"] = v
        for step, fid, op, item, delta in ledger.LOG:
            if fid != ids[p]:
                continue
            d = step // 24
            if op == "SELL":
                f["rev_" + item] += delta
                f[f"rev_days{min(d // 10, 2)}"] += delta
                if item in PREM:
                    f[f"prem_units_h{(step % 24) // 6}"] += 1
            elif op == "HIRE":
                f["cost_hire"] += -delta; f["hires"] += 1
            elif op == "LAND":
                f["cost_land"] += -delta; f.setdefault("land_day1", d) if "land_day1" not in f else f.setdefault("land_day2", d)
            else:
                f[f"cost_{op}_{item}"] += -delta
                if d == 0:
                    f[f"open_{op}_{item}"] += -delta
        stream = played[p] if played[p] else [acts[p] for acts in t["actions"]]
        for step, a in enumerate(stream):
            a = a or {}
            d = step // 24
            if 10 <= d <= 25:
                for u in [a.get("farmer") or ["PASS"]] + list(a.get("hands") or []):
                    k = u[0] if u else "PASS"
                    f["act_move" if k in MOVES else ("act_pass" if k == "PASS" else ("act_shed" if k in IDLE else "act_prod"))] += 1
                    if k in ("WATER", "HARVEST", "CARE", "FEED", "FERTILIZE", "PLANT", "COLLECT_FERTILIZER"):
                        f["act_" + k] += 1
        for k in [k for k in f if k.startswith("act_")]:
            f[k] /= 16.0
        n = sum(f[f"prem_units_h{h}"] for h in range(4)) or 1
        for h in range(4):
            f[f"prem_share_h{h}"] = f[f"prem_units_h{h}"] / n
        name = "OURS" if override is not None and p == override[0] else t["names"][p]
        rows.append({"ep": ep, "seat": p, "team": name, "opp": t["names"][1 - p], "feat": dict(f)})
    return rows


if __name__ == "__main__":
    out_path = os.path.join(ROOT, "results", "fingerprints.json")
    done = json.load(open(out_path)) if os.path.exists(out_path) else []
    have = {r["ep"] for r in done}
    eps = [os.path.basename(f)[:-5] for f in glob.glob(os.path.join(ROOT, "tapes", "*.json"))
           if not f.endswith((".shops.json", ".units.json"))]
    eps = [e for e in eps if e not in have]
    with ProcessPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 3) as ex:
        for rows in ex.map(game, eps, chunksize=4):
            done += rows
    json.dump(done, open(out_path, "w"))
    print("fingerprinted", len(done) // 2, "games")
