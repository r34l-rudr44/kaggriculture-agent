# Architecture and project history

This is the one document to read before working on the project. It explains how the agent works, how we measure it, what each version changed, and every experiment we ran, with its numbers. `CONTRIBUTING.md` holds the code conventions, data hygiene rules and the evaluation protocol.

Last updated 2026-09-29.

## 1. The game, as it matters for design

These facts were checked against the engine source (kaggle_environments `kaggriculture.py` 1.32.7, loaded by `fastsim.py` as `fastsim.K`).

**Board and setup**
- Two farms share one market. A game is 720 steps (30 days x 24 hours). The winner is the farm with more coins at the end; only the win counts on the ladder.
- The board is 10x10 and the shed sits at the centre, tiles (4,4)-(5,5).
- A farm starts with one quadrant. The other three cost 1000, 2000 and 4000.

**Shed**
- The shed holds 100 units. At midnight every unit's inventory drops into it and the units return home.
- Anything beyond 100 is destroyed.

**Hands**
- Hands are hired every day. The n-th hire of a day costs fib(n): the 12 hires we use cost 376 in total, the 13th 233, the 14th 377.

**Crops**
- A plant dies after 2 consecutive days unwatered. The planting day counts as unwatered.
- Ongoing crops (strawberry, tomato) produce on schedule even when unwatered. Watering on a production day, together with fertilizer (FERTILIZE covers that day and the next), doubles the output.
- All same-day flags (watered, fed, cared) are read at midnight, so the hour of the action does not matter.

**Animals**
- An animal yields every production whether or not it is fed. Feed only matters for survival (2 unfed days kill it) and for the care bonus.
- `fertilizer_available` resets every night: uncollected fertilizer is lost.

**Town**
- A shop unlocks every 3 days. It is drawn from the same daily RNG that spawns weeds (one draw per empty tile), so changing one farm changes the town. That is why every tape test pins the shops.
- Every 4 steps each shop removes 1 unit of each product it buys, or 2 units if it buys a single product. The town centre removes 1 unit of every product every 24 steps. These draws are fixed and run after the order book clears.

**Market**
- A product's price is a curve of market inventory (neutral point 10000). Buy and sell prices use the same curve, so there is no spread.
- Orders are capped at 10 per step. The two players' lists are processed in lockstep slots, so order position matters.

## 2. The agent (`agents/v13.py`, about 2100 lines, standard library)

Every turn, `_act(obs, P, MEM)` runs this pipeline. `make_agent(params)` merges overrides into `DEFAULT_PARAMS` and wraps `_act` in a try/except. `P` holds the parameters; `MEM` holds per-player memory across turns.

```
Turn(obs)                      parse both farms, market, town, units, carried goods, rival tiles
track_rival(...)               infer the rival's harvested-but-unsold stock and its sale hours
(v13) hide wheat bought for the draw trade from the plan
setup_home(...)                day-0 layout: pens at the shed door, melon ring, wheat rim (home_layout)
animal_needs(...)              feed/care/collect needs per pen; how many feed trips are required
make_plan(...)                 hires, wheat purchases, budget, land purchases, then plan_tiles:
   herd_book_targets(...)      herd size per species from the market books (MarketBook)
   book_additions(...)         strawberry and second-melon counts from the books
   crop_room(...)              tomato and carrot room left in their markets
build_jobs(...)                every tile with work -> job (priority, action list, need)
assign_units(...)              greedy: each unit takes the best job by priority - w_dist*distance
                               + burst bonus for chained actions + stick bonus for yesterday's target;
                               shed pickups of feed/fertilizer/animals, drops for sale, overflow couriers
market_orders(...)             sells (hold_for_later, wait_for_draw, race_order), hires, buys, combined
                               under the 10-order cap
(v13) draw_trade(...)          wheat bought on a draw step, sold on the next
last day: final_sweep / last_day_orders
```

**The market model** (lines 109-370) is the agent's main strategic asset:
- `market_price` and `sell_revenue` implement the engine's price curves.
- `town_demand`, `daily_demand` and `town_draw` forecast the town's drains.
- `crop_sales`, `animal_sales` and `farm_sales` forecast both farms' supply from the visible tiles.
- `MarketBook` combines these into a day-by-day inventory forecast per product. A candidate plant or animal is valued at the forecast prices of its own sale days, net of the price it knocks off our other sales, plus `herd_rival_weight` times the revenue it takes from the rival.
- `sale_split` decides how much of a batch to hold for a later sale window.

