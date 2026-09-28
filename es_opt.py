"""Evolution-strategy search over agent parameters against the validated objective.

python es_opt.py --agent agents/v10.py --gens 25 --pop 10 --workers 10 --tag es1

Objective (development data only): mean margin (our coins minus opponent coins) over
  * the pinned seat test on top50_dev.json tapes (town shops pinned; only games where the frozen side
    keeps >= 95% of its recorded coins when the base agent plays, fixed once so every candidate plays
    the same games), and
  * the sparring pool in poolset.json on `pool_seeds` development seeds x both seats.
The search is a separable CMA-style ES in a normalized [0, 1] box with antithetic sampling and
rank-based weights. Progress is appended to results/es_<tag>.jsonl; the best point so far is written to
results/es_<tag>_best.json.
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


def _game(job):
    kind, agent_path, params, spec = job
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    import fastsim, tapes, pinshops
    from tourney import load_agent
    pinshops.install(fastsim.K)
    me = load_agent(agent_path, params)
    _crn(fastsim.K, kind == "pool")
    if kind == "seat":
        ep, seat = spec
        t = tapes.load(ep)
        agents = [tapes.TapeAgent(ep, 0), tapes.TapeAgent(ep, 1)]
        agents[seat] = me
        pinshops.pin(pinshops.recorded_shops(ep))
        r, _ = fastsim.play(agents[0], agents[1], t["seed"])
        pinshops.unpin()
        return r[seat] - r[1 - seat], r[1 - seat], t["rewards"][1 - seat]
    opp_path, seed, seat = spec
    opp = load_agent(opp_path)
    agents = [None, None]
    agents[seat], agents[1 - seat] = me, opp
    r, _ = fastsim.play(agents[0], agents[1], seed)
    return r[seat] - r[1 - seat], None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="agents/v10.py")
    ap.add_argument("--gens", type=int, default=25)
    ap.add_argument("--pop", type=int, default=10)
    ap.add_argument("--sigma", type=float, default=0.15)
    ap.add_argument("--pool_seeds", type=int, default=8)
    ap.add_argument("--seed0", type=int, default=16000)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--tag", default="es")
    a = ap.parse_args()
    rng = random.Random(7)
    agent = os.path.join(ROOT, a.agent)
    pool = [os.path.join(ROOT, f) for f in json.load(open(os.path.join(ROOT, "poolset.json")))]
    eps = sorted({e for e in json.load(open(os.path.join(ROOT, "top50_dev.json"))) if os.path.exists(os.path.join(ROOT, "tapes", f"{e}.json"))})

    ex = ProcessPoolExecutor(a.workers)
    # Fix the seat-game subset once: games whose frozen side keeps >= 95% when the base agent plays.
    seat_specs = [(ep, s) for ep in eps for s in (0, 1)]
    base_seat = list(ex.map(_game, [("seat", agent, None, sp) for sp in seat_specs], chunksize=1))
    seat_specs = [sp for sp, r in zip(seat_specs, base_seat) if r[1] >= 0.95 * r[2]]
    pool_specs = [(o, a.seed0 + k, s) for o in pool for k in range(a.pool_seeds) for s in (0, 1)]

    def objective(params):
        jobs = [("seat", agent, params, sp) for sp in seat_specs] + [("pool", agent, params, sp) for sp in pool_specs]
        res = list(ex.map(_game, jobs, chunksize=1))
        seat = [r[0] for r in res[: len(seat_specs)]]
        pl = [r[0] for r in res[len(seat_specs):]]
        return 0.5 * sum(seat) / len(seat) + 0.5 * sum(pl) / len(pl), sum(seat) / len(seat), sum(pl) / len(pl)

    import importlib.util
    spec = importlib.util.spec_from_file_location("base_agent", agent)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    defaults = mod.DEFAULT_PARAMS
    mean = encode({n: defaults[n] for n, *_ in SPACE})
    sig = [a.sigma] * len(SPACE)
    base_f = objective(None)
    log_path = os.path.join(ROOT, "results", f"es_{a.tag}.jsonl")
    best = {"f": base_f[0], "seat": base_f[1], "pool": base_f[2], "params": decode(mean), "gen": 0}
    with open(log_path, "a") as fh:
        fh.write(json.dumps({"gen": 0, "baseline": base_f, "n_seat": len(seat_specs), "n_pool": len(pool_specs)}) + "\n")
    print(f"baseline f={base_f[0]:.0f} seat={base_f[1]:.0f} pool={base_f[2]:.0f} (seat games {len(seat_specs)}, pool games {len(pool_specs)})", flush=True)

    half = a.pop // 2
    wts = [math.log(half + 0.5) - math.log(i + 1) for i in range(half)]
    wts = [w / sum(wts) for w in wts]
    for gen in range(1, a.gens + 1):
        cands = []
        for _ in range(half):
            eps_v = [rng.gauss(0, 1) for _ in SPACE]
            for sgn in (1, -1):
                z = [m + sgn * s * e for m, s, e in zip(mean, sig, eps_v)]
                cands.append((z, [sgn * e for e in eps_v]))
        scored = []
        for z, e in cands:
            f = objective(decode(z))
            scored.append((f, z, e))
        scored.sort(key=lambda t: -t[0][0])
        top = scored[:half]
        new_mean = [sum(w * t[1][i] for w, t in zip(wts, top)) for i in range(len(SPACE))]
        # separable step-size update from the spread of the selected points
        for i in range(len(SPACE)):
            spread = math.sqrt(sum(w * ((t[1][i] - mean[i]) / max(1e-9, sig[i])) ** 2 for w, t in zip(wts, top)))
            sig[i] = min(0.35, max(0.03, sig[i] * math.exp(0.2 * (spread - 1.0))))
        mean = [min(1.0, max(0.0, x)) for x in new_mean]
        f_best, z_best, _ = scored[0]
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
