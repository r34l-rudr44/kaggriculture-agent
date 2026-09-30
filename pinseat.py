"""Seat test against top players with the town pinned to the recording.

python pinseat.py CAND.py [--params JSON] [--base BASE.py] [--set top50_dev.json] [--workers 10] [--tag T]
For each recorded game in the set and each seat, the candidate replaces that seat and plays the frozen
other side on the recorded seed with the recorded shops. Games where the frozen side keeps less than 95%
of its recorded coins (its recording broke) are dropped for both agents. Reports margin (candidate minus
frozen side), wins and own coins, paired against the base agent (default agents/v8.py) with per-game SE.

--keep units instead drops a game only when the frozen side's recording broke: it completes fewer than 98% of
its recorded sales or of its other market and hiring transactions. A frozen side that earns less because the
candidate pressed its prices then still counts, which the coin filter would treat as a broken recording.
"""
import argparse, json, math, os, sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))


def read_json(path, tries=5):
    """json.load that rides out a transient read failure (another program briefly holding the file)."""
    import time
    for k in range(tries):
        try:
            with open(path) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            if k == tries - 1:
                raise
            time.sleep(0.2 * (k + 1))


def _units(state, seat):
    import ledger
    fid = id(state[0].observation.farms[seat])
    sold = sum(1 for e in ledger.LOG if e[1] == fid and e[2] == "SELL")
    other = sum(1 for e in ledger.LOG if e[1] == fid and e[2] != "SELL")
    return sold, other


def _recorded_units(ep):
    """Transactions of each side in the recorded game (cached next to the tape)."""
    import fastsim, tapes, pinshops, ledger
    cache = os.path.join(ROOT, "tapes", f"{ep}.units.json")
    if os.path.exists(cache):
        return read_json(cache)
    t = tapes.load(ep)
    pinshops.pin(pinshops.recorded_shops(ep))
    ledger.LOG.clear()
    _, st = fastsim.play(tapes.TapeAgent(ep, 0), tapes.TapeAgent(ep, 1), t["seed"])
    pinshops.unpin()
    u = [_units(st, 0), _units(st, 1)]
    tmp = f"{cache}.{os.getpid()}"
    json.dump(u, open(tmp, "w"))
    try:
        os.replace(tmp, cache)
    except OSError:  # another worker wrote the same cache first
        os.remove(tmp)
    return u


def _run(job):
    path, params, ep, seat = job
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    import fastsim, tapes, pinshops, ledger
    from tourney import load_agent
    if not getattr(fastsim.K, "_ledger_installed", False):
        ledger.install()
        fastsim.K._ledger_installed = True
    pinshops.install(fastsim.K)
    rec_units = _recorded_units(ep)[1 - seat]
    shops = pinshops.recorded_shops(ep)
    t = tapes.load(ep)
    agents = [tapes.TapeAgent(ep, 0), tapes.TapeAgent(ep, 1)]
    agents[seat] = load_agent(path, params)
    pinshops.pin(shops)
    ledger.LOG.clear()
    r, st = fastsim.play(agents[0], agents[1], t["seed"])
    pinshops.unpin()
    sold, other = _units(st, 1 - seat)
    intact = sold >= 0.98 * rec_units[0] and other >= 0.98 * rec_units[1]
    return ep, seat, r[seat], r[1 - seat], t["rewards"][1 - seat], intact


def seats_of(eps, only=None):
    """(episode, seat) pairs to play: both seats, or only the seats a team of `only` played in the recording."""
    if not only:
        return [(ep, s) for ep in eps for s in (0, 1)]
    import tapes
    return [(ep, s) for ep in eps for s in (0, 1) if tapes.load(ep)["names"][s] in only]


def evaluate(path, params, eps, workers, only=None):
    jobs = [(path, params, ep, s) for ep, s in seats_of(eps, only)]
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
    ap.add_argument("--keep", default="coins", choices=["coins", "units"])
    ap.add_argument("--only", default=None, help="comma-separated team names: replay only the seats they played")
    a = ap.parse_args()
    eps = sorted(set(json.load(open(a.set))))
    eps = [e for e in eps if os.path.exists(os.path.join(ROOT, "tapes", f"{e}.json"))]
    params = json.loads(a.params) if a.params else None
    only = set(a.only.split(",")) if a.only else None
    # the cache is keyed on the base file's content, so an edited base agent never reuses a stale baseline
    import hashlib
    tag = hashlib.sha1(open(a.base, "rb").read()).hexdigest()[:8]
    cache = os.path.join(ROOT, "results", f"pinseat_base_{os.path.basename(a.base)[:-3]}_{tag}_{os.path.basename(a.set)[:-5]}.json")
    if os.path.exists(cache):
        base = {tuple(json.loads(k)): v for k, v in json.load(open(cache)).items()}
        if a.keep == "units" and any(len(v) < 6 for v in base.values()):
            base = evaluate(a.base, None, eps, a.workers, only)
            json.dump({json.dumps(list(k)): v for k, v in base.items()}, open(cache, "w"))
    else:
        base = evaluate(a.base, None, eps, a.workers, only)
        json.dump({json.dumps(list(k)): v for k, v in base.items()}, open(cache, "w"))
    cand = evaluate(a.cand, params, eps, a.workers, only)
    if a.keep == "units":
        keys = [k for k in cand if k in base and cand[k][5] and base[k][5]]
    else:
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
