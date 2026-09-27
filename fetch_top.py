"""Download the two most recent public episodes of each leaderboard submission in top50.json.
Episode #1 -> top50_dev.json (development), episode #2 -> top50_seal.json (sealed; gate only)."""
import json, os, subprocess, sys
top = json.load(open("top50.json"))
os.makedirs("replays", exist_ok=True)
dev, seal = [], []
for rank, team, sub, score in top:
    out = subprocess.run([sys.executable, "-m", "kaggle.cli", "competitions", "episodes", str(sub), "-v"], capture_output=True, text=True).stdout
    eps = [l.split(",")[0] for l in out.splitlines() if l[:1].isdigit() and "COMPLETED" in l and "PUBLIC" in l]
    for k, ep in enumerate(eps[:2]):
        if not any(f.startswith(f"episode-{ep}") for f in os.listdir("replays")):
            subprocess.run([sys.executable, "-m", "kaggle.cli", "competitions", "replay", ep, "-p", "replays", "-q"], capture_output=True)
        (dev if k == 0 else seal).append(ep)
    print(rank, sub, len(eps), flush=True)
json.dump(dev, open("top50_dev.json", "w"))
json.dump(seal, open("top50_seal.json", "w"))
print("dev", len(dev), "seal", len(seal))
