"""Win/loss record of a submission's ladder games: python scout/record.py SUB_ID"""
import sys
from kaggle.api.kaggle_api_extended import KaggleApi
api = KaggleApi(); api.authenticate()
sub = int(sys.argv[1])
w = l = 0; rows = []
for e in api.competition_list_episodes(sub):
    ags = e.agents
    me = [a for a in ags if a.submission_id == sub]
    op = [a for a in ags if a.submission_id != sub]
    if len(me) != 1 or len(op) != 1 or me[0].reward is None or op[0].reward is None:
        continue
    win = me[0].reward > op[0].reward
    w += win; l += not win
    rows.append((e.id, int(me[0].reward), int(op[0].reward), op[0].team_name))
print(f"W-L {w}-{l}")
for r in rows[:int(sys.argv[2]) if len(sys.argv) > 2 else 12]:
    print(f"  {r[0]}  {'W' if r[1] > r[2] else 'L'}  {r[1]:7d} vs {r[2]:7d}  {r[3]}")
