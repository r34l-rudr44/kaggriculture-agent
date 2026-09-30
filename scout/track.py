"""Ladder snapshot of the final pair (v15 and the re-submitted v10): score, record, team rank and the rank-50/100
lines. Appends one line to results/track.log."""
import csv, glob, io, os, subprocess, sys, tempfile, time, zipfile
PAIR = {"56714146": "v15", "56714161": "v10"}
env = dict(os.environ, PYTHONIOENCODING="utf-8")
cli = [sys.executable, "-m", "kaggle.cli", "competitions"]
subs = subprocess.run(cli + ["submissions", "kaggriculture", "-v"], capture_output=True, text=True, env=env).stdout
rows = [r for r in csv.reader(io.StringIO(subs[subs.index("ref,fileName"):])) if r]
head = rows[0]
score = {r[0]: (r[head.index("publicScore")] or r[head.index("status")].split(".")[-1]) for r in rows[1:]}
d = tempfile.mkdtemp()
subprocess.run(cli + ["leaderboard", "kaggriculture", "--download", "-p", d], capture_output=True, env=env)
zipfile.ZipFile(glob.glob(os.path.join(d, "*.zip"))[0]).extractall(d)
lb = list(csv.DictReader(open(glob.glob(os.path.join(d, "*.csv"))[0], encoding="utf-8")))
rank = next(i + 1 for i, r in enumerate(lb) if r["TeamName"] == "TX")
recs = {}
for sub, name in PAIR.items():
    out = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "record.py"), sub, "0"],
                         capture_output=True, text=True, env=env).stdout.strip()
    recs[name] = out.replace("W-L ", "")
line = (f"{time.strftime('%Y-%m-%d %H:%M')} IST  "
        + "  ".join(f"{name} {score.get(sub, '?')} ({recs[name]})" for sub, name in PAIR.items())
        + f"  | rank {rank}/{len(lb)}  #50 {lb[49]['Score']}  #100 {lb[99]['Score']}")
print(line)
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "track.log"), "a").write(line + "\n")
