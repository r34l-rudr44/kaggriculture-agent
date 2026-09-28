"""Evolution-strategy search over agent parameters against the validated objective.

python es_opt.py --agent agents/v12.py --set top50_dev2.json --keep units --soft 3000 --w_seat 0.7 --tag es2

Objective (development data only), a weighted mean over
  * the pinned seat test on the --set tapes (town shops pinned; the seat games are fixed once from the
    base agent's run: with --keep units those where the frozen side completes its recorded transactions,
    with --keep coins those where it keeps >= 95% of its recorded coins), and
  * the sparring pool in poolset.json on `pool_seeds` development seeds x both seats.
Each game scores its margin (our coins minus the opponent's), or with --soft S the soft win S*tanh(margin/S),
which counts close games most: the ladder rates wins, not margins. A seat game whose recording breaks for a
candidate keeps the base agent's score. The search is a separable CMA-style ES in a normalized [0, 1] box
with antithetic sampling and rank-based weights; each generation is played as one batch. Progress is
appended to results/es_<tag>.jsonl; the best point so far is written to results/es_<tag>_best.json.
"""
import argparse, json, math, os, random, sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))

SPACE = [  # name, low, high, integer?
    ("herd_rival_weight", 0.0, 1.2, False),
    ("herd_labor", 4.0, 24.0, False),
    ("buy_block_frac", 0.10, 0.60, False),
    ("maint_frac", 0.15, 0.50, False),
    ("book_alt", 10.0, 45.0, False),
    ("book_labor", 30.0, 100.0, False),
    ("tom_min_price", 60.0, 110.0, False),
    ("room_mult", 0.8, 1.8, False),
    ("w_dist", 12.0, 30.0, False),
    ("eve_harv", 10.0, 60.0, False),
    ("collect_base", 30.0, 80.0, False),
    ("fert_wheat_ratio", 1.0, 2.4, False),
    ("hold_risk", 0.001, 0.006, False),
    ("wave_cap", 6, 16, True),
    ("sheep_cap", 10, 22, True),
    ("cow_cap", 8, 16, True),
    ("pen_fert_cover", 0.2, 0.9, False),
]


def decode(z):
    p = {}
    for (name, lo, hi, is_int), v in zip(SPACE, z):
        x = lo + min(1.0, max(0.0, v)) * (hi - lo)
        p[name] = int(round(x)) if is_int else round(x, 4)
    return p


def encode(params):
    return [(params[n] - lo) / (hi - lo) for n, lo, hi, _ in SPACE]


_WEED_DRAWS = {}


def _crn(K, on):
    """Pool games draw weeds from their own seeded stream, so neither agent's field shifts the other's weeds or
    the shop draws; the draw counter is cleared before every game so a replayed seed gets the same weeds.
    Seat games run on the unpatched engine, as the recorded games did."""
    if not hasattr(K, "_orig_spawn_weeds"):
        K._orig_spawn_weeds = K._spawn_weeds
    orig = K._orig_spawn_weeds

    def spawn(farm, board_size, weed_chance, rng):
        key = tuple(rng.getstate()[1][:4])
        k = _WEED_DRAWS.get(key, 0)
        _WEED_DRAWS[key] = k + 1
        return orig(farm, board_size, weed_chance, random.Random(hash((key, k))))

    K._spawn_weeds = spawn if on else orig
    _WEED_DRAWS.clear()


def _game(job, tries=3):
    for k in range(tries):
        try:
            return _play(job)
        except OSError:  # a transient file error must not end a day-long search
            if k == tries - 1:
                raise


