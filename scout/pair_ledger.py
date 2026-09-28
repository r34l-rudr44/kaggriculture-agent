"""Two agents in the same recorded seats (our seat of each episode, opponent frozen, shops pinned): ledgers side by side.
python scout/pair_ledger.py A.py B.py SET.json"""
import collections, json, os, sys
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUR = {n for n in ("TX", os.environ.get("KAGG_TEAM_NAME", "")) if n}  # our seat labels


def run(args):
    path, ep = args
    sys.path.insert(0, ROOT); os.chdir(ROOT)
    import fastsim, tapes, pinshops, ledger
    from tourney import load_agent
    if not getattr(fastsim.K, "_ledger_on", False):
        ledger.install(); fastsim.K._ledger_on = True
    pinshops.install(fastsim.K)
    t = tapes.load(ep); seat = 0 if t["names"][0] in OUR else 1
    ag = [tapes.TapeAgent(ep, 0), tapes.TapeAgent(ep, 1)]; ag[seat] = load_agent(path)
    pinshops.pin(pinshops.recorded_shops(ep)); ledger.LOG.clear()
    r, st = fastsim.play(ag[0], ag[1], t["seed"]); pinshops.unpin()
    ids = [id(f) for f in st[0].observation.farms]
    c = [collections.Counter(), collections.Counter()]
    for step, fid, op, item, delta in ledger.LOG:
        p = ids.index(fid)
        c[p][("rev " + item) if op == "SELL" else ("cost " + op + (" " + item if item else ""))] += delta
        c[p]["net d%02d-%02d" % (step // 24 // 5 * 5, step // 24 // 5 * 5 + 4)] += delta
    return ep, seat, r[seat], r[1 - seat], dict(c[seat]), dict(c[1 - seat]), t["names"][1 - seat], json.load(open(os.path.join(ROOT, "tapes", f"{ep}.shops.json")))[-1]


if __name__ == "__main__":
    A, B, S = sys.argv[1:4]
    eps = json.load(open(S))
    with ProcessPoolExecutor(6) as ex:
        ra = list(ex.map(run, [(A, e) for e in eps])); rb = list(ex.map(run, [(B, e) for e in eps]))
    for a, b in zip(ra, rb):
        print(f"\n{a[0]} vs {a[6]}  | {os.path.basename(A)}: {a[2]:.0f} - {a[3]:.0f}   {os.path.basename(B)}: {b[2]:.0f} - {b[3]:.0f}")
        print("   final shops:", a[7])
        keys = sorted(set(a[4]) | set(b[4]) | set(a[5]) | set(b[5]))
        rows = [(k, a[4].get(k, 0), b[4].get(k, 0), a[5].get(k, 0), b[5].get(k, 0)) for k in keys]
        for k, x, y, u, v in sorted(rows, key=lambda r: -abs((r[2] - r[1]) - (r[4] - r[3])))[:9]:
            print(f"   {k:26s} ours {x:8.0f} -> {y:8.0f} ({y - x:+6.0f})   opponent {u:8.0f} -> {v:8.0f} ({v - u:+6.0f})")
