# Contributing

Conventions for working on this project. `docs/ARCHITECTURE.md` explains how the agent and the
evaluation stack actually work; read that first for context, and this for the rules of engagement.

## Agent code

1. **An agent is a single standard-library Python file.** It exposes `make_agent(params=None)` and
   ends with a top-level `agent(obs, config)`; Kaggle runs the last callable in the file. It does no
   file I/O and imports nothing outside the standard library.
2. **Put every change behind a parameter whose default reproduces the parent exactly.** Prove it with
   an identity check before measuring anything: `pinseat.py` against the parent must print
   `diff +0 (SE 0)`.
3. **Check for hidden exceptions.** `_act` is wrapped in `try/except`, which silently turns a crash
   into a passing turn. Call `_act` directly over a few games and count exceptions. Keep each turn
   well under 50 ms; the engine's limit is 1 s plus a small overage bank.
4. **Match the surrounding style**: same naming, terse comments, and a module docstring describing
   the strategy.
5. **Build submissions with `python prep_submit.py agents/vN.py`.** It runs a static scan and an
   official-engine smoke test, then writes `submission/main.py`. Only submit that file, and only
   when the smoke test passes and it matches the agent file exactly.

## Data hygiene

The whole evaluation rests on keeping measurement sets separate from development sets.

- **Sealed data is for `gate.py` only.** Never use it to develop, tune or diagnose anything. Sealed
  data is: seeds 30000 and above, `top50_seal.json`, and `gate_top.json`.
- **Development sets** are `top50_dev.json`, `top50_dev2.json`, `top50_dev3.json`, `our_losses.json`,
  `top10_recent.json` and `ladder_set.json`.
- **Anything used to find or tune a change must be confirmed on a set that played no part in finding
  it.** Every use counts: once a set has been used to choose between variants, it is no longer held
  out for that change.
- **Fetched replays** go through `tapes.py build`, after which the raw replays (about 30 MB each) can
  be deleted.

## Evaluation protocol

The validated metric, which ranks past versions in line with their ladder ratings:

```
python pinseat.py CAND.py [--params JSON] --base agents/v13.py --set top50_dev3.json \
    --keep units --workers 10 --tag T
```

The candidate plays one seat of a recorded top-50 game. The other seat replays its recording, and the
town shops are pinned to the recording. Keep `--keep units`: it drops only games where the frozen
side's recording broke. The older coin-based filter hid exactly the effect top players beat us with.

| Tool | Use |
|---|---|
| `h2h.py CAND OPP... --seeds N --seed0 S --params JSON --tag T`, then `h2h.py --cmp A.json B.json` | Paired runs against reactive bots (pool listed in `poolset.json`) |
| `pinseat.py ... --set our_losses.json --only TX` | Loss regression suite: replays our seat in each game we lost |
| `pinseat.py ... --set results/top10_set.json --only <team>` | Top-10 seat test |
| `gate.py agents/INCUMBENT.py agents/CANDIDATE.py --workers 10` | Blind promotion gate on sealed seeds, with a pre-registered pass rule |
| `scout/` | Scouting and analysis tools; see the README |

**What counts as evidence:**

1. A paired difference above 2 SE on a set that was not used to find the change.
2. No pool member significantly worse.
3. Then the gate.

Report every run of a lever, not just the good ones. Best-of-N selection inflates results, and so do
small samples: "5 losses v10 would have won" proves nothing.

**Pitfalls already hit, so don't repeat them:**

- A common-random-numbers patch applied to only some games in `es_opt`, biasing a search.
- The coin-based keep filter in the seat test.
- Cache-file races on Windows.
- Development tapes leaking into the gate.
- Validation episodes where the agent plays itself, with no real opponent.
- Comparing on games that were intact for only one of the two agents.

## Originality

- Third-party public bots live in `external/` (gitignored) and are used **only as black-box sparring
  opponents**. No third-party code goes into the agents.
- Only borrow a component that measurably beats what we have, and re-implement it in our own
  architecture.
- Scouting works from public game replays: what opponents did, measured by re-simulating their games.

## Repository hygiene

- **Code and project data only**: no logs, run output or scratch work. `results/`, `tapes/`,
  `replays/`, `submission/`, `external/` and `agents/scratch_*/` are gitignored.
- **Never commit credentials.** Kaggle API tokens live in `~/.kaggle/`, outside the repo.
- **The team name is configuration, not a constant.** `gate.py` and the `scout/` tools read it from
  the `KAGG_TEAM_NAME` environment variable.

## Running jobs

- **One heavy job at a time.** The gate, `es_opt.py`, and large `pinseat` or `h2h` runs are heavy;
  two at once has caused out-of-memory crashes and a 3x slowdown on a 12-core / 16 GB machine. Size
  `--workers` to the cores you have.
- **After stopping a job, kill its worker processes too.** Orphaned `spawn_main` workers have held
  8 GB. Check that no duplicate copy of the job is running.
