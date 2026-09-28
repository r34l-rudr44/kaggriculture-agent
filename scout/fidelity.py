"""Does the submitted agent play on Kaggle exactly as it does locally? Replays our seat of recorded ladder games
with the local agent (opponent frozen, shops pinned) and compares every action; also counts the fallback action
({"farmer": ["PASS"], "hands": [], "market": []}) an exception inside the agent would produce.
python scout/fidelity.py AGENT.py EP [EP ...]"""
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUR = {n for n in ("TX", os.environ.get("KAGG_TEAM_NAME", "")) if n}  # our seat labels


def job(args):
    path, ep = args
    sys.path.insert(0, ROOT); os.chdir(ROOT)
    import fastsim, tapes, pinshops
    from tourney import load_agent
    pinshops.install(fastsim.K)
    t = tapes.load(ep)
    seat = 0 if t["names"][0] in OUR else 1
    rec = [s[seat] for s in t["actions"]]
    me = load_agent(path); mine = []
    def spy(obs, cfg=None):
        a = me(obs, cfg); mine.append(a); return a
    ag = [tapes.TapeAgent(ep, 0), tapes.TapeAgent(ep, 1)]; ag[seat] = spy
    pinshops.pin(pinshops.recorded_shops(ep))
    r, _ = fastsim.play(ag[0], ag[1], t["seed"]); pinshops.unpin()
    norm = lambda a: json.dumps(a or {}, sort_keys=True)
    first = next((i for i, (x, y) in enumerate(zip(rec, mine)) if norm(x) != norm(y)), None)
    fallback = sum(1 for a in rec if a and a.get("farmer") == ["PASS"] and not a.get("hands") and not a.get("market")
                   and rec.index(a) > 24)
    return ep, seat, first, len(rec), fallback, t["rewards"][seat], r[seat], t["rewards"][1 - seat], r[1 - seat]


if __name__ == "__main__":
    path = sys.argv[1]
    with ProcessPoolExecutor(4) as ex:
        for ep, seat, first, n, fb, rec_me, loc_me, rec_op, loc_op in ex.map(job, [(path, e) for e in sys.argv[2:]]):
            same = "IDENTICAL" if first is None else f"diverges at step {first}"
            print(f"{ep} seat {seat}: {same} | recorded {rec_me:.0f} vs {rec_op:.0f}, local {loc_me:.0f} vs {loc_op:.0f} | fallback steps {fb}")
