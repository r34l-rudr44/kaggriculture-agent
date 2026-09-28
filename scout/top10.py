"""Top-10 study: (1) the top-10 player vs v12 in the same seats, (2) what separates top-10 wins from losses,
(3) per-team profile. Inputs: results/fingerprints.json, results/v12_in_top10.json, top10_recent.json,
results/pinseat_t10_v12.json (which seats stayed intact with v12 in them)."""
import collections, json, math, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = lambda f: json.load(open(os.path.join(ROOT, f)))
FEATS = ["open_BUY_ANIMAL_COW", "open_BUY_ANIMAL_SHEEP", "open_BUY_SEED_MELON", "open_BUY_SEED_WHEAT", "open_BUY_SEED_STRAWBERRY",
         "animal_COW_d10", "animal_SHEEP_d10", "animal_GOOSE_d10", "animal_COW_d20", "animal_SHEEP_d20", "animal_GOOSE_d20",
         "plant_STRAWBERRY_d10", "plant_STRAWBERRY_d15", "plant_STRAWBERRY_d20", "plant_WHEAT_d15", "plant_TOMATO_d15",
         "plant_CARROT_d15", "plant_MELON_d10", "plant_MELON_d20", "quads_d10", "quads_d15", "quads_d20", "hires", "cost_hire",
         "cost_BUY_PRODUCT_WHEAT", "cost_BUY_PRODUCT_FERTILIZER", "cost_BUY_SEED_STRAWBERRY", "prem_units_h0", "prem_units_h1",
         "prem_units_h2", "prem_units_h3", "act_prod", "act_pass", "act_move", "act_shed", "act_WATER", "act_HARVEST", "act_CARE",
         "act_FEED", "act_FERTILIZE", "act_COLLECT_FERTILIZER", "act_PLANT", "rev_STRAWBERRY", "rev_MILK", "rev_WOOL", "rev_EGG",
         "rev_MELON", "rev_TOMATO", "rev_WHEAT", "rev_CARROT", "rev_FERTILIZER", "rev_days0", "rev_days1", "rev_days2", "coins"]


def ms(v):
    n = len(v)
    if n < 2:
        return (v[0] if v else float("nan")), float("nan")
    m = sum(v) / n
    return m, math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1) / n)


def main():
    fp = collections.defaultdict(dict)
    for r in R("results/fingerprints.json"):
        fp[r["ep"]][r["seat"]] = r["feat"]
    recs = R("top10_recent.json")
    ours = {(x["rec"]["ep"], x["rec"]["seat"]): {r["seat"]: r["feat"] for r in x["rows"]} for x in R("results/v12_in_top10.json")}
    intact = {tuple(json.loads(k)) for k, v in R("results/pinseat_t10_v12.json").items() if v[5]}
    # (1) same seat: top-10 player (recorded) vs v12, intact seats only
    keys = [(r["ep"], r["seat"]) for r in recs if (r["ep"], r["seat"]) in intact and r["ep"] in fp]
    print(f"(1) SAME SEAT, top-10 player vs v12, {len(keys)} intact seats. Recorded top-10 wins "
          f"{sum(fp[e][s]['win'] for e, s in keys)}, v12 wins {sum(ours[(e, s)][s]['win'] for e, s in keys)}")
    print(f"    {'feature':30s} {'top10':>9s} {'v12':>9s} {'diff':>9s} (SE)")
    rows = []
    for k in FEATS:
        a = [fp[e][s].get(k, 0) for e, s in keys]; b = [ours[(e, s)][s].get(k, 0) for e, s in keys]
        m, se = ms([x - y for x, y in zip(a, b)])
        rows.append((k, sum(a) / len(a), sum(b) / len(b), m, se))
    for k, a, b, m, se in rows:
        flag = " **" if se == se and se > 0 and abs(m) > 2.5 * se else ""
        print(f"    {k:30s} {a:9.1f} {b:9.1f} {m:+9.1f} ({se:.1f}){flag}")
    # opponent's coins in the same seat games: how much each suppresses the rival
    oa = [fp[e][1 - s]["coins"] for e, s in keys]; ob = [ours[(e, s)][1 - s]["coins"] for e, s in keys]
    print(f"    frozen opponent coins: facing top-10 {sum(oa)/len(oa):.0f}, facing v12 {sum(ob)/len(ob):.0f}")
    # (2) top-10 wins vs losses (recorded games), diff to the opponent
    print(f"\n(2) TOP-10 WINS vs LOSSES in {len(recs)} recorded games: mean (top10 - opponent) in wins, in losses")
    W = [r for r in recs if r["ep"] in fp and r["win"]]; L = [r for r in recs if r["ep"] in fp and not r["win"]]
    out = []
    for k in FEATS:
        dw = [fp[r["ep"]][r["seat"]].get(k, 0) - fp[r["ep"]][1 - r["seat"]].get(k, 0) for r in W]
        dl = [fp[r["ep"]][r["seat"]].get(k, 0) - fp[r["ep"]][1 - r["seat"]].get(k, 0) for r in L]
        (mw, sw), (ml, sl) = ms(dw), ms(dl)
        t = (mw - ml) / math.sqrt(sw ** 2 + sl ** 2) if sw == sw and sl == sl and sw + sl > 0 else 0
        out.append((k, mw, ml, t))
    for k, mw, ml, t in sorted(out, key=lambda x: -abs(x[3]))[:22]:
        print(f"    {k:30s} wins {mw:+9.1f}  losses {ml:+9.1f}   t={t:+.1f}")
    # who beats them
    print("\n    their losses were to:", collections.Counter(fp[r["ep"]] and r["team"] for r in L).most_common(10))
    # (3) per-team profile, key features
    print("\n(3) TEAM PROFILES (mean over their games): record | cows/sheep/geese d20 | straw d15 | quads d15 | prem units h0..h3 | act_prod act_pass")
    for team in sorted({r["team"] for r in recs}, key=lambda t: -next(r["score"] for r in recs if r["team"] == t)):
        g = [(r["ep"], r["seat"], r["win"]) for r in recs if r["team"] == team and r["ep"] in fp]
        f = lambda k: sum(fp[e][s].get(k, 0) for e, s, _ in g) / len(g)
        print(f"    {team[:22]:22s} {sum(w for *_, w in g)}-{sum(not w for *_, w in g)} | {f('animal_COW_d20'):4.1f}/{f('animal_SHEEP_d20'):4.1f}/{f('animal_GOOSE_d20'):4.1f} | "
              f"{f('plant_STRAWBERRY_d15'):4.1f} | {f('quads_d15'):3.1f} | {f('prem_units_h0'):5.0f} {f('prem_units_h1'):5.0f} {f('prem_units_h2'):5.0f} {f('prem_units_h3'):5.0f} | {f('act_prod'):5.0f} {f('act_pass'):4.0f}")
    e0 = [ours[k][k[1]] for k in keys]
    f = lambda k: sum(x.get(k, 0) for x in e0) / len(e0)
    print(f"    {'v12 (same seats)':22s}       | {f('animal_COW_d20'):4.1f}/{f('animal_SHEEP_d20'):4.1f}/{f('animal_GOOSE_d20'):4.1f} | "
          f"{f('plant_STRAWBERRY_d15'):4.1f} | {f('quads_d15'):3.1f} | {f('prem_units_h0'):5.0f} {f('prem_units_h1'):5.0f} {f('prem_units_h2'):5.0f} {f('prem_units_h3'):5.0f} | {f('act_prod'):5.0f} {f('act_pass'):4.0f}")


if __name__ == "__main__":
    main()
