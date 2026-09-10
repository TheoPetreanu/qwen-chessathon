# Handoff brief — AI Chessathon engine

> **STALE IN PLACES — read `PROGRESS.md` (top section) first.** This file is a
> 2026-09-07 snapshot. As of 2026-09-10 the reference is `openingcap`
> (repfix+repfix2+item5+clockcap+syzygy+opening cap, +18 +/- 11 Elo) and an
> UNTESTED 6,888-entry opening book sits in `engine/ca_book.py`. Known stale below: the reference chain
> (now `syzygy`, not `repfix2`), `build/` (now synced, not v1), the live
> submission (v5 = `submission_clockcap.zip` is ACTIVE; syzygy was never
> uploaded), `--workers 3` (measured wrong, use 6), the 12-position opening set
> (use `tests/openings_gen.fen`, 400 positions), and item 5 (accepted). ACPL
> analysis was listed as never done; it was run 2026-09-08. Sections 2-5 (the
> hard rules and the repetition-bug narrative) are still accurate and are the
> most valuable part of this file.

Written for a reviewer coming in cold and asked "how do we make this better?".
Everything below is current as of 2026-09-07, late evening. Read `CLAUDE.md`,
`METHODOLOGY.md` and `TASK3.md` too — this file summarises and adds to them,
it does not replace them.

**What would be most useful from a fresh reviewer:** ideas we have not already
tried and rejected, and scrutiny of the reasoning below. Sections 8 and 9 list
open leads and the things most likely to be wrong.

---

## 1. What the engine is

A magic-bitboard chess engine compiled with numba (`@njit`), ~1.0-1.3M
nodes/sec, depth 15-23 at the competition time control. `python-chess` is used
**only** at the boundary — parsing the incoming FEN, and legality-checking the
move before returning it. It never appears in the search. That architecture is
the project's main structural advantage: a competent python-chess alpha-beta
(`baseline/agent.py`) runs at 28-36 knps, ~35x slower.

Search: iterative-deepening PVS/alpha-beta, aspiration windows, null-move
pruning, reverse futility, razoring, LMR, internal iterative reduction,
killers/history/counter-move ordering, quiescence with SEE pruning,
transposition table packed into one int64 + uint64 key.

Eval: hand-crafted tapered (material, PST, mobility, king safety, pawn
structure, bishop pair, rook files) plus SEE.

Layout:
- `engine/` — source of truth, the working copy
- `build/` — what gets zipped for submission (`agent.py` at the ROOT)
- `checkpoints/` — frozen snapshots; `REFERENCE.txt` names the current one
- `candidates/` — one directory per experiment, kept even when rejected
- `tests/`, `tools/`, `overnight_logs/`

Run everything with `.venv\Scripts\python.exe` (chess 1.11.2 + numba 0.67.0,
matching the competition image).

## 2. Hard rules — do not break these

1. **Bitboards are `uint64`, never `int64`.** Magic lookups, the de Bruijn
   bitscan and SWAR popcount rely on multiplication wrapping mod 2^64. Mixing
   uint64/int64 in one expression makes numba promote to float64. This has
   already caused one silent illegal-move bug.
2. **Steady-state time spend must stay strictly below the increment.** Budget
   is `0.80*inc + usable/28`, hard cap `min(2.5*soft, 20% of usable)`. The
   increment is *inferred* each move, never hardcoded.
3. `MAX_SEARCH_PLY = 100` is a hard cap — stacks are fixed size with numba
   bounds checking OFF, so overrunning corrupts memory rather than raising.
4. **One match at a time**, `--workers 3` (6 physical cores). Check the process
   list before every launch. Nothing else CPU-heavy while a match runs —
   duplicate/competing load has corrupted timing before.
5. **Never touch `build/`** until a change is proven.
6. Pure Python source only. No native binaries, no third-party engine or port,
   no shipped database of another engine's moves, no network. Stockfish exists
   in `tools/stockfish/` as a *sparring partner in tests only*.

## 3. Testing methodology (this is where most of the value is)

Original rule from `METHODOLOGY.md`: never adopt a change whose measured effect
is inside its own error bar; 24-game matches resolve nothing under ~100 Elo;
detecting ~20 Elo needs 400-1000 games; iterate at 10s+0.1s (~400 games/hour
with 3 workers), confirm finals at 60s+0.5s.