def _play(job):
    kind, agent_path, params, spec = job
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    import fastsim, pinshops
    from tourney import load_agent
    pinshops.install(fastsim.K)
    _crn(fastsim.K, kind == "pool")
    if "ledger" in sys.modules:  # the seat test's transaction log would otherwise grow with every pool game
        sys.modules["ledger"].LOG.clear()
    if kind == "seat":
        import pinseat
        ep, seat = spec
        _, _, me, op, rec, intact = pinseat._run((agent_path, params, ep, seat))
        return me - op, op >= 0.95 * rec, intact
    opp_path, seed, seat = spec
    agents = [None, None]
    agents[seat], agents[1 - seat] = load_agent(agent_path, params), load_agent(opp_path)
    r, _ = fastsim.play(agents[0], agents[1], seed)
    return r[seat] - r[1 - seat], True, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="agents/v12.py")
    ap.add_argument("--set", default="top50_dev.json")
    ap.add_argument("--keep", default="units", choices=["units", "coins"])
    ap.add_argument("--soft", type=float, default=0.0)
    ap.add_argument("--w_seat", type=float, default=0.5)
    ap.add_argument("--gens", type=int, default=25)
    ap.add_argument("--pop", type=int, default=10)
    ap.add_argument("--sigma", type=float, default=0.15)
    ap.add_argument("--pool_seeds", type=int, default=8)
    ap.add_argument("--seed0", type=int, default=16000)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--tag", default="es")
    ap.add_argument("--resume", action="store_true", help="continue from the mean and step sizes last logged under --tag")
    a = ap.parse_args()
    rng = random.Random(7)
    agent = os.path.join(ROOT, a.agent)
    pool = [os.path.join(ROOT, f) for f in json.load(open(os.path.join(ROOT, "poolset.json")))]
    eps = sorted({e for e in json.load(open(os.path.join(ROOT, a.set))) if os.path.exists(os.path.join(ROOT, "tapes", f"{e}.json"))})
    score = (lambda m: a.soft * math.tanh(m / a.soft)) if a.soft > 0 else (lambda m: m)
    kept = (lambda r: r[2]) if a.keep == "units" else (lambda r: r[1])

    ex = ProcessPoolExecutor(a.workers)
    seat_specs = [(ep, s) for ep in eps for s in (0, 1)]
    base_seat = list(ex.map(_game, [("seat", agent, None, sp) for sp in seat_specs], chunksize=1))
    base_seat, seat_specs = zip(*[(r, sp) for sp, r in zip(seat_specs, base_seat) if kept(r)])
    pool_specs = [(o, a.seed0 + k, s) for o in pool for k in range(a.pool_seeds) for s in (0, 1)]

    def evaluate(batch):
        """(objective, seat mean, pool mean) of each params dict in the batch, played as one map."""
        jobs = [("seat", agent, p, sp) for p in batch for sp in seat_specs] + \
               [("pool", agent, p, sp) for p in batch for sp in pool_specs]
        res = list(ex.map(_game, jobs, chunksize=1))
        n_s, n_p = len(seat_specs), len(pool_specs)
        out = []
        for i in range(len(batch)):
            seat = [score(r[0] if kept(r) else b[0]) for r, b in zip(res[i * n_s:(i + 1) * n_s], base_seat)]
            pl = [score(r[0]) for r in res[len(batch) * n_s + i * n_p:len(batch) * n_s + (i + 1) * n_p]]
            ms, mp = sum(seat) / n_s, sum(pl) / n_p
            out.append((a.w_seat * ms + (1 - a.w_seat) * mp, ms, mp))
        return out

    import importlib.util
    spec = importlib.util.spec_from_file_location("base_agent", agent)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    defaults = mod.DEFAULT_PARAMS
    mean = encode({n: defaults[n] for n, *_ in SPACE})
    sig = [a.sigma] * len(SPACE)
    log_path = os.path.join(ROOT, "results", f"es_{a.tag}.jsonl")
    start = 1
    if a.resume:
        log = [json.loads(l) for l in open(log_path)]
        base_f = log[0]["baseline"]
        last = log[-1]
        mean, sig, start = encode(last["mean_params"]), last["sigma"], last["gen"] + 1
        best_path = os.path.join(ROOT, "results", f"es_{a.tag}_best.json")
        best = json.load(open(best_path)) if os.path.exists(best_path) else \
            {"f": base_f[0], "seat": base_f[1], "pool": base_f[2], "params": decode(mean), "gen": 0}
        rng = random.Random(7 + start)
        print(f"resumed at gen {start}, best so far {best['f']:.0f}", flush=True)
    else:
        base_f = evaluate([None])[0]
        best = {"f": base_f[0], "seat": base_f[1], "pool": base_f[2], "params": decode(mean), "gen": 0}
        with open(log_path, "a") as fh:
            fh.write(json.dumps({"gen": 0, "baseline": base_f, "n_seat": len(seat_specs), "n_pool": len(pool_specs),
                                 "args": vars(a)}) + "\n")
        print(f"baseline f={base_f[0]:.0f} seat={base_f[1]:.0f} pool={base_f[2]:.0f} (seat games {len(seat_specs)}, pool games {len(pool_specs)})", flush=True)

    half = a.pop // 2
    wts = [math.log(half + 0.5) - math.log(i + 1) for i in range(half)]
    wts = [w / sum(wts) for w in wts]
    for gen in range(start, a.gens + 1):
        cands = []
        for _ in range(half):
            eps_v = [rng.gauss(0, 1) for _ in SPACE]
            for sgn in (1, -1):
                cands.append([m + sgn * s * e for m, s, e in zip(mean, sig, eps_v)])
        scored = sorted(zip(evaluate([decode(z) for z in cands]), cands), key=lambda t: -t[0][0])
        top = scored[:half]
        new_mean = [sum(w * t[1][i] for w, t in zip(wts, top)) for i in range(len(SPACE))]
        # separable step-size update from the spread of the selected points
        for i in range(len(SPACE)):
            spread = math.sqrt(sum(w * ((t[1][i] - mean[i]) / max(1e-9, sig[i])) ** 2 for w, t in zip(wts, top)))
            sig[i] = min(0.35, max(0.03, sig[i] * math.exp(0.2 * (spread - 1.0))))
        mean = [min(1.0, max(0.0, x)) for x in new_mean]
        f_best, z_best = scored[0]
        if f_best[0] > best["f"]:
            best = {"f": f_best[0], "seat": f_best[1], "pool": f_best[2], "params": decode(z_best), "gen": gen}
            json.dump(best, open(os.path.join(ROOT, "results", f"es_{a.tag}_best.json"), "w"), indent=1)
        with open(log_path, "a") as fh:
            fh.write(json.dumps({"gen": gen, "best_gen": f_best, "best_so_far": best["f"], "mean_params": decode(mean),
                                 "sigma": [round(s, 3) for s in sig]}) + "\n")
        print(f"gen {gen}: best_gen f={f_best[0]:.0f} (seat {f_best[1]:.0f}, pool {f_best[2]:.0f})  best_so_far {best['f']:.0f} (+{best['f'] - base_f[0]:.0f} vs base)", flush=True)
    ex.shutdown()


if __name__ == "__main__":
    main()
