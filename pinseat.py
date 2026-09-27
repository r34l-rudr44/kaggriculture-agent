"""Seat test against top players with the town pinned to the recording.

python pinseat.py CAND.py [--params JSON] [--base BASE.py] [--set top50_dev.json] [--workers 10] [--tag T]
For each recorded game in the set and each seat, the candidate replaces that seat and plays the frozen
other side on the recorded seed with the recorded shops. Games where the frozen side keeps less than 95%
of its recorded coins (its recording broke) are dropped for both agents. Reports margin (candidate minus
frozen side), wins and own coins, paired against the base agent (default agents/v8.py) with per-game SE.
"""
import argparse, json, math, os, sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))


def _run(job):
    path, params, ep, seat = job
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    import fastsim, tapes, pinshops
    from tourney import load_agent
    pinshops.install(fastsim.K)
    shops = pinshops.recorded_shops(ep)
    t = tapes.load(ep)
    agents = [tapes.TapeAgent(ep, 0), tapes.TapeAgent(ep, 1)]
    agents[seat] = load_agent(path, params)
    pinshops.pin(shops)
    r, _ = fastsim.play(agents[0], agents[1], t["seed"])
    pinshops.unpin()
    return ep, seat, r[seat], r[1 - seat], t["rewards"][1 - seat]


def evaluate(path, params, eps, workers):
    jobs = [(path, params, ep, s) for ep in eps for s in (0, 1)]
    with ProcessPoolExecutor(workers) as ex:
        return {(r[0], r[1]): r for r in ex.map(_run, jobs, chunksize=1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cand")
    ap.add_argument("--params", default=None)
    ap.add_argument("--base", default=os.path.join("agents", "v8.py"))
    ap.add_argument("--set", default="top50_dev.json")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--tag", default="pinseat")
    a = ap.parse_args()
    eps = sorted(set(json.load(open(a.set))))
    eps = [e for e in eps if os.path.exists(os.path.join(ROOT, "tapes", f"{e}.json"))]
    params = json.loads(a.params) if a.params else None
    cache = os.path.join(ROOT, "results", f"pinseat_base_{os.path.basename(a.base)[:-3]}_{os.path.basename(a.set)[:-5]}.json")
    if os.path.exists(cache):
        base = {tuple(json.loads(k)): v for k, v in json.load(open(cache)).items()}
    else:
        base = evaluate(a.base, None, eps, a.workers)
        json.dump({json.dumps(list(k)): v for k, v in base.items()}, open(cache, "w"))
    cand = evaluate(a.cand, params, eps, a.workers)
    keys = [k for k in cand if k in base and cand[k][3] >= 0.95 * cand[k][4] and base[k][3] >= 0.95 * base[k][4]]
    n = len(keys)
    d = [(cand[k][2] - cand[k][3]) - (base[k][2] - base[k][3]) for k in keys]
    own = [cand[k][2] - base[k][2] for k in keys]
    mean = lambda v: sum(v) / max(1, len(v))
    se = lambda v: math.sqrt(sum((x - mean(v)) ** 2 for x in v) / max(1, len(v) - 1)) / math.sqrt(max(1, len(v)))
    bw = sum(1 for k in keys if base[k][2] > base[k][3])
    cw = sum(1 for k in keys if cand[k][2] > cand[k][3])
    bm = mean([base[k][2] - base[k][3] for k in keys])
    cm = mean([cand[k][2] - cand[k][3] for k in keys])
    print(f"PINSEAT {a.tag}: n={n} valid of {len(cand)}  margin base {bm:+.0f} cand {cm:+.0f}  diff {mean(d):+.0f} (SE {se(d):.0f})"
          f"  own diff {mean(own):+.0f} (SE {se(own):.0f})  wins {bw} -> {cw}")
    json.dump({json.dumps(list(k)): v for k, v in cand.items()}, open(os.path.join(ROOT, "results", f"pinseat_{a.tag}.json"), "w"))


if __name__ == "__main__":
    main()
