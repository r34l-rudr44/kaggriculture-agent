"""Population rating: round-robin among a pool of reactive agents, fitted with Bradley-Terry.

python poolbt.py --pool agents/v4.py agents/v5_script.py ... [--seeds 24] [--workers 10] [--tag NAME]
Every pair plays `seeds` seeds x both seats (common random numbers for weeds/shops). Ratings are
reported on an Elo-like scale (400 * log10 odds), anchored so the pool mean is 0, with bootstrap SE.
"""
import argparse, itertools, json, math, os, random, sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))


def _crn(K):
    if getattr(K, "_crn_patched", False):
        return
    orig = K._spawn_weeds
    count = {}

    def spawn(farm, board_size, weed_chance, rng):
        key = tuple(rng.getstate()[1][:4])
        k = count.get(key, 0)
        count[key] = k + 1
        return orig(farm, board_size, weed_chance, random.Random(hash((key, k))))

    K._spawn_weeds = spawn
    K._crn_patched = True


def _game(job):
    a, b, pa, pb, seed = job
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    import fastsim
    from tourney import load_agent
    _crn(fastsim.K)
    r, _ = fastsim.play(load_agent(a, pa), load_agent(b, pb), seed)
    return r[0], r[1]


def fit_bt(names, games, iters=300):
    """games: list of (i, j, score_i) with score 1/0.5/0. Returns ratings (Elo scale, mean 0)."""
    n = len(names)
    w = [0.0] * n
    wins = [[0.0] * n for _ in range(n)]
    cnt = [[0] * n for _ in range(n)]
    for i, j, s in games:
        wins[i][j] += s
        wins[j][i] += 1 - s
        cnt[i][j] += 1
        cnt[j][i] += 1
    p = [1.0] * n
    for _ in range(iters):  # minorization-maximization (Hunter 2004), with a tiny prior for stability
        new = []
        for i in range(n):
            num = sum(wins[i]) + 0.5
            den = sum(cnt[i][j] / (p[i] + p[j]) for j in range(n) if cnt[i][j]) + 1.0 / (p[i] + 1.0)
            new.append(num / den)
        g = math.exp(sum(math.log(x) for x in new) / n)
        p = [x / g for x in new]
    return [400 * math.log10(x) for x in p]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", nargs="+", required=True, help="agent files; append ::JSON for params")
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--seed0", type=int, default=12000)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--tag", default="pool")
    a = ap.parse_args()
    entries = []
    for e in a.pool:
        path, _, js = e.partition("::")
        entries.append((path, json.loads(js) if js else None, os.path.basename(path)[:-3] + (js and "+" + js or "")))
    names = [x[2] for x in entries]
    jobs, meta = [], []
    for i, j in itertools.combinations(range(len(entries)), 2):
        for s in range(a.seed0, a.seed0 + a.seeds):
            for swap in (False, True):
                x, y = (j, i) if swap else (i, j)
                jobs.append((entries[x][0], entries[y][0], entries[x][1], entries[y][1], s))
                meta.append((x, y, s))
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(_game, jobs, chunksize=2))
    games = []
    margins = {}
    for (x, y, s), (rx, ry) in zip(meta, res):
        sc = 1.0 if rx > ry else (0.5 if rx == ry else 0.0)
        games.append((x, y, sc))
        margins.setdefault((min(x, y), max(x, y)), []).append((rx - ry) if x < y else (ry - rx))
    ratings = fit_bt(names, games)
    rng = random.Random(1)
    boots = []
    for _ in range(200):
        boots.append(fit_bt(names, [games[rng.randrange(len(games))] for _ in games], iters=120))
    se = [math.sqrt(sum((b[k] - sum(bb[k] for bb in boots) / len(boots)) ** 2 for b in boots) / len(boots)) for k in range(len(names))]
    order = sorted(range(len(names)), key=lambda k: -ratings[k])
    print(f"pool of {len(names)}, {len(games)} games")
    for k in order:
        print(f"  {names[k]:40s} {ratings[k]:+7.0f}  (SE {se[k]:.0f})")
    print("pairwise score (row vs col):")
    for i in order:
        row = []
        for j in order:
            if i == j:
                row.append("   -  ")
                continue
            gs = [s if x == i else 1 - s for x, y, s in games if {x, y} == {i, j}]
            row.append(f"{sum(gs)/len(gs):6.2f}")
        print(f"  {names[i][:14]:14s} " + " ".join(row))
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    json.dump({"names": names, "ratings": ratings, "se": se, "games": games}, open(os.path.join(ROOT, "results", f"pool_{a.tag}.json"), "w"))


if __name__ == "__main__":
    main()
