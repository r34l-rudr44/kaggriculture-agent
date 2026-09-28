"""Fingerprints of two agents in the same seats (dev2 intact seats): our features and the frozen rival's revenue."""
import json, math, os, sys
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fingerprint
KEYS = ["plant_STRAWBERRY_d10", "plant_STRAWBERRY_d15", "plant_STRAWBERRY_d20", "plant_WHEAT_d15", "plant_TOMATO_d15", "plant_CARROT_d15",
        "plant_MELON_d20", "animal_COW_d15", "animal_SHEEP_d15", "animal_GOOSE_d15", "animal_COW_d25", "animal_SHEEP_d25",
        "act_prod", "act_pass", "rev_STRAWBERRY", "rev_MILK", "rev_WOOL", "rev_EGG", "rev_MELON", "rev_WHEAT", "rev_TOMATO", "coins"]


def job(a):
    path, ep, seat = a
    rows = fingerprint.game(ep, (seat, os.path.join(ROOT, path)))
    return rows[seat]["feat"], rows[1 - seat]["feat"]


if __name__ == "__main__":
    A, B, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    b10 = json.load(open(os.path.join(ROOT, "results", "pinseat_base_v10_top50_dev2.json")))
    b12 = json.load(open(os.path.join(ROOT, "results", "pinseat_base_v12_top50_dev2.json")))
    seats = [json.loads(k) for k, v in b12.items() if v[5] and k in b10 and b10[k][5]][:n]  # intact for both
    with ProcessPoolExecutor(5) as ex:
        ra = list(ex.map(job, [(A, e, s) for e, s in seats])); rb = list(ex.map(job, [(B, e, s) for e, s in seats]))
    def ms(v):
        m = sum(v) / len(v); return m, math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1) / len(v))
    print(f"{len(seats)} seats: {A} -> {B}")
    for k in KEYS:
        m, se = ms([b[0].get(k, 0) - a[0].get(k, 0) for a, b in zip(ra, rb)])
        print(f"  ours  {k:24s} {sum(a[0].get(k, 0) for a in ra)/len(ra):9.1f} -> {sum(b[0].get(k, 0) for b in rb)/len(rb):9.1f}  diff {m:+8.1f} (SE {se:.1f})")
    for k in ("rev_STRAWBERRY", "rev_MILK", "rev_WOOL", "rev_EGG", "coins"):
        m, se = ms([b[1].get(k, 0) - a[1].get(k, 0) for a, b in zip(ra, rb)])
        print(f"  RIVAL {k:24s} diff {m:+8.1f} (SE {se:.1f})")
    d = [(b[1].get("rev_STRAWBERRY", 0) - a[1].get("rev_STRAWBERRY", 0)) for a, b in zip(ra, rb)]
    print("  rival strawberry gain > +3000 in", sum(x > 3000 for x in d), "of", len(d), "seats; < -3000 in", sum(x < -3000 for x in d))