**Parameters** (`DEFAULT_PARAMS`, lines 449-575, about 95 keys) steer everything:
- opening quantities;
- crop windows and caps (`straw_*`, `tom_*`, `wave_*`, `carrot_last`, `wheat_last`);
- book valuation (`book_alt`, `book_labor`, `book_unlock_w`, `room_mult`);
- herd (`herd_labor`, `herd_rival_weight`, `*_cap`, `*_last`, `buy_block_frac`, `goose_per_egg_shop`);
- labour (`w_dist`, `burst`, `stick`, `eve_harv`, `collect_base`, `pen_fert_cover`, the `hires` schedule);
- selling (`hold_*`, `draw_wait_*`, `race_*`, `final_hold_*`);
- trading (`draw_trade_*`).

**Known structural weakness.** The job assignment is greedy per step:
- A strawberry bush 6 steps away scores about -56 at noon, while a nearby wheat watering scores +58, so far bushes wait until their window has closed.
- Priority reflects neither value (a bush death costs about 450, a wheat death about 100) nor latest-start deadlines.

This is the root cause behind the labour gap in section 6.

## 3. Evaluation infrastructure

| Piece | Role |
|---|---|
| `fastsim.py` | Runs the official engine directly, about 10x faster, with identical results |
| `tapes.py` | Turns recorded replays into per-step action tapes. `TapeAgent(ep, seat)` replays one seat |
| `pinshops.py` | Recovers a recorded game's shop sequence and forces it while a candidate plays |
| `pinseat.py` | **The validated metric.** The candidate plays one seat of recorded top-50 games against the frozen other seat, with shops pinned. `--keep units` drops only games where the frozen side's recording broke. Output is paired against a base agent. It ranks our versions in their ladder order (margin per game: v7 -17.8k < v8 -10.7k < v10 -8.7k) |
| `h2h.py` | Paired head-to-head against reactive bots, both seats, with a common-random-numbers weed patch |
| `gate.py` | Blind promotion gate. Uses sealed seeds 31000-31047, the sealed top-player tapes (`gate_top.json`, 178 tapes), our old ladder opponents, and the pool. The pass rule was fixed on 2026-09-27 |
| `es_opt.py` | Separable evolution-strategy parameter search (antithetic, rank-weighted, batched, `--soft`, `--resume`) |
| `ledger.py` | Instruments the engine to log every committed unit. Used for revenue and cost decompositions |
| `scout/` | Top-10 and loss scouting, strategy fingerprints (about 100 features per player), the paired win model, fidelity checks and ladder tracking |

**Data sets:**

| Set | Contents | Use |
|---|---|---|
| `top50_dev.json` | 43 tapes | development |
| `top50_dev2.json` | 200 tapes | development |
| `top50_dev3.json` | 150 tapes, fresh | confirmation |
| `top50_seal.json`, `gate_top.json` | sealed | gate only |
| `our_losses.json` | every ladder loss of our live submissions | loss regression suite |
| `top10_recent.json` | 380 recent top-10 games | top-10 study |
| `ladder_set.json` | 80 old ladder games | gate |

**Sparring pool** (`poolset.json`): five public bots run as black boxes from `external/`, including farm2945. They rate about 1450-2500 on today's ladder, and we beat them 80-93% of the time.

## 4. Versions

