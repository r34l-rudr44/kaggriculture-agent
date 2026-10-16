# Kaggriculture agent

Agent and evaluation tooling for the Kaggle simulation competition
[Kaggriculture](https://www.kaggle.com/competitions/kaggriculture): a two-player farming game
where each player runs a 10x10 farm, both sell into one shared market, and the player with the
most coins after 720 turns wins.

**Result: silver medal.**

## Approach

The agents are hand-written policies developed in numbered versions. Each version starts from its
predecessor, puts every change behind a parameter whose default reproduces the parent exactly, and is
promoted only after a blind gate on sealed holdout data. Strategy came from measurement rather than
guesswork: public game replays of strong players were re-simulated locally, fingerprinted into
strategy features, and compared against our own play in the same seats to find where coins were
being lost. `docs/ARCHITECTURE.md` records every version and every experiment, including the ones
that failed.

## Agents

| File | Description |
|---|---|
| `agents/v15.py` | Final submission, live with the re-submitted v10 as the final pair. `v14` plus cash-safe hiring, a midnight shed-overflow guard and feed wheat listed ahead of land and seed buys. |
| `agents/v14.py` | Previous version. `v13` plus a market book that lists every sell first and places wheat orders against the rival's flow at each step of the draw cycle, and strawberry plantings that count the revenue they take from the rival. |
| `agents/v13.py` | Previous version. v12 plus wheat carried through the town's draws. |
| `agents/v12.py` | Previous candidate. `v10` plus sell lists race-ordered against the rival's stock at every step, fertilizer pickups net of what the herd pens hold, a goose cap that grows with egg shops, and market/herd weights retuned by `es_opt.py`. |
| `agents/v10.py` | Previous best. `v8` plus evening crews and batched tile visits, a corrected supply forecast for herd buying, extra fertilizer doses on wheat, and sales timed right after town consumption. |
| `agents/v8.py` | Earlier version. A day-by-day market model of every product (town demand, both farms' visible pipelines, rival stock) drives herd size, a second melon crop and sale timing; the full hiring schedule runs through day 27; the last day uses a coin-valued sweep and a timed final sale. |
| `agents/v7.py` | Earlier version. `v6` plus a ring layout opening with cash-sized day-0 orders, melon race priority, a day-by-day strawberry market forecast for planting, and a day-1 melon top-up. |
| `agents/v6.py` | Earlier version. `v5_script` plus midnight overflow couriers, retuned demand model, rival-sales tracking with race selling, order-book optimization of premium sales, premium rush. |
| `agents/v5_script.py` | Scripted all-in opening (2 cows + 3 sheep around the shed, care from day 0), state-driven days 1-10, demand-sized strawberries/tomatoes, shop-driven herd, burst job engine. |
| `agents/v5_planner.py` | Alternative design: per-tile action calendars, labor planner, value-based router. |
| `agents/v5_evolve.py` | Alternative design evolved from v4. |
| `agents/v4.py` | Early greedy task-assignment agent (baseline). |

Every agent is a single standard-library file exposing `make_agent(params=None)` and ending with a
top-level `agent(obs, config)` (Kaggle runs the last callable in the file).

## Evaluation tools

| Tool | Purpose |
|---|---|
| `fastsim.py` | Runs the official engine directly (about 10x faster than `kaggle_environments.env.run`, identical results). |
| `tourney.py` | Parallel head-to-head: `python tourney.py agents/v6.py agents/v5_script.py --seeds 24`. |
| `tapes.py` | Turns downloaded top-player replays into replayable action tapes (`python tapes.py build`). |
| `panel.py` | Candidate vs frozen top-player tapes on their original seeds. |
| `panel2.py`, `cmp.py` | Low-noise panel (common random numbers) and paired comparison of two runs. |
| `h2h.py` | Paired head-to-head vs reactive agents in both seats (common random numbers); `--cmp A.json B.json` compares two runs. |
| `ledger.py` | Exact per-product revenue/cost ledger of a game. |
| `validate.py` | Loads a file the way Kaggle does, plays full games, checks errors and timing. |
| `pinshops.py`, `pinseat.py` | Pin the town shops of a recorded game (the engine draws shops from the weed RNG) and run the pinned seat test against top players. `--keep units` drops only games whose frozen side's recording broke; `--only TEAM` replays one team's seats (e.g. our ladder losses). |
| `es_opt.py` | Evolution-strategy parameter search on the seat test and the sparring pool (soft-win score, `--resume`). |
| `poolbt.py` | Round-robin population rating (Bradley-Terry). |
| `gate.py` | Blind promotion gate on sealed holdout seeds (strong opponent, our ladder opponents, top-20 tapes, duel) with a pre-registered rule. |
| `fetch_top.py` | Downloads top-50 players' recent games into development and sealed tape sets. |
| `fetch_ladder.py` | Downloads our recent ladder games to build the ladder-opponent suite (`ladder_set.json`). |
| `prep_submit.py` | Static checks plus an official-engine smoke test in an empty directory; writes `submission/main.py`. |
| `fetch_replays.py`, `summarize_replay.py` | Download top-player replays (Kaggle CLI) and condense them into per-day summaries. |

## Scouting and analysis (`scout/`)

| Tool | Purpose |
|---|---|
| `scout.py` | `top N`: recent wins and losses of the current top-10 teams; `losses`: every ladder loss of our live submissions. Both become tapes. |
| `fingerprint.py` | Replays every tape and records about a hundred strategy features per player (openings, farm mix over time, land, hires, spending, sale timing, labour). |
| `learn.py` | Paired win model over the fingerprints (cross-validated logistic regression, feature win rates). |
| `top10.py`, `v12_in_top10.py` | Top-10 players vs our agent in the same seats; what separates top-10 wins from losses. |
| `cmp_fp.py`, `pair_ledger.py` | Two agents in the same seats: strategy features and per-product ledgers side by side. |
| `fidelity.py` | Replays our recorded ladder games locally and checks that every action matches Kaggle's. |
| `track.py`, `record.py`, `ladder_strength.py` | Ladder snapshot, win/loss record, and the rating our games imply given opponent strength. |

## Setup

```bash
pip install -r requirements.txt
python fetch_replays.py 3      # needs Kaggle API credentials; top30.json lists leaderboard submissions
python tapes.py build          # builds tapes/ from replays/
python panel.py agents/v6.py --workers 8
```

Set `KAGG_TEAM_NAME` to your Kaggle display name so `gate.py` and the `scout/` tools can identify
your own seat in recorded games.

Not part of the repo: `external/` (third-party public bots, used as black-box sparring opponents and
not redistributed here) and the generated `replays/`, `tapes/`, `results/` and `submission/`
directories.

## Docs

- `CONTRIBUTING.md`: code conventions, data hygiene and the evaluation protocol.
- `docs/ARCHITECTURE.md`: how the agent works, the evaluation stack, every version and experiment with its numbers, and where to start.
- `docs/PLAYBOOK.md`, `docs/STRATEGY.md`: early notes from the v5 era (historical).

## License

MIT, see `LICENSE`.
