"""What wins? Paired models over strategy fingerprints (results/fingerprints.json).
python scout/learn.py [--top10 top10_recent.json] -> printed report + results/learn_report.json
Only decision features are used (openings, farm mix over time, land, hires, spending, sale timing, labour);
revenue, coins and cash are outcomes and are left out."""
import collections, json, math, os, sys
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUR = {n for n in ("TX", os.environ.get("KAGG_TEAM_NAME", "")) if n}  # our seat labels
OUTCOME = ("coins", "win", "margin", "rev_", "money_")


def load():
    rows = json.load(open(os.path.join(ROOT, "results", "fingerprints.json")))
    games = collections.defaultdict(dict)
    for r in rows:
        games[r["ep"]][r["seat"]] = r
    games = {e: g for e, g in games.items() if len(g) == 2 and g[0]["feat"]["win"] + g[1]["feat"]["win"] == 1}
    keys = sorted({k for r in rows for k in r["feat"] if not k.startswith(OUTCOME)})
    return games, keys


def logit_fit(X, y, lam):
    w = np.zeros(X.shape[1])
    for _ in range(50):  # Newton steps on the L2-penalised log-likelihood (no intercept: the pairs are antisymmetric)
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) + lam * w
        H = (X * (p * (1 - p))[:, None]).T @ X + lam * np.eye(X.shape[1])
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-6:
            break
    return w


def auc(s, y):
    order = np.argsort(s); r = np.empty(len(s)); r[order] = np.arange(1, len(s) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / max(1, n1 * n0)


def main():
    games, keys = load()
    eps = sorted(games)
    F = lambda r: np.array([float(r["feat"].get(k, 0.0)) for k in keys])
    D = np.array([F(games[e][0]) - F(games[e][1]) for e in eps])
    y = np.array([games[e][0]["feat"]["win"] for e in eps], float)
    sd = D.std(0) + 1e-9
    Z = D / sd
    # antisymmetric augmentation: each game from both players' side
    Xa, ya = np.vstack([Z, -Z]), np.concatenate([y, 1 - y])
    rep = {"n_games": len(eps), "n_features": len(keys)}
    print(f"games {len(eps)}, decision features {len(keys)}")
    # univariate: in how many games does the player with MORE of the feature win?
    uni = []
    for j, k in enumerate(keys):
        m = D[:, j] != 0
        if m.sum() < 60:
            continue
        hw = ((D[m, j] > 0) == (y[m] == 1)).mean()
        uni.append((k, hw, math.sqrt(hw * (1 - hw) / m.sum()), int(m.sum())))
    uni.sort(key=lambda t: -abs(t[1] - 0.5))
    print("\nMORE-OF-FEATURE WINS (share of games the player with more wins; SE; n)")
    for k, hw, se, n in uni[:30]:
        print(f"  {k:32s} {hw:.3f} ({se:.3f})  n={n}")
    rep["univariate"] = uni
    # cross-validated L2 logistic model, folds by game
    rng = np.random.default_rng(0); fold = rng.integers(0, 5, len(eps))
    for lam in (3.0, 30.0, 300.0):
        s = np.zeros(len(eps))
        for f in range(5):
            tr, te = fold != f, fold == f
            w = logit_fit(np.vstack([Z[tr], -Z[tr]]), np.concatenate([y[tr], 1 - y[tr]]), lam)
            s[te] = Z[te] @ w
        print(f"\nlogistic lam={lam:5.0f}: CV AUC {auc(s, y):.3f}  accuracy {((s > 0) == (y == 1)).mean():.3f}")
    w = logit_fit(Xa, ya, 30.0)
    top = sorted(zip(keys, w), key=lambda t: -abs(t[1]))[:25]
    print("\nMODEL WEIGHTS (per SD of the feature difference; + = helps winning), lam=30")
    for k, v in top:
        print(f"  {k:32s} {v:+.3f}")
    rep["weights"] = sorted(zip(keys, w.tolist()), key=lambda t: -abs(t[1]))
    # players: our agent and the top-10 teams, profile vs their opponents
    top10 = {}
    if os.path.exists(os.path.join(ROOT, "top10_recent.json")):
        for r in json.load(open(os.path.join(ROOT, "top10_recent.json"))):
            top10[r["team"]] = r["score"]
    focus = [k for k, _ in top[:15]]
    for label, names in (("OUR AGENT", OUR), *(((f"TOP-10 {t} ({s:.0f})", {t}) for t, s in sorted(top10.items(), key=lambda x: -x[1])))):
        g = [(e, s) for e in eps for s in (0, 1) if games[e][s]["team"] in names]
        if len(g) < 4:
            continue
        wins = sum(games[e][s]["feat"]["win"] for e, s in g)
        print(f"\n{label}: {wins}-{len(g) - wins} in {len(g)} games; mean feature diff vs opponent, wins / losses")
        for k in focus:
            j = keys.index(k)
            dw = [(1 if s == 0 else -1) * D[eps.index(e), j] for e, s in g if games[e][s]["feat"]["win"]]
            dl = [(1 if s == 0 else -1) * D[eps.index(e), j] for e, s in g if not games[e][s]["feat"]["win"]]
            print(f"    {k:32s} wins {np.mean(dw) if dw else float('nan'):+9.2f}   losses {np.mean(dl) if dl else float('nan'):+9.2f}")
    json.dump(rep, open(os.path.join(ROOT, "results", "learn_report.json"), "w"))


if __name__ == "__main__":
    main()