**Added this session — SPRT.** Fixed-N batches wasted 400 games on item 1
without an answer, so matches now stop as soon as they are decisive:

- `tests/sprt.py` — LLR maths. H0: elo0=0, H1: elo1=8, alpha=beta=0.025,
  bounds ±3.664, hard cap 1500 games → INCONCLUSIVE.
- `tests/test_sprt.py` — validates the formula (bounds, antisymmetry under
  symmetric hypotheses, linear scaling, monotonicity). **Read its docstring:**
  the "obvious" validation (replay item 1's numbers, expect no accept) is
  invalid, because those are absolute scores vs Stockfish, not head-to-head
  vs a reference. elo0=0 only means "no difference" when both sides of the
  record are the two engines being compared.
- `tests/gauntlet.py` — `--sprt` flag, shared stop event, per-game LLR check
  under the existing lock. Stop is checked at FEN (pair) boundaries so
  opening pairs stay intact for a possible future pentanomial upgrade.

Standard command:

```
.venv\Scripts\python.exe tests\gauntlet.py --a engine --amod agent ^
    --b checkpoints\<REFERENCE> --bmod agent --sprt --elo0 0 --elo1 8 ^
    --workers 3 --base 10000 --inc 100 > overnight_logs\<name>.log
```

**Operating rule added mid-session (user instruction):** cut any match that is
flat for 500+ games rather than grind to the 1500 cap. A near-zero true effect
is SPRT's slowest case to resolve, so the extra games buy nothing.

Per-candidate procedure: pre-flight (`REFERENCE.txt` matches `engine/`, no
match running) → build candidate into `engine/` → smoke test (legal moves from
3 FENs) → `tests/test_perft.py` (mandatory, 0 failures) → `test_stress.py`
only if `ca_movegen.py`/`ca_tables.py` changed → SPRT → accept (new checkpoint
+ update `REFERENCE.txt`) or revert → log to `PROGRESS.md` immediately.

## 4. THE BIG FINDING — repetition detection was dead

This is the single most important thing in this document.

`is_repetition()` in `ca_search.py` **could never return True**. `agent.py`
stored history one index per ply and `info[0]` put the current position at
index `rep_len-1`, so same-side-to-move ancestors sit at `rep_len-3, -5, ...`.
The scan started at `rep_len-2` and stepped by 2 — walking the **opposite
parity** chain. Since `compute_hash()` xors `ZOBRIST_SIDE` for black, those
entries can never equal the current key, and the rest of that chain was
placeholder zeros.

Effect: the search was **completely blind to repetition draws**. It never
scored a repeating line as 0, so it would shuffle into a threefold without
seeing it.

Fix (`repfix`): one line, `i = rep_len - 2` → `i = rep_len - 3`.
Result: **+41 ±18 Elo over 522 games, formal SPRT ACCEPT.**
Proof independent of Elo: `tests/test_repetition.py` — v1 fails it, fix passes.

**Follow-up (`repfix2`):** the fix made the existing history *usable*, but the
history was still half-fake — `agent.py` only recorded positions it was handed
(our turn) and wrote placeholder zeros between them, so opponent-to-move
repetitions still could not match real game history. Nothing is genuinely
unknown: every position is either one we were shown or one reachable by
applying our own move. `_SEEN` + placeholders was replaced by `_HIST`, a true
ply-by-ply chain. Also fixed: the forced-move fast path (`len(legal)==1`)
returned without recording anything, punching holes in the chain.
`tests/test_history_chain.py` verifies this (old code records 4 of 8 plies and
0 of 2 forced-move plies).

`repfix2` measured **+14 ±22 (inconclusive)** and was **adopted on correctness
grounds, explicitly not on the Elo number** — the justification is a proven
defect, same basis as `repfix`.

## 5. Methodology lesson worth internalising

Across items 2-5 we played **2,918 self-play games at a 75.4% draw rate** and
never noticed the bug. Three reasons, all worth fixing in any future harness:

1. **A/B self-play is structurally blind to defects both sides share.** Every
   match was candidate vs our own reference; both had identical repetition
   blindness, so it contributed exactly zero to the measured *difference*. The
   bug was only visible against foreign opponents — i.e. in live results.
2. **The harness collapsed all draws into one bucket** (`arena.play` returned
   just `"draw"`). Now returns `draw:threefold` / `draw:stalemate` /
   `draw:fifty` / `draw:material` / `draw:other`, and `gauntlet.py` shows a
   live `3fold=N (X%)` counter plus a termination breakdown.
3. **No expected draw rate was ever recorded**, so 75% never looked wrong.

Generalisation: watch absolute behaviour (termination mix, draw rate, node
rate) alongside relative Elo. Relative testing cannot see shared defects.

## 6. Results so far

Reference chain: `v1` → `repfix` → `repfix2` (current).

| change | games | score | Elo | verdict |
|---|---|---|---|---|
| v1 baseline vs SF@2500 | 200 | 60.0% | +70 ±39 | reference point |
| #1 easy-move early stop | 400 | 62.0% | +85 ±25 | REJECTED (inconclusive, z≈0.6) |
| #2 continuation history | 639 | 49.9% | −1 ±13 | REJECTED (flat) |
| #3 history gravity | 1017 | 50.3% | +2 ±10 | REJECTED (flat) |
| #4 improving flag | 376 | 44.7% | **−37 ±18** | REJECTED (formal SPRT reject) |
| #5 LMR shaping (vs v1) | 881 | 51.9% | +14 ±11 | unfinished, cut to chase the bug |
| **repfix** | **522** | **55.9%** | **+41 ±18** | **ACCEPTED (formal)** |
| repfix2 | 495 | 52.0% | +14 ±22 | adopted on correctness |
| contempt 20cp | 530 | 47.1% | −20 ±22 | REJECTED |
| #5 LMR shaping (vs repfix2) | 853 | 52.6% | +18 ±18 | INCONCLUSIVE, not adopted |

Notes on the rejections:
- **#4 (improving flag) is the interesting failure.** −37 Elo is large. Node
  rate was 1.095 vs 1.121 Mnps (only ~2% slower, `tools/measure_nps.py`), so it
  was **not** a speed regression — it was a genuine search-quality loss.
  `improving` goes false on any minor eval dip, so stacking an extra full-ply
  LMR cut on top of existing reductions in that (common) case diluted search
  effort. Not conclusively root-caused; a gentler version might work.
- **contempt at 20cp was mechanically effective and directionally wrong**:
  threefold draws collapsed to 21%, but 132W/163L. Reading: repetitions arise
  in positions our eval can't judge reliably, so declining them loses more than
  it wins. **Important caveat: self-play is the weakest possible test for
  contempt**, since its whole value is converting draws to wins against
  *weaker* opposition, and the self-play opponent is a near-identical twin. A
  smaller value (~8-10cp) targeting self-play-neutral is untested.
- **#5 is a persistent small positive that neither sample can resolve** — +14
  in both independent matchups (vs v1 and vs repfix2), LLR flat around +0.7.
  Likely a real ~10-15 Elo effect, below what the test is powered for.
  Resolving it properly would need ~2000+ games.

## 7. Competition context

Platform: aichessathon.com. Team "Endgame" / "testrun1". Submission = `build/`
contents zipped with `agent.py` at the ROOT, max 10 submissions per 24h.
Rounds run roughly hourly. Time control **120s + 0.5s/move**, 90s init budget
(we use 37-44s of it for numba JIT).

Ratings start at 1500 and converge from below, so an underrated engine needs
many games to climb — and **a draw against an equal-rated opponent moves you
exactly 0**, while a draw against a lower-rated one loses rating. This is why
the repetition bug was costlier than +41 Elo suggests: it converted roughly
half our games into rating no-ops.

Live results, rounds 46-60 (**rounds 46-58 pre-fix, 59-60 post-fix**):
- Pre-fix, 13 games: 6W 7D 0L, **53.8% draws** (White 2W 5D, Black 4W 2D)
- Post-fix, 2 games: 1W 0D 1L — far too few to read
- For comparison the then-#1 team was 29W 8D 4L (**19.5% draws**), rating 2637

**Caution for the reviewer:** an earlier analysis in this project made a lot of
a "perfect colour split" (White always drew, Black always won). With more games
that was **small-sample noise** — it is 2W 5D as White across 7 pre-fix games,
not 0W 4D. The bug it pointed at was real and independently proven, but the
clue itself was weaker than it looked. Don't over-read 4-game patterns.

## 8. Open leads / untried ideas

- **Finish #5** properly (~2000 games) or discard it. Currently unresolved.
- **Contempt at a smaller value** (8-10cp), or contempt scaled by material
  rather than flat. Test design matters more than the value: self-play
  systematically undervalues it. Consider measuring against a *weaker*
  opponent (`tests/sf_agent.py` takes `SF_ELO`) to mirror competition
  conditions, comparing two candidate-vs-SF scores rather than head-to-head.
- **Item 6, singular extensions** — the one item from `TASK3.md` never
  attempted. Explicitly deferred as needing a manually reviewed diff.
- **Pentanomial scoring** in the SPRT (score opening pairs 0/0.5/1/1.5/2
  instead of individual games). The gauntlet already plays both colours of each
  FEN adjacently, so the structure is there. Cuts variance materially.
- **ACPL analysis** — ~~never done~~ **DONE 2026-09-08**, see `acpl_report.csv`
  (320 rows) and `tools/acpl_analysis.py`. It showed 4 of the 5 archived draws
  were thrown wins (peaks +331 to +9920cp, each surrendered by accepting a
  repetition) — the repfix bug, from the pre-fix era. Still **not** done for
  recent games: the dashboard CSV export carries results and clocks but no move
  data, so fresh PGNs are needed to extend it.
- **Eval quality generally.** Every search-side item (2,3,4,5) came back flat
  or negative, while the one *correctness* fix was worth +41. That pattern
  suggests the search is reasonably tuned and the remaining upside may be in
  evaluation — but see the explicit out-of-scope list below.
- **Time management** — `MOVES_TO_GO=28` was tested at 45 and was inconclusive
  (+29 ±81 fast TC, +14 ±64 real TC). Untuned since. Note games run 32-69
  moves in live play.
- **Opening book** — `tests/openings.py` has only **12** positions, so a
  400-game match reuses each ~33 times. Fine for relative testing but a wider
  book would reduce correlation between games.

## 9. Out of scope (already decided, do not re-propose)

- **NNUE / any trained evaluator** — needs a dataset and training pipeline the
  project doesn't have.
- **Texel tuning** — already attempted and measured at **−99 Elo** from only
  2,571 positions. Would need 200k+ positions.
- Anything third-party inside `engine/`, `build/` or the zip.

## 10. Things in this session's reasoning most likely to be wrong

Listed deliberately so a reviewer knows where to push:

1. The explanation for **why #4 lost 37 Elo** is a plausible story, not a
   verified root cause.
2. **repfix2 was adopted while Elo-inconclusive.** Justified on correctness,
   but it is a deviation from the project's own adoption rule and could be
   argued the other way.
3. The claim that **contempt fails because the eval can't judge repetition
   positions** is an inference from one 530-game run at one value.
4. **#5's "+14 in both matchups"** is presented as corroboration, but the two
   runs used different references and cannot be pooled.
5. Early in the session `is_repetition()` was reviewed by eye and declared
   **"not a bug"** — reading the code was not enough; only tracing indices
   exposed it. Assume other functions may have the same class of defect and
   have not been index-traced.

## 11. Current state / how to resume

- `checkpoints/REFERENCE.txt` = `repfix2`, and `engine/` has been restored to
  match it (verified with `diff -rq`). **No match is running; the machine is
  idle.**
- `build/` is **still v1** — deliberately untouched; the shipped zips were
  built directly from checkpoints.
- Zips built: `submission_repfix.zip`, `submission_repfix2.zip` (the latter is
  the current best and what should be uploaded).
- All SPRT logs are in `overnight_logs/`.
- To restore the reference at any point: copy the 6 files from
  `checkpoints/repfix2/` over `engine/` and confirm with `diff -rq`.

Validation commands:

```
.venv\Scripts\python.exe tests\test_perft.py            # must be 0 failures
.venv\Scripts\python.exe tests\test_repetition.py engine
.venv\Scripts\python.exe tests\test_history_chain.py engine
.venv\Scripts\python.exe tests\test_sprt.py
.venv\Scripts\python.exe tools\measure_nps.py engine    # not during a match
```
