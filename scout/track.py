"""Ladder snapshot: our live submissions' scores, team rank and the rank-50/100 lines. Appends to results/track.log."""
import csv, glob, io, os, subprocess, sys, tempfile, time, zipfile
env = dict(os.environ, PYTHONIOENCODING="utf-8")
cli = [sys.executable, "-m", "kaggle.cli", "competitions"]
subs = subprocess.run(cli + ["submissions", "kaggriculture", "-v"], capture_output=True, text=True, env=env).stdout
rows = [r for r in csv.reader(io.StringIO(subs[subs.index("ref,fileName"):])) if r]
head = rows[0]
live = {r[head.index("description")].split(":")[0]: (r[head.index("publicScore")] or r[head.index("status")].split(".")[-1]) for r in rows[1:3]}
d = tempfile.mkdtemp()
subprocess.run(cli + ["leaderboard", "kaggriculture", "--download", "-p", d], capture_output=True, env=env)
zipfile.ZipFile(glob.glob(os.path.join(d, "*.zip"))[0]).extractall(d)
lb = list(csv.DictReader(open(glob.glob(os.path.join(d, "*.csv"))[0], encoding="utf-8")))
rank = next(i + 1 for i, r in enumerate(lb) if r["TeamName"] == "TX")
line = (f"{time.strftime('%Y-%m-%d %H:%M')} IST  " + "  ".join(f"{k} {v}" for k, v in live.items())
        + f"  | rank {rank}/{len(lb)}  #50 {lb[49]['Score']}  #100 {lb[99]['Score']}")
print(line)
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "track.log"), "a").write(line + "\n")
for sub, name in (("56706837", "v14"), ("56667699", "v10 copy")):
    rec = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "record.py"), sub, "0"],
                         capture_output=True, text=True, env=env).stdout.strip()
    print(f"{name} ladder record:", rec)
