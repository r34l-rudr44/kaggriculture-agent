"""Rating each submission's ladder games imply: Elo-scale maximum likelihood with each opponent fixed at its
team's current leaderboard score (a proxy: the team's best submission). Also the record by opponent band."""
import csv, glob, math, os, subprocess, sys, tempfile, zipfile
from kaggle.api.kaggle_api_extended import KaggleApi
env = dict(os.environ, PYTHONIOENCODING="utf-8")
d = tempfile.mkdtemp()
subprocess.run([sys.executable, "-m", "kaggle.cli", "competitions", "leaderboard", "kaggriculture", "--download", "-p", d], capture_output=True, env=env)
zipfile.ZipFile(glob.glob(os.path.join(d, "*.zip"))[0]).extractall(d)
lb = {r["TeamName"]: float(r["Score"]) for r in csv.DictReader(open(glob.glob(os.path.join(d, "*.csv"))[0], encoding="utf-8"))}
api = KaggleApi(); api.authenticate()
SUBS = [(int(a.split("=")[0]), a.split("=")[1]) for a in sys.argv[1:]] or [(56617571, "v10"), (56630707, "v12")]
for sub, name in SUBS:
    games = []
    for e in api.competition_list_episodes(sub):
        me = [a for a in e.agents if a.submission_id == sub]; op = [a for a in e.agents if a.submission_id != sub]
        if len(me) == 1 and len(op) == 1 and me[0].reward is not None and op[0].reward is not None and op[0].team_name in lb:
            games.append((lb[op[0].team_name], 1.0 if me[0].reward > op[0].reward else 0.0))
    ll = lambda R: sum(w * math.log(1 / (1 + 10 ** ((o - R) / 400))) + (1 - w) * math.log(1 - 1 / (1 + 10 ** ((o - R) / 400))) for o, w in games)
    R = max(range(800, 3400, 5), key=ll)
    lo = min(r for r in range(800, 3400, 5) if ll(r) >= ll(R) - 1.92); hi = max(r for r in range(800, 3400, 5) if ll(r) >= ll(R) - 1.92)
    print(f"{name}: {len(games)} games, {int(sum(w for _, w in games))} wins -> implied rating {R} (95% {lo}-{hi})")
    for a, b in ((0, 1500), (1500, 2000), (2000, 2300), (2300, 2500), (2500, 2700), (2700, 4000)):
        g = [w for o, w in games if a <= o < b]
        if g:
            print(f"    opponents {a}-{b}: {int(sum(g))}-{len(g) - int(sum(g))}")