| Version | What changed | Ladder |
|---|---|---|
| v4 | Greedy task agent | 592 |
| v5_script | Scripted all-in opening, demand-sized crops, shop-driven herd | 1128 |
| v6 | Overflow couriers, rival-sales tracking, race selling, order-book optimization | 1305 |
| v7 | Ring layout, cash-sized orders, melon race, strawberry forecast | 1539 |
| v8 | Market books drive herd, second melon crop, sale timing; full hiring schedule; last-day sweep | ~1700 |
| v10 | Evening crews and batched visits; supply-forecast fix (v8 double-counted last night's output); `buy_block_frac` 0.3; wheat fertilizer doses; sell after town draws | **2486-2531** (121-70; fitted strength 2590) |
| v11 | v10 plus ES parameters plus goose cap | Not submitted: the gate failed (margin up, wins flat) |
| v12 | v11 plus race-ordering every step (+113) and pen fertilizer rationing (+722) | ~1700 (87-13). Rating climbed slowly because it drew weak opponents. Weakness: about 2 fewer late strawberry bushes than v10 (`book_alt` 31) |
| v12.1 | v12 with `book_alt` 25 | Not submitted: failed the gate on the pool and duel, though held-out sets showed +692/+940 |
| **v13** | v12 plus the wheat draw trade (`draw_trade`) | Live since 2026-09-29 |

`agents/v13.py` and a re-submitted, unchanged v10 are the live pair, the final pair unless replaced.

**v13 evidence:**

| Test | Result vs v12 |
|---|---|
| Duel | 68-12 |
| Gate duel | 88-8 |
| `top50_dev3` | +716 (SE 183) |
| `top50_dev2` | +910 (SE 184) |
| Pool | positive against all 5 bots |
| Gate | FAIL: strong-bot suite even (-110) and pool even (+9). Submitted anyway as a deliberate call |

## 5. Experiments, with results

**Confirmed and kept:**
- Race-ordering sells every step: +113 (SE 29).
- Pen fertilizer rationing (`pen_fert_cover` 0.5): +722 (SE 295); +819 (SE 144) held out.
- Goose cap for egg-rich towns: +383 (SE 171).
- Wheat draw trade: +716 and +910 on held-out sets.
- ES parameters (the ES mean, not its best point): duel 80-40 vs v10 and more pool wins. In the seat test the gain was only about +1k, because the ES seat term was biased by a patch mismatch (since fixed).

**Refuted (with numbers):**

| Experiment | Result |
|---|---|
| Tomato quadrant on bought land | -0.6k to -2.9k. It takes waterings from strawberries |
| Wheat feed buffer | -1.2k |
| Selling sooner (no holds / no draw wait / higher hold risk) | -0.9k to -1.2k |
| One-visit herd service | Pen visits 27 -> 20 a day, but coins flat to negative |
| Evening pre-watering | Idle turns 20 -> 15 a day, no coin gain |
| Evening sell run (runners) | Pool -828 |
| Sale clock | Noise; pool negative |
| Harvest-threshold and cadence changes | -0.1k to -0.8k |
| Crop watering priority 110 | -607 on independent data |
| Town-conditioned caps (contextual policy) | Only the wool effect is real (+521 per yarn store, t 3.8); the combined rule did not confirm (-134) |
| Farm growth alone | +224 |
| Learned sales forecaster | Oracle headroom only +524 (SE 522) |
| 13th hire | -2.7k over the window |

**Oracles** (upper bounds, not buildable):
- 2 free hands on days 10-27: **+3573 (SE 162)**, wins 38 -> 62 of 184.
- Growth plus 2 free hands: +3688.
- Growth plus free strawberry waterings: +278.

The mechanism analysis showed the gain is volume (wheat, carrots, strawberry doubles, care bonuses), which lowers the rival's later prices. Sale timing accounts for only about 0.3k.

## 6. Where the gap to the top 10 is

Top-10 players compared with v12 in the same seats (21 intact games):
- They win 13 of those games; v12 in the same seats wins 2. The margin gap is about 18k per game.
- 7.4k of it is our own lower coins.
- 10.8k of it is the same frozen opponent earning more against us, through prices.

| Per day, days 10-25 | Top-10 | v12 |
|---|---|---|
| Useful actions | 153 | 130 |
| Idle | 2 | 20 |
| Moves | 115 | 130 |
| Shed trips | 11 | 17 |
| Hires over the game | 289 | 312 |

They also run a bigger farm:
- about 4 more strawberry bushes;
- about 2 more each of geese, tomatoes and carrots;
- some buy the 4th quadrant;
- no second melon crop.

They sell premium goods all day, rather than mostly at hour 0.

**What decides top-10 games:** wool and milk revenue relative to the opponent. 32 of their 40 losses were to other top-10 teams.

**Win model** (1057 games, CV AUC 0.76): the strongest features are premium units sold across the day, sheep and geese by day 10, strawberries by day 10, fertilizer use, and fewer idle turns.

**Wheat traders** in our loss log have huge wheat turnover. It is gross, not profit (88-757 coins per game), and it does not hurt us. Their straddle of the town draws inspired v13's draw trade.

**Open lead:** shifting all of v12's orders one slot later changed the margin by about 1.6k in v12-vs-v12 games. Nobody has studied it yet.

## 7. Where to start

1. **v14 = v13 plus a deadline- and value-aware scheduler, plus growth.**
   - Score each job by value, and add a latest-start ramp: latest start = 23 - distance - actions.
   - Then raise `straw_cap` and the animal caps.
   - Test growth together with the scheduler, never one without the other.
2. **Order-position study:** where our buy and sell orders sit in the 10-slot list, and how that interacts with the rival's lockstep slots.
3. **Strawberry supply** (`book_alt`) on top of v13.

**Measure every change like this:**
1. Identity check first.
2. `pinseat --set top50_dev3.json --keep units` against v13, plus `h2h` against the pool.
3. Confirm on a set the change was not tuned on.
4. Run the gate.
5. Decide on the submission with the gate numbers in hand.

## 8. v14 (live since 2026-09-30) and the last day's findings

`agents/v14.py` = v13 plus two levers. It passed the blind gate against v13 on every suite:

| Suite | Result |
|---|---|
| Strong reactive bot | +1242 (SE 234) |
| Pool | +898 (SE 140); every bot better on margin |
| Top-player tapes | +890 |
| Old ladder opponents | +889 |
| Duel | 93-3 |

It was submitted as `56706837`. The final pair is v14 + the v10 copy (`56667699`).

**1. Order position (`arrange`, `order_layout` 4, `race_model` 1).**

How the engine processes orders:
- Both players' lists are processed slot by slot.
- Sells and wheat/fertilizer buys commit unit by unit at a shared price, so an order interacts only with the rival's orders for the same product. Position moves coins from one player to the other.

What v14 does:
- It lists every sell before hires, land, animals and seeds, and wheat buys last.
- `track_wheat` learns the rival's net wheat flow at each step of the 4-step draw cycle. Each wheat order goes right after the steep sells when the rival usually moves wheat the same way, and last when it moves the other way.
- The steep sells race the rival's held goods, assuming it lists them in any order. v13 had assumed wool, then milk, then strawberry.

Results: duel against v13 32-0 on development seeds; ladder_set +406 (2.9 SE); top-10 seats +53 (SE 17).

Known imprecision: `wheat_net` under-counts our own draw-trade sale at the step after each draw, so the tracker books it as rival flow. Fixing it changed nothing against farm2945 and has not been measured elsewhere.

**2. Rival-aware strawberry planting (`book_rival_w` 0.25).**
- The strawberry book now credits a quarter of the revenue a new bush takes from the rival, as the herd books already did with `herd_rival_weight`.
- Against farm2945, which always runs 33 bushes: +734 (seed-level SE 224) over 100 fresh seeds.
- Our own coins fall slightly (about -250). The gain comes from the rival earning less.

**Rejected on the last day** (verified on fresh data):

| Lever | Result |
|---|---|
| No second melon crop | -2749; that crop is worth about +2.9k of our own coins |
| Top-10 melon profile | Pool collapsed |
| Early geese and cows | Margin not confirmed |
| Deadline/value scheduler | Weight 0.15 is about 0 on normal seats; weight 0.5 with growth regressed (Codex's attempt, -2444) |
| Wheat-flow dead zone 0 | -100 on a fresh block |
| `book_alt` 25 on v14 | -21 against farm2945; a small, uncertain gain elsewhere |
| Fewer hires, caring when prices are low, earlier strawberries or tomatoes | All negative against farm2945 |

**Measurement caveat for seat tests (important):**
- In about a third of intact seats, the frozen rival earns more than 10k above its recording when it faces v13.
- Almost any change gains on those seats, so raw seat-test means carry a perturbation premium of about +600.
- Judge a lever by its own-coin diff, median or winsorized means, the within-10k subset, and h2h and gate results, not by the raw mean alone.

**Open fragility:**
- In some games v14 reaches day 10 with about 10 coins, so the hour-0 hires depend on tiny sales.
- One development game got 4 hands instead of 12 and lost about 11.6k.
- A cash-safe hire reserve could remove these tails.

**Scale of the remaining gap:** in recent top-10 seats v13 trailed by about 20k per game, with 0 of 99 intact wins. The levers above add about 1-2k against strong play. The structural gap is labour and volume, and it remains open.

## 9. v15, the final submission (2026-09-30)

`agents/v15.py` = v14 plus three fixes found by the code audit. Each is behind a parameter; with all three off, it plays exactly like v14.

- **`cash_floor` 1 (hour 1+).** When an hour's hires cannot be paid, sell the feed and fertilizer reserves and list the cheap sells ahead of the hires. Some games had spent everything on the day-6 herd buy and hired no hands on day 7.
- **`mid_guard` 1.** The hour-23 overflow sale counts this step's harvests, collections and pickups. Any yield that still cannot fit stays on its tile, instead of being destroyed by the midnight drop. This used to cost about 900 coins per game.
- **`feed_first` 1.** The feed wheat buy goes right after the hires, ahead of land, animal and seed buys.

Results against v14:
- Development data:
  - farm2945: +1066 (SE 160), own coins +584.
  - Fresh top-50 seat test: +1076, own coins +296.
  - v14's 6 ladder losses: 4 turned into wins.
  - Duel: 55-5.
- Gate PASS on every suite:
  - farm2945: +1113, wins 85 -> 91.
  - Old ladder opponents: +1347.
  - Top-player tapes: +971.
  - Pool: +512, all 5 bots.
  - Duel: 85-11.

The final pair is v15 + the re-submitted v10.

v16 was tried and rejected. It fixed the day-28 half-production drop in `crop_sales` (`book_tail`). Duel vs v15: 19-25. v14's losses went 4 -> 2 wins. Seat test +43. Not submitted.

Ladder diagnosis, for later work:
- v12, v13 and v14 stalled around 1700-2000 on upset losses to low-rated teams running the public 2945 bot, which grows 33 strawberry bushes by day 15.
- Our books then forecast a crowded strawberry market and retreat to cheaper crops.
- The long-term fix is a planner that sizes the day's work and the farm together. Measured gap to the top 10: 153 vs 127 useful actions per day, about 14k mid-game revenue, and about 20k per game in top-10 seats.
