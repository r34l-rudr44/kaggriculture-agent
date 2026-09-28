"""v12 in each recent top-10 game, in the top-10 player's seat against the frozen opponent (shops pinned)."""
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fingerprint


def job(r):
    return r, fingerprint.game(r["ep"], (r["seat"], os.path.join(ROOT, "agents", sys.argv[1] if len(sys.argv) > 1 else "v12.py")))


if __name__ == "__main__":
    recs = json.load(open(os.path.join(ROOT, "top10_recent.json")))
    with ProcessPoolExecutor(4) as ex:
        out = [{"rec": r, "rows": rows} for r, rows in ex.map(job, recs, chunksize=1)]
    json.dump(out, open(os.path.join(ROOT, "results", "v12_in_top10.json"), "w"))
    print("done", len(out))
