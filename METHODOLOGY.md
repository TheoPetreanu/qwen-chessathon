# Testing methodology — read this before running ANY match

This machine has **6 physical cores / 12 threads**.

## Hardware and concurrency
- Use **`--workers 6`**. Corrected 2026-09-09 by measurement: the old
  "3 workers = 6 processes = core count" reasoning counted the wrong thing.
  A worker owns 2 engine processes but they **alternate turns** -- the idle one
  blocks on stdin at ~0% CPU -- so 3 workers only ever kept 3 cores busy and
  half the machine sat idle.

  | workers | games/hour (10s+0.1s) | per-engine nps | CPU load |
  |---|---|---|---|
  | idle | -- | 1.114 Mnps | ~0% |
  | 3 | 351 | 0.956 (-14%) | 22% |
  | **6** | **~670 (+90%)** | 0.815 (-27%) | 53% |

- The real ceiling is **memory bandwidth, not cores.** `TT_BITS = 22` gives
  4.19M entries x 16 bytes = **67 MB of randomly-accessed TT per engine**
  against a 16 MB L3, so every probe already misses cache and extra engines
  contend for the memory controller. That is why per-engine nps still falls
  27% without oversubscribing a single core. Two consequences: throughput
  scales sub-linearly past 6, and this is an argument *against* the parked
  `ttsize` candidate (TT_BITS=24 would be 268 MB per engine).
- Contention is bandwidth-related, not scheduler-related, so it does not
  produce timing spikes -- but it is not free: 6 workers produced **1 time
  forfeit in 527 games** (0.2%) where 3 workers produced none. For a match
  measuring *time management* specifically, weigh that before turning it up.

### 12 workers for OFFLINE work, 6 for matches
Use all 12 logical processors for batch jobs with a fixed per-item wall-clock
budget (`tools/build_book.py`), never for a timed match. Measured:

| | idle | 6 workers | 12 workers |
|---|---|---|---|
| per-engine nps | 1.114 M | 0.815 M | 0.602 M |
| book positions/hour | -- | 2,037 | **3,333 (+64%)** |
| total nodes/hour | -- | 16.6 G | **20.1 G (+21%)** |

SMT genuinely pays here: each search gets 26% fewer nodes (about a quarter to
half a ply) but 64% more positions finish, and aggregate search work rises. The
job is wall-clock bounded per position and has no opponent, so oversubscription
only redistributes work. **A timed match is the opposite case** -- there,
contention is charged to an engine's own clock and distorts the measurement, so
stay at 6 or below. RAM is not the limit either way: 12 workers use 5.7 GB of
31.9 GB.
- A timed match is **wall-clock bound, not CPU bound**. Cores only let you run
  more games concurrently; they cannot make a single game finish sooner.
  - 60s + 0.5s  ~= 170 s per game
  - 10s + 0.1s  ~=  25 s per game

## Openings -- use the generated set, not the built-in 12
`tests/openings.py` has only **12** positions. A 500-game match replays each
~40 times, so games are heavily correlated, the SPRT's independence assumption
is violated, and **every error bar this project has reported was optimistically
narrow.** Use:

```
--openings tests\openings_gen.fen        # 400 positions, mean +4.2cp, sd 27.9
```

built by `tools\gen_openings.py` with our own engine (8-12 plies of top-K
moves, kept only if a 150 ms real search scores within +-50 cp). Regenerate
with a different `--seed` if a set ever needs replacing.

Do **not** use a foreign opening set without re-scoring it: a 300-position file
from another project was filtered by a textbook-PST eval and, scored with ours,
ranged **-1088 to +1240 cp** with only 129/300 inside +-50 cp.

## Pentanomial scoring
`--pentanomial` scores opening PAIRS (0/0.5/1/1.5/2) rather than single games,
cancelling the variance that opening imbalance contributes. It prints the
per-game LLR alongside so the saving is visible rather than assumed. Measured
gain on a balanced book with a high draw rate: **~1.03x, i.e. near nil** --
pairs are dominated by 1-1 outcomes when the openings are already level. Expect
it to matter more on a wider or less balanced book. It is validated by
`tests/test_sprt.py`, including the structural check that it reduces exactly to
the per-game LLR when pairs are independent.

## Statistical power — the rule that matters most
24 games produces roughly **+/- 80 Elo** error bars. That cannot resolve
anything smaller than about 100 Elo. Most real engine improvements are 5-30 Elo.

- To detect ~20 Elo you need roughly **400-1000 games**.
- **Never adopt a change whose measured effect is inside its own error bar.**
  Record the number, state that it is inconclusive, and revert. An inconclusive
  result is not a small positive result.
- Iterate at **10s + 0.1s**. Confirm only final candidates at 60s + 0.5s.
  At 10s + 0.1s with 6 workers you get roughly 670 games/hour; at the real
  120s + 0.5s you get roughly 70, so a 500-game run there costs ~7 hours.
- **Do not run an iteration match at the real TC to "avoid extrapolation".**
  Tried 2026-09-09 and abandoned: at ~36 games/hour (3 workers) an item-5-sized
  effect needing ~2400 games would have taken 68 hours. A fast-TC run that
  actually reaches a decision beats a slow one that never does. The prior
  belief that 10s+0.1s "cannot contain" a long-game clock defect is overstated:
  game length in moves is similar at both TCs, so a budget-shape defect shows up
  at both. Confirm the winner at the real TC afterwards.

## Sequencing
Run one experiment at a time and keep all 6 cores busy. Long single-threaded
stretches (self-play generation, tuning, JIT warmup) leave 5 cores idle — batch
those or overlap them with a match.

## What counts as a hard bug (outranks all tuning)
An illegal move, a crash, or a flag. Any of these: stop, reproduce, fix, then
re-run `tests\test_perft.py` and `tests\test_stress.py` before continuing.
