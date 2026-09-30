"""Scouting data for v13.
python scout/scout.py top [N_PER_TEAM]   recent games (wins and losses) of the current top-10 -> top10_recent.json
python scout/scout.py losses              every ladder loss of our live submissions -> our_losses.json
Replays are converted to tapes and then recycled (a replay is ~30 MB)."""
import csv, glob, json, os, subprocess, sys, tempfile, zipfile
from kaggle.api.kaggle_api_extended import KaggleApi
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
OURS = {56617571: "v10", 56630707: "v12", 56667675: "v13", 56667699: "v10copy", 56706837: "v14"}
SEALED = set(json.load(open("top50_seal.json")))
api = KaggleApi(); api.authenticate()


def episodes(sub):
    out = []
    for e in api.competition_list_episodes(sub):
        ags = sorted(e.agents, key=lambda a: a.index)
        if len(ags) == 2 and all(a.reward is not None for a in ags) and ags[0].submission_id != ags[1].submission_id:
            out.append({"ep": str(e.id), "time": str(e.create_time), "subs": [a.submission_id for a in ags],
                        "teams": [a.team_name for a in ags], "rewards": [a.reward for a in ags]})
    return out


def fetch(eps):
    todo = [ep for ep in eps if not os.path.exists(os.path.join("tapes", f"{ep}.json"))]
    for ep in todo:
        subprocess.run([sys.executable, "-m", "kaggle.cli", "competitions", "replay", ep, "-p", "replays", "-q"],
                       capture_output=True, env=ENV)
    if todo:
        subprocess.run([sys.executable, "tapes.py", "build"], capture_output=True, env=ENV)
        for f in glob.glob(os.path.join("replays", "episode-*-replay.json")):
            os.remove(f)  # the tape keeps everything we use
    return [ep for ep in eps if os.path.exists(os.path.join("tapes", f"{ep}.json"))]


def top10(n_per_team):
    d = tempfile.mkdtemp()
    subprocess.run([sys.executable, "-m", "kaggle.cli", "competitions", "leaderboard", "kaggriculture", "--download", "-p", d],
                   capture_output=True, env=ENV)
    zipfile.ZipFile(glob.glob(os.path.join(d, "*.zip"))[0]).extractall(d)
    lb = list(csv.DictReader(open(glob.glob(os.path.join(d, "*.csv"))[0], encoding="utf-8")))
    top = {r["TeamName"]: float(r["Score"]) for r in lb[:10]}
    seen = {}  # team -> {sub: latest time}
    crawl = [int(s) for _, _, s, _ in json.load(open("top50.json"))] + list(OURS)
    done = set()
    for sub in crawl:
        if sub in done:
            continue
        done.add(sub)
        for e in episodes(sub):
            for t, s in zip(e["teams"], e["subs"]):
                if t in top:
                    seen.setdefault(t, {})[s] = max(seen.get(t, {}).get(s, ""), e["time"])
    out = json.load(open("top10_recent.json")) if os.path.exists("top10_recent.json") else []
    have = {r["ep"] for r in out}
    for team, subs in seen.items():
        sub = max(subs, key=subs.get)  # the team's most recently active submission
        eps = [e for e in episodes(sub) if e["ep"] not in have and e["ep"] not in SEALED]
        eps.sort(key=lambda e: e["time"], reverse=True)
        wins = [e for e in eps if e["rewards"][e["subs"].index(sub)] > max(r for s, r in zip(e["subs"], e["rewards"]) if s != sub)]
        losses = [e for e in eps if e not in wins]
        pick = losses[: n_per_team // 2] + wins[: n_per_team - min(len(losses), n_per_team // 2)]
        got = set(fetch([e["ep"] for e in pick]))
        for e in pick:
            if e["ep"] in got:
                seat = e["subs"].index(sub)
                out.append({"ep": e["ep"], "team": team, "score": top[team], "sub": sub, "seat": seat,
                            "win": e["rewards"][seat] > e["rewards"][1 - seat], "time": e["time"]})
        print(team, top[team], "sub", sub, "picked", len(pick), flush=True)
    json.dump(out, open("top10_recent.json", "w"), indent=0)
    print("top10_recent:", len(out), "games,", sum(r["win"] for r in out), "wins")


def losses():
    out = json.load(open("our_losses.json")) if os.path.exists("our_losses.json") else []
    have = {r["ep"] for r in out}
    for sub, ver in OURS.items():
        new = [e for e in episodes(sub) if e["ep"] not in have]
        lost = []
        for e in new:
            seat = e["subs"].index(sub)
            if e["rewards"][seat] < e["rewards"][1 - seat]:
                lost.append((e, seat))
        got = set(fetch([e["ep"] for e, _ in lost]))
        for e, seat in lost:
            if e["ep"] in got:
                out.append({"ep": e["ep"], "ver": ver, "seat": seat, "opp": e["teams"][1 - seat], "time": e["time"],
                            "ours": e["rewards"][seat], "theirs": e["rewards"][1 - seat]})
        print(ver, "new losses", len(lost), flush=True)
    json.dump(out, open("our_losses.json", "w"), indent=0)
    print("our_losses:", len(out))


if __name__ == "__main__":
    os.makedirs("replays", exist_ok=True)
    top10(int(sys.argv[2]) if len(sys.argv) > 2 else 8) if sys.argv[1] == "top" else losses()
