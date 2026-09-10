# Progress log

> **START HERE (2026-09-10):** the most recent entry is the **`## AUTOSAVE
> 2026-09-10`** section at the BOTTOM of this file -- it was appended, not
> prepended, so it is out of the usual newest-first order. It records the
> saved book, the shipped zip, and the prioritised next steps. Read it before
> anything else. Current reference: `checkpoints/REFERENCE.txt` = `openingcap`.


Methodology: `tests/gauntlet.py --a engine --amod agent --b tests --bmod sf_agent
--pairs 100 --base 10000 --inc 100 --workers 3` (200 games per batch, 10s+0.1s,
Stockfish pinned at UCI_Elo 2500 via UCI_LimitStrength). This is the fast
iteration TC from METHODOLOGY.md. One match at a time, verified via process
list before every launch. `tests/test_perft.py` green (0 failures) both before
and after this session's work.

Absolute-rating caveat (still applies, from NO_STOCKFISH.md / TASK2.md):
Stockfish's `UCI_Elo` scale is Stockfish's own approximation, not calibrated to
FIDE/CCRL. All numbers below are "roughly this band" relative to that anchor,
useful for comparing our own versions against each other, not a certified
external rating. Anchoring off SF@2500, the baseline number below corresponds
to roughly 2531-2609 (~2570 point estimate) on that approximate scale.

## Why 2,918 of our own test games did not catch the repetition bug

Worth recording, because it is a methodology hole, not bad luck. Across the
item 2-5 SPRT runs we played 2,918 games at 10s+0.1s from balanced openings
and drew **75.4%** of them (item2 76.6%, item3 76.0%, item4 71.8%, item5
75.4%). That draw rate is the bug's fingerprint, and nobody could read it:

1. **A/B self-play is structurally blind to bugs both sides share.** Every
   match was candidate vs `checkpoints/v1`, and both sides had identical
   repetition blindness. SPRT measures a *difference* between two engines; a
   defect present in both contributes exactly zero to that difference. The
   bug was only visible against foreign opponents -- i.e. in the live
   competition results, which is where it was actually found.
2. **The harness collapsed every draw into one bucket.** `arena.play()` did
   `reason = "mate" if board.is_checkmate() else "draw"`, so threefold,
   stalemate, fifty-move and insufficient-material were indistinguishable in
   every log we produced.
3. **The anomaly detector only watches crash/illegal/flag/malformed.** An
   implausible draw rate is not a category it knows about.
4. **No expected draw rate was ever recorded**, so 75% never looked wrong.

Fixed: `arena.play()` now returns a specific reason (`draw:threefold`,
`draw:stalemate`, `draw:fifty`, `draw:material`, `draw:other`), and
`tests/gauntlet.py` keeps a per-reason tally, shows a running
`3fold=N (X%)` counter on every game line, and prints a full termination
breakdown in the FINAL summary. The `draw:` prefix keeps the existing
anomaly check (which splits on `:`) working unchanged.

Standing lesson: **a self-play A/B harness cannot detect a defect shared by
both sides.** Absolute-behaviour checks (termination mix, draw rate, node
rate) need to be watched alongside relative Elo.

## UPDATE 2026-09-09: opening hard-cap ADOPTED (+18 +/- 11, 1388 games);
## position pool fully enumerated at 308; depth-6 book build running

**Opening hard-cap ACCEPTED and promoted.** `checkpoints/openingcap/`,
`REFERENCE.txt` -> `openingcap`. The change is `OPENING_MOVES = 8` /
`OPENING_HARD_MULT = 1.3`, capping only `hard` (normally `2.5 * soft`) for our
first 8 moves and leaving `soft` untouched, plus passing `_MOVE_NUMBER` into
`_think_time` and resetting it on new-game detection.

**Result: 1388 games, +298 =862 -228, 52.5%, +18 +/- 11 Elo.** SPRT
`--pentanomial`, 6 workers, 400 generated openings, vs `checkpoints/syzygy`.

**Disclosure on the verdict, because it is not a clean formal accept.** The LLR
**crossed the +3.664 accept bound at game 1382 (+3.70) and registered ACCEPT**,
then in-flight pairs on the other five workers completed and it settled at
**+3.488**, so the run's final printed status is INCONCLUSIVE. Standard SPRT
practice is that the first bound crossing IS the decision and continuing past
it is optional continuation (which biases toward the null) -- but the trailing
games exist only because `_stop` breaks at pair boundaries, so this reading is
favourable to us and is flagged as such. Independent of the LLR, the 95% CI is
**[+7, +29], which excludes zero**, satisfying METHODOLOGY.md's actual adoption
rule on its own terms. Adopted on that basis. A confirming run pooled with this
one (the route that resolved item 5) is the clean follow-up if ever wanted.

Two flags occurred, **one caused by each engine** -- symmetric, consistent with
the 6-worker memory contention documented in METHODOLOGY.md, not a defect in
the change. Pentanomial measured **1.06x** the per-game LLR (3.488 vs 3.304):
real but small, and the pair table shows why -- 48.8% of pairs are 1-1.

**Mechanism, validated before the match rather than after:** opening spend
53.3s -> 41.9s, clock after move 8 70.7s -> 82.1s, **move-9 budget 2.91s ->
3.32s (+14%)**. On a real middlegame the cap cut the allowance 11.69s -> 6.08s
and the search still reached **depth 17**, identical to baseline. This is the
property `MOVES_TO_GO=45` lacked, and is why that one measured -3 while this
measured +18: a uniform divisor scales every move down and hoards the
remainder, a cap on the early ceiling redistributes it.

**Position pool: FULLY ENUMERATED at 308.** 3,506 games harvested from public
team pages; 308 distinct start FENs, **0 singletons**, Chao1 = 308 exactly.
Zero singletons with the estimator converged on the observed count is complete
saturation -- there is nothing left to find.

**CORRECTION -- the coverage table below is IN-SAMPLE and badly optimistic.**
It was measured on the same games the book was built from, so it is guaranteed
to look good. A held-out split (1,757 train / 1,757 test) gives the honest
out-of-sample hit rate per move:

| | move 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| in-sample (wrong) | 100% | 97% | 96% | 96% | 96% | 96% |
| **held-out (real)** | **87%** | **43%** | **21%** | **10%** | **4%** | **2%** |

Coverage collapses with depth because deep lines are singletons: **87% of the
27,584 depth-6 targets occur exactly once in 3,523 games** (99% at d6, 93% at
d4, 66% at d2, 15% at d1). A future game deviates one move and misses.

**Consequences, both important:**
1. **The book is worth ~10-12s per game, not ~43s.** About 5s of that is move 1
   alone (308 positions); depths 4-6 are ~15,000 positions for roughly **1
   second combined**. Building deep is almost pure waste.
2. **A second claim of mine was also wrong: at 10s/position the stored moves
   are WEAKER than live play, not stronger.** In a real game the engine runs
   uncontended at 1.114 Mnps, so a 5.89s live move searches ~6.6M nodes, while
   a 10s book entry built under 12-worker contention (0.602 Mnps) searches only
   ~6.0M. To genuinely beat live play the book needs ~30s/position (18.1M
   nodes, 2.7x live).

Rebuilt accordingly: **depth 3, 30s/position** -- 9,680 targets instead of
27,584, same clock benefit, finishes sooner, and the entries are finally
stronger than what we would have played. The 10s cache is archived at
`tools/book_cache_10s.jsonl`, superseded.

**In-sample coverage table (kept for the record, do NOT quote it as coverage):**

| replies stored | our move 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| top-1 | 100% | 72% | 61% | 57% | 55% | 54% |
| top-2 | 100% | 91% | 88% | 87% | 86% | 86% |
| **top-3** | 100% | 97% | 96% | 96% | 96% | **96%** |

Engine play from these positions is highly convergent, so coverage barely
decays past move 2. Our first six moves cost **42.9s** of a 120s clock, and all
seven losses in rounds 46-81 finished under 10s, so this is the largest single
lever identified so far -- bigger than any +/-20 Elo search tweak.

**Build running:** `tools/build_book.py --depth 6 --topm 3 --ms 10000
--workers 6`, 12,726 targets (d1=308, d2=1636, d3=2331, d4=2680, d5=2834,
d6=2937), ~7h. Targets are ordered **shallowest-first** so an interrupted run
still yields complete coverage of the early moves rather than an arbitrary
alphabetical slice; results append to a resumable JSONL cache.

**Stockfish must NOT be used to generate this book.** It would be precisely the
"shipped database of another engine's moves/evals" the project rules forbid,
regardless of opening books being permitted in general -- a book of Stockfish's
moves is not the same artifact as a book of ours. Stockfish may *measure* the
finished book (same status as any test) but must never *select* an entry, or
its judgement is laundered into the shipped zip.

## UPDATE 2026-09-09: the start-position pool is PUBLIC and FINITE (~330), so a
## self-computed opening table is viable after all

**Every game on aichessathon.com is publicly browsable with a downloadable
PGN** (user pointed this out; `/team/<uuid>` lists a team's games,
`/game/<uuid>` carries the full PGN with the start FEN embedded in the Next.js
payload). `tools/fetch_games.py` harvests them. This is public scouting data,
read-only.

**Measured pool size, from 1290 harvested games across 44 teams: 276 distinct
start positions and still rising slowly; Chao1 ~326, birthday ~366.** So the
pool is roughly **300-370 positions**, finite and enumerable.

**This corrects an earlier estimate in this file of ~36 positions**, which came
from 9 games with a single collision -- small-sample noise of exactly the kind
section 7 of HANDOFF.md warns about. Validation that the harvest is the real
pool: **4 of our own 8 known start FENs appear in it**, which is precisely the
~50% expected when about half the pool has been sampled.

**Consequence for the opening table.** Learning positions from our own games
alone would reach ~84 of ~330 after 84 rounds (25%) -- too weak. But the whole
pool can simply be harvested, then precomputed offline. `tools/build_book.py`
searches each position far longer than we could afford at the board and writes
`engine/ca_book.py`, so a hit is instant *and* stronger than the live search.
Every move is our own engine's; no third-party book is involved (generic
polyglot books were separately shown not to cover these positions at all).

**Coverage subtlety, and the fix.** Each pooled position has a side to move.
When we are that side we get a hit; when we are the other colour the opponent
moves first and we are handed a position one ply deeper that is not in the
pool -- so a naive table fires on only ~50% of games. Measured from the
harvested games, **opponent replies are highly concentrated: the most common
reply accounts for a mean 74% / median 69% of games from a given position**
(142 positions with >=3 games). So `--expand 2` precomputes the replies that
actually occur rather than guessed ones, lifting coverage to ~90%+ for roughly
3x the compute. Expect ~5.4s saved per game on average at ~5.9s per hit.

Integration in `agent.py` sits after the forced-move and tablebase
short-circuits: dict lookup on the raw first four FEN fields **as handed to
us** -- deliberately not normalised through python-chess, whose `ep_square` is
set after any double push while the referee emits the field only when the
capture is legal (the bug `_hash_after` already had to fix). The move is
legality-checked before use and any miss, malformed entry or missing module
falls through to normal search, so the table can never cost a game. Verified to
degrade correctly with no book present.

**Not yet built:** the precompute needs the machine and the opening-cap SPRT
has it (rule 4). Note also `candidates/openingcap/` is the artifact under test;
`engine/` additionally carries the book-lookup code, which is a no-op while
`BOOK` is empty but means the two are not byte-identical -- do not confuse them
when the SPRT reports.

## UPDATE 2026-09-09 (later still): MOVES_TO_GO=45 REJECTED with a mechanism;
## harness throughput +90%; openings 12 -> 400; opening-cap candidate under test

**`MOVES_TO_GO` 28 -> 45: REJECTED. 527 games, +103 =316 -108, -3 +/- 19 Elo,
LLR -0.70** (10s+0.1s, 6 workers, vs `checkpoints/syzygy`). Decisively inside
its own error bar; the prior +29 estimate is now excluded by the CI and +14
sits at its edge. Reverted, saved to `candidates/movestogo45/`.

**The mechanism matters more than the number, because it kills a whole family
of ideas.** A bigger divisor does not move time from the opening to the
endgame -- it lowers *every* move's budget uniformly and simply ends the game
with the surplus unspent. The clock model built this session predicted exactly
this and it was misread as a benefit at the time: "37.7s left at move 60 vs
18.5s" is not more thinking time available later, it is **~19 seconds the game
ends without ever using.** Both configurations play the same 60 moves; MTG=45
just thinks less on all of them. That also retro-explains `reservewiden`
(-50 Elo): holding back a reserve is the same hoarding error, more
aggressively. **A uniform scale factor cannot redistribute. Only a shape
change can.**

**Live results updated (rounds 46-81, 36 games).** The clock signal is now much
sharper than when `clockcap` was written:

| result | n | mean clock left | under 10s |
|---|---|---|---|
| Win | 14 | 11.2s | 7/14 |
| Draw | 15 | 16.3s | 7/15 |
| **Loss** | **7** | **5.7s** | **7/7** |

**Every loss finished under 10 seconds.** Confound acknowledged and not
overstated: losing positions run longer (losses average 63 moves), so low clock
is partly a *consequence*. Note also the 73.1% -> 52.2% pre/post-repfix score
drop is most likely **rating convergence, not regression** -- we start at 1500
and climb into stronger opposition, and the pre-fix 73% was inflated by 54%
draws that move rating by ~0 against equal opponents.

**Harness throughput +90%, by measurement.** `--workers 3` was based on
counting engine *processes* (2 per worker) rather than *active* ones -- the
idle engine in each worker blocks on stdin at ~0% CPU, so 3 workers used 3 of
6 cores. Measured: 3 workers = 351 games/hr @ 0.956 Mnps; **6 workers = ~670
games/hr @ 0.815 Mnps**; idle baseline 1.114 Mnps. The binding constraint is
**memory bandwidth, not cores** -- `TT_BITS=22` is 67 MB of random-access TT
per engine against a 16 MB L3. Two consequences recorded in `METHODOLOGY.md`:
scaling past 6 is sub-linear, and this argues *against* the parked `ttsize`
candidate (TT_BITS=24 = 268 MB/engine). Cost: 6 workers produced **1 time
forfeit in 527 games** (0.2%), against the reference, where 3 workers produced
none.

**Openings 12 -> 400.** `tests/openings.py`'s 12 positions were replayed ~40
times each in a 500-game match, so games were heavily correlated and **every
error bar this project has published was optimistically narrow.** New
`tools/gen_openings.py` builds a set with our own engine (8-12 plies of top-K
moves, kept only if a 150 ms real search scores within +-50 cp):
`tests/openings_gen.fen`, **400 positions, mean +4.2cp, sd 27.9**, 0 duplicates,
0 decided. `gauntlet.py` gained `--openings`. A foreign 300-position set was
evaluated first and **rejected**: scored with our eval it ranged -1088 to
+1240 cp (only 129/300 within +-50), because it had been filtered by a
textbook-PST eval at 1200 nodes.

**Pentanomial scoring built and validated** (`sprt.llr_pentanomial`,
`--pentanomial`, 5 new checks in `test_sprt.py`, all pass). Key structural
check: with independent pairs it reproduces the per-game LLR to full precision,
so any gain is real correlation rather than a normalisation artifact. **Measured
gain: ~1.03x, i.e. near nil** on a balanced book with 58% draws -- pairs are
dominated by 1-1 outcomes. Reported honestly rather than assumed; it should
matter more on a wider book.

**Opening book: definitively dead, now on three independent grounds.** Five
polyglot books tested (21.7k to 11.1M entries) with a harness validated against
startpos/Sicilian/Catalan/Nimzo first. Best case (`book.bin`, 11.1M entries)
covered 5/8 of our start FENs and 7 of our moves across 9 games (~5.4s saved) --
but it is **178 MB against a 50 MB cap**, only reaches 1-3 moves deep, and in
5 of those 7 moves it *disagreed* with what we played. Decisive detail: in
`codekiddy.bin`, which has informative weights, our positions score **4 and 10
against 5,438-11,035 for mainline theory** -- a ~1000x gap. A "book move" for
our positions means one or two games in a million-game corpus once played it,
which is weaker evidence than our own 6-second search. Books are statistical,
not solved; only tablebases are perfect.

**Foreign project reviewed (`chessbot-cursor-chess-engine`), nothing adoptable.**
python-chess based, ~31k nps / depth 8 (~35x slower than ours, same class as our
`baseline/`). All three of its shipped wins -- passed pawns, razoring, reverse
futility -- we already have, and ours are better (their passed-pawn table is
flat 10/20/35/60/90/140; ours is tapered, MG 4/6/12/26/50/90 and EG
10/18/32/58/100/160). Useful corroboration though: they attempted Texel tuning
four times (-47, -6, +17, +4) and reverted all four, concluding 92k shallow
self-play positions contain no 10-Elo eval signal once overfitting is blocked.
We measured -99 Elo independently. **Texel is now closed by two independent
projects.** Their code was read but not copied; only `openings.fen` was used,
and only to be re-scored and then rejected.

**Latent bug found and fixed: `_MOVE_NUMBER` was never reset between games.**
Harmless in competition (the referee gives each game a fresh process) but wrong
in testing, where `arena.Engine` is created once per worker and reused for every
game in its slice. Anything keyed on the move number would have applied only to
the first game of a match. Now reset in the `_is_new_game` branch alongside
`_HIST`, and covered by the smoke test.

**Candidate under test: opening hard-cap.** `OPENING_MOVES = 8`,
`OPENING_HARD_MULT = 1.3` (vs the normal `2.5 * soft`), capping only `hard` and
leaving `soft` untouched, so `usable` stays higher and the existing
`soft = 0.8*inc + usable/MOVES_TO_GO` gives every later move a bigger budget by
itself. **Mechanism validated before spending any games** (the lesson from
MOVES_TO_GO):

| | opening spend (8 moves) | clock after move 8 | move-9 budget |
|---|---|---|---|
| baseline | 53.3s | 70.7s | 2.91s |
| candidate | **41.9s** | **82.1s** | **3.32s (+14%)** |

Later moves get *more*, which is the property MOVES_TO_GO lacked. Also checked
directly: on a real middlegame position the cap cut the allowance 11.69s ->
6.08s and the search **still reached depth 17**, identical to baseline -- and
the hard deadline is enforced exactly (overshoot +0.00s; an apparent 48%
overshoot seen earlier was an artifact of a smoke test passing a constant clock,
which made `_observe_increment` infer a garbage increment). Gates green: perft,
repetition, history-chain, tt-mate all 0 failures; diff vs reference is the
intended lines only. Saved to `candidates/openingcap/`. **SPRT running** vs
`checkpoints/syzygy` at 10s+0.1s, 6 workers, `--pentanomial`, 400 openings:
`overnight_logs/openingcap_sprt_run1.log`.

## UPDATE 2026-09-09 (later): live-version question RESOLVED; opening book killed
## on evidence; MOVES_TO_GO=45 under test at the real TC

**Which zip is live -- ANSWERED, closing the `REVIEW_FINDINGS.md` Phase 0
blocker.** The user supplied the dashboard's submission list; sha256 prefixes
of the local zips match its hashes exactly:

| dashboard | hash | file | status |
|---|---|---|---|
| v5 | `88e59cf35602` | `submission_clockcap.zip` | **ACTIVE** |
| v4 | `168bbc1a8077` | `submission_item5.zip` | superseded |
| v3 | `68ad8ffcb81a` | `submission_repfix2.zip` | re-upload of v2 (same hash) |
| v2 | `68ad8ffcb81a` | `submission_repfix2.zip` | superseded |

**`submission_syzygy.zip` was never uploaded -- there is no v6.** Everything
live, rounds 76-79 included, is `clockcap`. Any claim that recent results
reflect Syzygy is wrong.

**Live results, rounds 46-79 (34 rated games), split at repfix (round 58/59):**

| segment | games | W-L-D | draw% | score% | mean moves | mean clock left |
|---|---|---|---|---|---|---|
| pre-repfix 46-58 | 13 | 6-0-7 | 54% | 73.1% | 37 | 16.9s |
| post-repfix 59-79 | 21 | 8-5-8 | 38% | 57.1% | 60 | 10.0s |

repfix did what it was meant to (draws 54% -> 38%) but **roughly doubled mean
game length, 37 -> 60 of our own moves, tail to 154**, which pushed the engine
into the regime where the clock starves: games <10s left went from 3/13 to
16/21, and <5s from 1/13 to 7/21. Games >=60 moves score **50.0%** vs **68.8%**
for shorter ones. All five losses finished under 10s. Caveat, stated so it is
not over-read: hard games are naturally longer, so this correlation is
confounded as *motivation* -- but a self-play A/B on one constant is a
controlled experiment, so the confound does not touch the test itself.

**Where the clock actually goes -- measured from the 9 archived PGNs:**
mean spend on our first 8 moves is **53.3s**, and 63.3s over the first 10 --
over half the 120s base, while still in the opening. Then games finish at
1.4-10s. (Note the earlier "1.4s risks flagging" worry is WRONG: the emergency
branch at `agent.py:134` caps soft to ~0.365s at that clock, below the 0.5s
increment, so it is stable by design. This is a strength argument, not a
safety one.)

**Opening book: killed on evidence this time, not on argument.** Downloaded
three polyglot books (`gm2600` 21,671 entries, `komodo` 578,126,
`codekiddy` 1,030,253; kept in `tools/books/`, test-only, same permitted status
as `tools/stockfish/`). Harness validated first -- it finds startpos, 1.e4 c5,
the Catalan and the Nimzo with sensible high-weight moves. Then: **only 3 of
our 8 competition start FENs appear in the 1.03M-entry book at all, two of them
at weight 4 and 10** (i.e. essentially no games ever reached them). Replaying
all 9 real games with the *actual* opponent replies: **2 of our moves covered
across 9 games.** The organizers evidently pick positions that are near-level
AND off-theory, which is what you would design to make engines think rather
than replay book. The earlier dismissal was right; it is now backed by a
measurement rather than an inference.

**Also corrected: `HANDOFF.md` lists ACPL analysis as "never done".** It was run
2026-09-08; `acpl_report.csv` has 320 rows. It is what showed 4 of the 5
archived draws were thrown wins (peaks +331 to +9920 cp, each surrendered by
accepting a repetition) -- i.e. the repfix bug, from the pre-fix era. No ACPL
exists for recent games because the dashboard CSV export carries no move data;
that needs PGNs.

**Candidate under test: `MOVES_TO_GO` 28 -> 45.** Chosen over the alternatives
(reservewiden: new logic, -50 Elo in run1; contempt: docs concede self-play is
the wrong test; singular extensions: needs a hand-reviewed diff; ttsize: real
but its case is theoretical). Rationale: one constant, no new code path; two
earlier tests of *exactly 45* both came back positive but underpowered
(+29 +/- 81 fast TC, +14 +/- 64 real TC) -- the item-5 signature; and the
regime moved under it (budget provisions for 28 moves, live games now average
60). Diff vs `checkpoints/syzygy` verified to be **that constant and nothing
else** -- the project has been bitten twice by candidates carrying confounds.
Gates green: perft 0 failures, `test_repetition` 0, `test_history_chain` 0,
smoke test 3/3 legal (startpos 3.64s vs ~5.9s at MTG=28, and KPvK returned in
0.00s confirming the Syzygy path fires).

**SPRT running at the real competition TC, 120s+0.5s** -- not 10s+0.1s, which
under-represents a defect that only exists in long games at a 120s base --
vs `checkpoints/syzygy`, 3 workers, logging to
`overnight_logs/movestogo45_sprt_run1.log`. ~36 games/hour (engines are created
once per worker, `gauntlet.py:47`, so the ~40s JIT is paid 3 times total, not
per game). Note for whoever reads the result: the smoke test showed a search
overshooting its own hard cap (9.0s against a 7.65s hard limit), which is also
why the deterministic clock model built this session overpredicted remaining
time by 15-23s against all 34 live games. Worth a look independently of this
test.

## UPDATE 2026-09-09: session self-audit -- caught a real confound, and closed out reservewiden run2

At the user's request, re-checked the last several steps for anything missed.
Found one real mistake and fixed it before anything was tested on it:

**`engine/agent.py` had the unresolved `reservewiden` recalibration (run2,
still mid-flight/never concluded, see below) and the Syzygy integration
stacked together** when `candidates/syzygy/` was first saved -- the same
class of mistake as the `ttsize`-leaking-into-`reservewiden` catch earlier
this session, just missed a second time. Confirmed via diff (`ca_search.py`,
`ca_eval.py`, `ca_movegen.py`, `ca_tables.py`, `ca_position.py` were all
already clean; only `agent.py` had the confound). Fixed by resetting
`engine/agent.py` to `checkpoints/clockcap`'s exact version and re-applying
only the Syzygy edits on top -- verified the resulting diff against
`clockcap` is now pure additions plus one no-op refactor (the forced-move
path's inline history code became a call to the new shared
`_record_short_circuit` helper, byte-for-byte equivalent). Gates re-run
green, smoke test re-confirmed (KRvK/KRPvK ~0.015s via tablebase, ordinary
positions unaffected). `candidates/syzygy/` re-saved from the corrected
state. The Syzygy section below has been written from this corrected
baseline throughout, not the confounded one.

**`reservewiden` run2's actual fate, since it was never formally closed
out:** stopped mid-flight (168 games, +52=59-57, -10 Elo +/- 43, LLR -0.25)
when it turned out to be the forgotten background match from the init-time
investigation below, not because of a score-based decision. 168 games and a
+/-43 CI is nowhere near enough to call this a reject the way run1's stable
152-game -50 +/-45 was -- this is genuinely inconclusive, not negative.
**Parked, not reverted**: `candidates/reservewiden/` already holds the
correct recalibrated (growth=6, cap=1200) version (verified). `engine/` moved
on to `clockcap` + Syzygy rather than back to plain `clockcap`, since
Syzygy's own baseline is `clockcap` regardless. If there's ever budget to
revisit it, it would need a fresh, uninterrupted run rather than treating
these 168 games as informative either way.

`build/` reconfirmed untouched and still exactly `checkpoints/clockcap`
throughout all of this (the Syzygy/reservewiden work only ever happened in
`engine/`, per the standing rule).

## UPDATE 2026-09-09: Syzygy PROMOTED; opening book ruled out; TT mate handling verified clean

**Syzygy promoted** to `checkpoints/syzygy/`, `REFERENCE.txt` -> `syzygy`,
`build/` synced, **`submission_syzygy.zip` built and validated end-to-end**
(extracted fresh to a scratch dir, confirmed content-identical to `build/`,
and confirmed the agent actually loads the tables and returns legal moves when
run from the extracted copy -- the path resolution matters since it's relative
to `agent.py`). 32.9MB uncompressed, well inside the 50MB cap. Adopted on the
correctness/safety basis stated in the correction below, NOT on a proven Elo
number. User will upload it.

**Opening book: ruled out, do not spend time on it.** Checked the premise
before building anything this time. **Every competition game starts from a
curated FEN at move 6-11** -- confirmed directly from the PGN headers
(`[SetUp "1"]` + `[FEN ...]` on all 9 local games, e.g. R54 starts at move 9,
R59 at move 11). A standard polyglot book is keyed on positions reached from
the initial position, so it would mostly miss outright; and even on a hit
we'd skip 1-2 moves (~2-6s), not the "10-15s in the first 10 moves" claimed,
because we are *already starting* past the opening. `REVIEW_TASK.md` said the
same thing in one line -- *"Games start from curated near-level positions, so
opening theory is devalued"* -- which, like the tablebase/R54 line, was
available the whole time. Second premise-check in a row that killed a
proposed task before effort was spent on it.

**New: `tests/test_tt_mate.py`, and TT mate handling is verified CORRECT.**
`REVIEW_TASK.md` Phase 1 flagged TT mate-score adjustment as untested, and it
was -- nothing covered it. Traced by hand first (store does `s += ply`, probe
does `s -= ply`, exact inverses; `MATE_IN_MAX = MATE - 256` safely covers the
`MAX_SEARCH_PLY = 100` range; the 16-bit +32768-biased score field holds
`+/-MATE` and `+/-INF` with headroom, no overflow) -- but per the `repfix`
lesson, reading and agreeing is not evidence, so it is now actually tested
against the real compiled search:
  1. mate-in-1 scores exactly `MATE - 1`, and the move played really is mate
     (the position is verified to contain a mate-in-1 via python-chess, not
     asserted from memory);
  2. four consecutive searches with a **deliberately warm TT** return an
     identical score -- this is the asymmetry test, since a store/probe pair
     that were not exact inverses would drift the score on every round trip;
  3. the claimed distance is **truthful**: `MATE - score` is compared against
     playing the line out with the engine moving for BOTH sides (the defender
     playing its own best resistance) and counting plies to checkmate;
  4. sharpest check -- search a position, play two plies, search again reusing
     the same TT, and assert the mate distance shrank by exactly 2.
**All pass, 0 failures.** This is a negative result in the useful sense: a
plausible high-impact bug class is now ruled out with evidence rather than
left as an open worry, and the test stays as a regression guard.

## UPDATE 2026-09-09: correction -- Syzygy does NOT fix R54, or any of the 5
## documented thrown-win draws, and the fast-TC SPRT for it was abandoned

Two mistakes caught back to back, at the user's prompting to reassess.

**Mistake 1: R54 was cited (in this file, above) as motivation for the
Syzygy work. It isn't valid motivation.** At R54's actual repetition point
(ply 94), the position has **11 pieces** (4 pawns each side + R+K vs K) --
nowhere near the 3-man/4-man/KRPvKR coverage shipped. `REVIEW_TASK.md`, which
was available this whole session, says this explicitly: *"Tablebases would
have fixed NONE of these. Piece counts at the five draws were 14, 23, 11, 22,
15 -- none <=5."* That line covers all five documented thrown-win games, R54
included. The Syzygy work should never have been framed around R54; that
framing has been struck from the section below. The tables themselves are
still correct, safe, and worth keeping (genuinely perfect play in the narrow
band of real bare endgames that DO occur, zero cost when they don't apply),
but there is no historical loss in this project's archive that they
concretely fix -- this ships on the same "provably correct, no proven Elo"
basis as `clockcap`, not as a fix for evidence we've cited.

**Mistake 2: the fast-TC SPRT launched for the Syzygy candidate was a weak
test, called out correctly by the user before it produced anything (stopped
at 6 games).** Self-play at 10s+0.1s between two near-identical engines
rarely reaches bare <=5-piece endings, and when it does, the existing
classical search (ACPL ~20-30, abundant relative time at this TC) likely
already handles most of them correctly without TB -- so this test structurally
can't isolate TB's value even given many more games. A real historical-replay
test (the `tools/repetition_replay.py` approach used for repfix/repfix2) was
considered as an alternative, but per Mistake 1 above, none of the five
documented draws are even in TB's piece-count range, so there is no real
failure case on file to replay either. **No further self-play or replay
testing attempted for Syzygy this session** -- it remains an unproven-Elo,
correctness-basis addition, saved in `candidates/syzygy/`, not yet promoted
to a checkpoint. If it's adopted, it should be on the same explicit,
disclosed basis as `clockcap`, not on a claimed test result.

## UPDATE 2026-09-09: init-time scare, fully diagnosed -- NOT a problem, docs were wrong

Mid-session, measured `checkpoints/clockcap`'s init at 60-67s -- alarming
against the "6.8s" figure `CLAUDE.md` had recorded. Chased and ruled out, in
order: thermal throttling (CPU clock confirmed pinned at max 3200MHz, not
reduced), code growth (`checkpoints/v1`, unchanged since the original
measurement, showed the identical ~49-50s), and a genuinely real contributor
that was still not the full story -- a forgotten `reservewiden_sprt_run2`
match had been running the entire time in the background (violates the
project's own "nothing else CPU-heavy during a match" rule; my mistake, lost
track of it while working on Syzygy sourcing), which accounted for ~18s of
the ~67s reading (67s -> 49s once actually stopped and the machine was clean).

**The remaining ~49s vs "6.8s" was not a regression at all: the "6.8s" figure
was simply wrong.** The 25-game CSV (rounds 46-70) already on this machine has
an `init_s` column: 25 real, completed, successfully-played competition games,
**36.6-49.0s, mean 39.9s -- every one finished normally, none failed on
init.** This matches the clean dev-machine measurement almost exactly. There
was no throttling mystery and no code-growth cause to find, because there was
nothing to explain -- reality has been ~37-49s all along, comfortably inside
the 90s cap (worst real case leaves ~41s margin), and the documented figure
was simply never re-verified against real data until now. `CLAUDE.md`
corrected to record the real range instead of the stale number.

**Practical consequence for future work:** real init margin is ~40-50s, not
~83s. This still comfortably covers Syzygy's actual measured cost (see next
section, negligible -- well under 1s), but it means the budget is tighter than
this project's own documentation implied, worth remembering before adding
anything else to init (a polyglot book, more tables).

## UPDATE 2026-09-09: Syzygy tablebases -- sourced, integrated, NOT proven, see correction above

**Correction (see the section above, written after this one but reading
first): R54 is NOT in this coverage (11 pieces at the repetition point) and
`REVIEW_TASK.md` already stated tablebases fix none of the five documented
draws. Struck that motivation from what follows; this stands purely as a
correct, safe, unproven-Elo addition, same basis as `clockcap`.**

Sourced for real this session, not left as an unresolved dependency:
**3-man (complete) + 4-man (complete) + KRPvKR** (the classic rook-and-pawn
ending -- the single most common practical endgame type, independent of any
specific documented failure), from `tablebase.sesse.net` (a genuine, working
static file mirror;
`tablebase.lichess.ovh` turned out to be a live query API, not a file host --
irrelevant anyway since using it at runtime would be a network-during-play
rule violation). **34MB total, verified file-by-file against `python-chess`'s
real API**, not just downloaded and trusted -- every file's `file` signature
confirmed "Syzygy WDL/DTZ tablebase", and probe results checked against known
theory (e.g. a textbook-drawn blocked-KPvK position, correct edge-file KRvK
DTZ). Full list of 292 files on the mirror sized by piece count before
choosing this subset: 3-man ~0MB, 4-man 4.1MB, 5-man 936MB (excluded, both
over budget and mostly not needed) -- the "~30-40MB for 4-man" and "~35MB for
5-man" figures floated earlier this session were both wrong; real numbers
only found by actually fetching and measuring the real directory listing.

**Integration (`engine/agent.py`):** `chess.syzygy` opened in `_warmup()` from
a path resolved relative to `agent.py`'s own location (`os.path.dirname`), not
the working directory, wrapped in try/except so a missing/corrupt `syzygy/`
dir degrades to normal search rather than costing the game. Probed in
`get_move()` right after the forced-move fast path, before the real search,
for any position with `<=5` pieces (the ones outside our 4.1MB+KRPvKR set
raise `KeyError` and fall through to search harmlessly).

**A real, serious sign bug was caught and fixed before it shipped, not by
reading the code but by testing it.** `probe_wdl`/`probe_dtz` report from the
perspective of the side to move IN THE POSITION THEY ARE GIVEN -- after our
own candidate move is pushed, that's the OPPONENT. An earlier draft (pasted by
the user from another source) picked the move that MAXIMIZED this raw value,
which maximizes the opponent's outcome, i.e. picks our WORST move. Shipped as
written, this would have actively handed away every tablebase-covered win --
precisely the failure class tablebases exist to fix. Fixed by negating
(`wdl = -_TB.probe_wdl(...)`), and verified empirically (not just re-derived
on paper) against real downloaded tables: printed every legal move's raw vs
negated WDL in a real KRvK position and confirmed the negated values matched
known theory throughout. DTZ tie-break (prefer smaller signed our-DTZ,
which -- carefully re-derived -- turns out to be the correct comparison in
both the winning and losing case, not two separate branches as most example
code assumes) is documented in the function's own docstring.

Mandatory gates green (`test_perft`, `test_repetition`, `test_history_chain`).
Smoke-tested: KRvK and KRPvK both resolve in ~0.02s via the tablebase instead
of the multi-second search budget; ordinary middlegame positions are
unaffected (TB never engages above 5 pieces). Init-time cost of loading 34MB
across 72 files: negligible, within normal run-to-run noise (~46-47s with TB
vs ~46-49s baseline without, on the same now-clean machine).

**Saved to `candidates/syzygy/` (includes the table files). Not yet SPRT
tested or promoted to a checkpoint** -- a fast-TC self-play match is a weak
test for this specific change (games rarely reach <=5 pieces at 10s+0.1s, so
it mainly tests for regressions/overhead, not the actual endgame benefit,
same test-mismatch caveat as `clockcap`). Next step: run a confirmation SPRT
(mainly a no-regression check) and/or a targeted validation via
`tools/repetition_replay.py`-style replay of the actual thrown-win positions
if PGNs for them become available.

**Opening book: still not sourced.** Confirmed legal by the user (asked
organizers directly). Not yet attempted this session -- same mirror-hunting
approach that worked for Syzygy hasn't been tried for a book file yet.

## UPDATE 2026-09-08, later still: clock-reserve widening for long games

Second, more direct fix for the same clock-starvation defect `clockcap` only
partially addressed. `clockcap`'s spend cap only fires in <=6-piece positions;
the actual worst finishes in the 25-game CSV (1.4s/1.5s/2.0s left after
108/67/59 moves) are about the *whole game* running long, not specifically
about simplified endgames. `RESERVE_MS` was a flat 250ms with no signal for
"this game has already run long" -- `MOVES_TO_GO=28` stayed fixed regardless
of how many moves had already been played.

**Fix:** `agent.py` gained `RESERVE_GROWTH_MS=20` and `RESERVE_CAP_MS=3000` --
the reserve now grows with `board.fullmove_number` (parsed fresh from the FEN
every call, deliberately NOT the internal `_MOVE_NUMBER` counter, which is
never reset on new-game detection and could carry a stale value if the
process is ever reused across games). `_think_time` gained a `move_number`
parameter. This can only ever *reduce* `usable`/`soft`/`hard` relative to the
old flat reserve -- it cannot introduce a new way to overspend, only trade a
little strength in a game that turns out short for real protection in one
that turns out long. Verified analytically (not just by eye): at 30s left,
soft budget drops from 1459ms (move 1) to 1362ms (move 200, cap reached
~move 137); near-flag safety branches engage correctly and *earlier* the
further into a long game the position is.

Mandatory gates green: `test_perft.py` (0 failures), `test_repetition.py`,
`test_history_chain.py`. Smoke-tested (4 FENs, all legal, ~2-3s each at 30s
budget). **Caught and fixed a real methodology mistake before it shipped:**
the first candidate build accidentally carried over the unresolved `ttsize`
change (`TT_BITS=25`) from the previous session's `engine/`, which would have
confounded this test (SPRT-ing "ttsize+reserve" vs "clockcap" and attributing
any effect to the wrong change). Caught by diffing `engine/ca_search.py`
against `checkpoints/clockcap` before launch; `ca_search.py` reverted to
clockcap's `TT_BITS=22`, candidate re-saved and re-validated so only the
reserve change is isolated.

**SPRT running now** vs `checkpoints/clockcap`, logging to
`overnight_logs/reservewiden_sprt_run1.log`. `ttsize` was manually stopped
(862 games, trending +16 Elo +/- 17, LLR +1.20, not flat -- see its own
section below) to free the CPU for this higher-priority fix; not reverted,
just deprioritized. `candidates/ttsize/` kept on disk for a later re-test.

## UPDATE 2026-09-09: reserve-widening run1 REJECTED, recalibrated and re-testing

`overnight_logs/reservewiden_sprt_run1.log` (growth=20ms/move, cap=3000ms):
manually stopped at 152 games, **-50 Elo +/- 45, LLR -0.85, settled/stable, not
a fluke** -- too aggressive. Diagnosis: unlike `clockcap` (only fires in rare
<=6-piece positions), this reduced spend on EVERY move once a game ran long,
including genuinely complex, undecided positions, in a fast-TC self-play test
where the flag-risk it protects against barely exists. Real cost, near-zero
visible benefit at this TC -- the same test-mismatch caveat flagged for
`clockcap` and `ttsize`, but this time large enough to be a clear reject
rather than a wash.

**Recalibrated, not abandoned** -- the underlying defect (proven via the CSV,
independent of this test) is real. `RESERVE_GROWTH_MS` 20->6, `RESERVE_CAP_MS`
3000->1200 (~3-4x gentler): at move 100 this now reserves 850ms extra vs the
old version's 2250ms; cap reached at ~move 158 instead of ~move 137. Mandatory
gates re-verified green. **SPRT running now** vs `checkpoints/clockcap`,
`overnight_logs/reservewiden_sprt_run2.log`.

## UPDATE 2026-09-08, later still: TT resize candidate under SPRT test

Cheapest remaining item from the brief's Appendix A ranking (#4): TT was
`TT_BITS=22` (4.19M entries, 16B/entry = 64MB) against a 2GB budget. Measured
(not guessed, since OOM = an instant loss, the worst possible outcome) the
actual baseline process RSS after full warmup with the old size: **~247MB**
total, i.e. ~183MB is non-TT overhead (numba/llvmlite, python-chess, numpy,
interpreter). Changed to `TT_BITS=25` (32M entries = 512MB) -- an 8x increase,
short of the brief's literal "~1GB" suggestion by design, to keep real margin
under the cap (~695MB worst-case total vs 2GB, ~66% headroom) given this
machine can't fully replicate the competition environment. The array is a
fixed-size `np.zeros(TT_SIZE)`, so 512MB is a hard ceiling, not a typical-case
number -- Windows lazy-commits pages so a brief warmup measured lower, but the
array cannot exceed 512MB regardless of game length.

Mandatory gates green on `engine/`: `test_perft.py` (0 failures),
`test_repetition.py`, `test_history_chain.py`. Saved to `candidates/ttsize/`.

**Manually stopped at 862 games** (not flat -- trending, LLR climbed from
+0.78 at game ~687 to +1.20 at game 862, mean ~52.3%, +16 Elo +/- 17) to free
the CPU for the higher-priority reserve-widening fix below, which addresses a
proven real defect rather than a nice-to-have. Same status as item5's first
run: promising, unresolved, not adopted. `candidates/ttsize/` kept on disk;
`engine/` moved on to the next candidate rather than being reverted to
`checkpoints/clockcap`, since the next candidate is built on top of clockcap
anyway. Worth revisiting/pooling with a second run later if there's budget.

## UPDATE 2026-09-08, later same session: clock-starvation fix, ADOPTED on correctness grounds

User supplied the actual review brief (`REVIEW_TASK.md`, previously missing from
this directory) and a 25-game CSV export (`aichessathon-games.csv`, rounds
46-70) with real per-game clock telemetry, and confirmed **the live binary is
`repfix2`** (resolving the Phase 0 question `REVIEW_FINDINGS.md` had flagged
blocking). Two claims from the brief were checked directly against that CSV
before trusting them, not taken on faith:

- **"~10s compile-on-clock spike"** -- checked against the actual `_think_time`
  formula: the hard-cap ceiling at game start computes to exactly **11.69s**,
  matching the observed 8.4-11.8s "slowest move" range almost exactly. This is
  the existing time budget doing what it's designed to do, not a JIT stall.
  **Not adopted as a diagnosis** -- no fix built for it.
- **"No clock reserve, long games starve"** -- independently recomputed from
  the CSV: **corr(moves, clock_left_s) = -0.778** (brief said -0.78, confirmed).
  Worst finishes: **1.4s left after 108 moves, 1.5s after 67, 2.0s after 59** --
  real near-flag risk (flag = instant loss, the single worst outcome possible).
  **Confirmed real, and fixed.**

**Fix:** `engine/agent.py` `_think_time()` gained a spend cap for positions
with `<=6` total pieces (`SIMPLE_ENDGAME_PIECES`) -- e.g. KPvK, KRvK, KRPvK --
capping soft/hard budget to roughly 1.0x/1.8x the increment instead of the
full per-move formula. These positions already search to enormous depth for
free (branching collapses with few pieces), so multi-second spend there buys
negligible strength while starving the reserve later, sharper moves in the
same long game need. `_think_time` gained an `n_pieces` parameter; call site
in `get_move` passes `len(board.piece_map())`. Smoke-tested directly: a KPvK
and a KRvK position both now return in ~0.53s (was previously eligible for the
full multi-second budget); ordinary middlegame positions are unaffected,
confirmed still using the full ~11.7s hard cap on the same smoke test.

Mandatory gates green on `engine/`: `test_perft.py` (0 failures),
`test_repetition.py`, `test_history_chain.py`.

**SPRT vs `checkpoints/item5`** (candidate = item5 + this cap, reference =
item5 alone), 10s+0.1s, 3 workers: **879 games, +253=382-244 (50.5%), +4 Elo
+/- 17, LLR -0.05 -- flat throughout, manually stopped per the 500-flat rule**
(flat from roughly game 200 onward). The final line is `*** ANOMALY *** crash:
agent died ... caused by agent@engine` -- this is the process kill itself
(`arena.py`'s message for a vanished subprocess when the match is stopped
externally), not a real fault, same documented artifact as the repfix2 entry's
crash anomaly. No other anomalies across 879 games.

**Why flat is the expected, uninformative result here, not evidence against
the fix:** the change targets clock behaviour in long games with few pieces on
the board -- a rare tail event (3 of 25 real games came within ~2s of
flagging). Fast self-play (10s+0.1s, games typically 20-60 plies) essentially
never reaches the scenario this protects against, so a null Elo result here
is close to uninformative either way, not a sign the fix does nothing.

**ADOPTED on correctness/risk-reduction grounds, explicitly not on the Elo
number** -- same basis as `repfix2`: the defect (real near-flag finishes) was
independently verified against real competition data, not inferred from
self-play. `engine/` snapshotted to `checkpoints/clockcap/`.
`checkpoints/REFERENCE.txt`: `item5` -> `clockcap`. `build/` updated to match
and `submission_clockcap.zip` built and validated (0 diff vs `build/`, same
procedure as `submission_item5.zip`). **Not uploaded** -- left to the user, as
before.

## UPDATE 2026-09-08 (this session, resuming cold): item 5 formally ACCEPTED via pooling

The run described in the section below (`item5_on_repfix2_sprt_run2.log`) was
**found dead on resuming this session** — no `python.exe` process for
`gauntlet.py` was alive, and the log's last line (game 1583, `[CONTINUE]`,
LLR +2.52) is timestamped 15:06, over two hours before this check. No
`status=` line, no FINAL summary, no error/traceback/crash line anywhere in
the log — it did not stop by design or by any code path in `gauntlet.py`;
the process was killed externally, most likely because it was launched via a
background shell tied to the previous session, which was then torn down.
**Disclosed explicitly as a methodology deviation**, same spirit as the
manual-stop disclosures elsewhere in this file.

This does not invalidate the 1583 games it completed before dying — SPRT's
trinomial (W/D/L) counts are order-independent sums over iid game outcomes,
so a match that stops mid-flight for a reason unrelated to the score (a
killed process, not a score-dependent decision) contributes valid data, the
same as a manually-stopped-for-being-flat match does elsewhere in this file.

**Pooled with the run above it** (`#5 LMR shaping, SPRT vs repfix2`, 853
games), exactly as pre-registered in that row's own launch rationale ("the
two runs pool... roughly what it takes to separate +14 from 0"). Both runs
are the identical pairing (candidate = `checkpoints/repfix2` + item 5 LMR
change, vs reference = `checkpoints/repfix2`) at the same time control:

| run | games | W | D | L | score | LLR (elo0=0,elo1=8) |
|---|---|---|---|---|---|---|
| run1 (prior session) | 853 | 263 | 371 | 219 | 52.6% | +1.40 |
| run2 (died at game 1583) | 1583 | 488 | 687 | 408 | 52.5% | +2.52 |
| **pooled** | **2436** | **751** | **1058** | **627** | **52.5%** | **+3.92** |

Pooled LLR **+3.92 crosses the formal ACCEPT bound (+3.664)**. Elo estimate
(same `elo_with_ci` used throughout this file): **+18 ± 10**. Verified with
`tests/sprt.py`/`tests/gauntlet.py`'s own functions, not hand-computed.

Pre-promotion checks, all green on `engine/` (untouched since the run died —
still exactly `checkpoints/repfix2` + the item 5 diff, confirmed by diff):
`tests/test_perft.py` (0 failures), `tests/test_repetition.py engine`,
`tests/test_history_chain.py engine`, `tests/test_sprt.py`.

**ACCEPTED.** `engine/` snapshotted to `checkpoints/item5/` (byte-identical,
confirmed with `diff -rq`). `checkpoints/REFERENCE.txt`: `repfix2` -> `item5`.

**`build/` NOT touched** — still v1, per the standing rule ("never touch
`build/` until a change is proven" + the not-yet-done Phase 5 net-effect
check mentioned in `REVIEW_FINDINGS.md`). No new submission zip built yet.
`REVIEW_FINDINGS.md`'s own top-priority, still-open, BLOCKING item — which
zip is actually live on the aichessathon.com dashboard — is unresolved and
needs the user (dashboard access this machine doesn't have) before any
submission decision is made on top of this.

## UNATTENDED RUN IN PROGRESS (started 2026-09-08) — SUPERSEDED, see UPDATE above

`overnight_logs/item5_on_repfix2_sprt_run2.log` — item 5 (LMR shaping) vs
`checkpoints/repfix2`, SPRT elo0=0 elo1=8, 10s+0.1s, 3 workers,
**`--max-games 3000`** (raised from the usual 1500 so it does not stop early).
`engine/` holds the candidate = `checkpoints/repfix2` + the item 5 LMR change
only (diff verified: the 3-way `mscores[ply][i]` check replacing
`history > 4000`; `agent.py` untouched). All gates green before launch:
perft, test_repetition, test_history_chain, smoke.

**Why:** item 5 measured **+14 ±11 over 881 games vs v1** and **+18 ±18 over
853 games vs repfix2** — a consistent small positive that neither sample could
resolve. Conditions here are identical to run 1 vs repfix2, so the two runs
**pool**: combined they should reach ~1500-2500 games and a CI near ±11-15,
which is roughly what it takes to separate +14 from 0.

**How to read the result:**
- `status=ACCEPT` → adopt: snapshot `engine/` to `checkpoints/item5`, point
  `REFERENCE.txt` at it, rebuild the zip.
- `status=REJECT` → revert `engine/` from `checkpoints/repfix2/`.
- Still `CONTINUE`/flat after pooling → item 5 is a real but sub-10-Elo effect
  the harness cannot resolve at this H1; **do not adopt** (METHODOLOGY.md), and
  consider re-running with a wider `--elo1` instead of more games.

**To stop it:** kill the `python.exe` whose command line contains `gauntlet`.
**Nothing else CPU-heavy should run while this is live** (rule 4). `engine/`
currently holds the candidate, NOT the reference — restore with
`cp checkpoints/repfix2/*.py engine/` when done.

`build/` is untouched (still v1). The shippable build remains
`submission_repfix2.zip`.

## Methodology update: SPRT replaces fixed-N matches from item 2 onward

Fixed-200-game batches are what burned 400 games on item 1 without a clean
answer (a real ~10-20 Elo effect and pure noise look similar at that N). From
item 2 onward, matches use a sequential probability ratio test (SPRT) instead:
`tests/sprt.py` + a `--sprt` flag added to `tests/gauntlet.py`, elo0=0 (H0: no
change) vs elo1=8 (H1: a real improvement), alpha=beta=0.025, LLR bounds
+-3.664, hard cap 1500 games -> INCONCLUSIVE. Each match is now a candidate
engine (`engine/`) vs the current accepted reference (a `checkpoints/<x>/`
snapshot, tracked by `checkpoints/REFERENCE.txt`), not vs Stockfish directly
-- SPRT's elo0=0 null hypothesis only means "no difference" when both sides
of the record are the two things actually being compared. `tests/test_sprt.py`
validates the formula itself (bounds, symmetry under symmetric hypotheses,
scaling, monotonicity) before it is trusted for a real match -- see that
file's docstring for why replaying item 1's absolute vs-Stockfish numbers
through the LLR math is not a valid check (it produces a large positive LLR
even though item 1 was later shown, correctly, not to be an improvement).

## Results

| change | games | score% | Elo +/- CI | adopted? | notes |
|---|---|---|---|---|---|
| baseline (v1, unmodified engine/) vs SF@2500 | 200 | 60.0% (+84=72-44) | +70 +/- 39 | n/a (reference) | Today's reference point before any change. |
| #1 easy-move early stop, batch 1 | 200 | 63.2% (+79=95-26) | +94 +/- 35 | — | Promising in isolation but CI overlaps baseline heavily (z~0.9 on the score difference, not significant). |
| #1 easy-move early stop, batch 2 | 200 | 60.8% (+79=85-36) | +76 +/- 37 | — | Regressed back toward baseline, exactly the noise pattern METHODOLOGY.md warns about. |
| #1 easy-move early stop, pooled | 400 | 62.0% (+158=180-62) | +85 +/- 25 | **REJECTED (inconclusive)** | Two-sample z-test of pooled 400 games vs the 200-game baseline: diff = 0.02 score, SE_diff ~= 0.0325, z ~= 0.6. Nowhere near the ~1.96 needed for significance. Per METHODOLOGY.md, "never adopt a change whose measured effect is inside its own error bar" -- reverted. |
| #2 continuation history, SPRT vs v1 | 639 (manually stopped) | 49.9% (+74=490-75) | -1 +/- 13 | **REJECTED** | 1-ply/2-ply continuation history tables (`cont1`/`cont2`) added to move ordering. Smoke test and `tests/test_perft.py` (0 failures) passed before launch. SPRT vs `checkpoints/v1` (elo0=0/elo1=8, alpha=beta=0.025, 10s+0.1s, 3 workers): LLR drifted to -0.7..-1.2 and held there from ~game 200 through game 639 (~96 min), never approaching either +-3.664 bound. Score stayed pinned at essentially exactly 50% the whole time. **Manually stopped at 639/1500 games rather than run to the hard cap** -- a deviation from the pre-registered SPRT stopping rule, disclosed here explicitly: a near-zero true effect is the slowest case for SPRT to formally resolve (the LLR drift rate is proportional to how far the mean sits from the H0/H1 midpoint, which is where this sat for hundreds of games), and continuing to the full cap would have spent ~70+ more minutes to distinguish "no effect" from "very slightly negative," neither of which clears TASK3.md's bar for adoption. The 95%-CI point estimate at the stopping point (-1 +/- 13 Elo vs the v1 reference) is already decisively inside its own error bar, satisfying METHODOLOGY.md's "never adopt a change whose measured effect is inside its own error bar" rule on its own terms, independent of the formal LLR verdict. `engine/` reverted to `checkpoints/v1/` and reverified byte-identical; `candidates/item2/` kept on disk, not deleted. |
| #3 history gravity, SPRT vs v1 | 1017 (manually stopped) | 50.3% (+125=773-119) | +2 +/- 10 | **REJECTED** | `gravity_update()` (`h + bonus - h*abs(bonus)//MAX`) replaced the additive bonus/malus+clamp on the `history` table at beta cutoffs; per-root `//=4` decay untouched. Smoke test + `tests/test_perft.py` (0 failures) passed. SPRT vs `checkpoints/v1`: LLR oscillated in the -0.3..-0.7 band from ~game 350 through game 1017 (~155 min), never trending toward either bound -- the same flat-null signature as item 2. Adopted a standing rule this run: **cut any SPRT match that is flat for 500+ games rather than let it grind toward the 1500 cap** (explicit user instruction), since a near-zero effect is SPRT's slowest case to formally resolve and the extra games buy no decision-relevant information. One anomaly (`ANOMALIES: 1` at game 1017) was seen but its detail was lost -- the match was killed before reaching the FINAL summary that prints anomaly detail. Fixed for future runs: `tests/gauntlet.py`'s worker now prints each anomaly's full detail (reason, side, result, and which named engine caused it) live, the instant it happens, not just a running count. Given the ~1/1656-game base rate across items 2+3 combined and that item 3 is being discarded regardless, this wasn't chased further, but it's an open item to watch for recurrence. `engine/` reverted to `checkpoints/v1/` and reverified byte-identical; `candidates/item3/` kept on disk. |
| #4 improving flag, SPRT vs v1 | 376 (formal SPRT decision) | 44.7% (+33=270-73) | -37 +/- 18 | **REJECTED** | New `static_hist` scratch array (`agent.py`) tracks static eval vs 2 plies ago (same side to move); `improving` flag widens reverse-futility/futility margins and adds `r -= 1` to LMR whenever not improving. Smoke test + `tests/test_perft.py` (0 failures) passed. SPRT vs `checkpoints/v1` **crossed the formal REJECT bound on its own** (LLR -3.77 at game 372, no manual stop needed) -- unlike items 2/3, this was not a flat wash, it was a clear, sizeable regression. Diagnosed with `tools/measure_nps.py` (new tool, built this session): item4 ran at 1.095 Mnps vs v1's 1.121 Mnps -- only ~2% slower, ruling out a node-rate collapse as the cause. The regression is therefore most likely a search-quality effect, not a speed one: `improving` goes false on any minor eval dip between a side's own turns, and stacking an extra full-ply LMR reduction cut on top of the existing PV/history-based reductions in that (apparently common) case likely diluted search effort too broadly rather than sharpening it where it mattered. Not conclusively root-caused to a single line -- this is a plausible, structurally-grounded explanation, not a confirmed bug fix. `engine/` reverted to `checkpoints/v1/` and reverified byte-identical (twice -- once after the SPRT match, once after a follow-up nps-diagnostic reload); `candidates/item4/` kept on disk. |
| repfix2: complete the position history | 495 (manually stopped at the 500 flat rule) | 52.0% (+140=235-120) | +14 +/- 22 | **ADOPTED on correctness grounds -- Elo inconclusive** | Follow-on to `repfix`, which only made the *existing* history usable. `agent.py` recorded only positions it was handed (our turn) and wrote placeholder zeros for the opponent-to-move positions between them, so repetitions of those positions still could not be matched against real game history -- roughly half of all positions. Nothing is genuinely unknown: every position is either one we were shown or one reachable by applying our own move, so `_SEEN` (+ placeholders) is replaced by `_HIST`, a true ply-by-ply chain, and `_INFO[0] = len(_HIST)`. Also fixes a second hole: the forced-move fast path (`len(legal) == 1`) previously returned without recording anything. **A new test, `tests/test_history_chain.py`, drives the real agent through a scripted game and checks every recorded entry against python-chess ply for ply:** the current reference records only 4 of 8 plies and 0 of 2 forced-move plies (**fails**), repfix2 records all 8 and both (**passes**). That test also caught a genuine bug during development: python-chess sets `ep_square` after any double pawn push, but `fen()` emits the field only when the capture is legal, so hashing a pushed board disagreed with hashing the same position parsed from its FEN. Fixed via `_hash_after()`, which round-trips through the FEN so every entry uses the referee's own convention. Perft 0 failures, smoke test and `tests/test_repetition.py` green. **SPRT was vs `checkpoints/repfix`, not v1**, so it measures only the additional gain. Result: 495 games, +140 =235 -120, +14 +/- 22 Elo, LLR meandering around +0.5-0.7 without trending; stopped per the 500-game flat rule. **Mechanically it clearly works -- threefold draws fell to 41% from 62.6% in the repfix-vs-v1 match, total draws to 47%.** But the Elo case is NOT proven: the CI includes zero. Note the extra decisiveness cuts both ways -- wins rose modestly (125 -> 140 across the two matches) while losses rose more (63 -> 120), consistent with the engine declining draws on advantages smaller than its own evaluation error. **Adopted anyway, on the same independent-correctness basis as `repfix` itself, NOT on the Elo number**: `tests/test_history_chain.py` shows the previous reference recorded only 4 of 8 plies and 0 of 2 forced-move plies, i.e. it was objectively incomplete, and building further draw-related work on a knowingly half-blind detector would be unsound. This is an explicit, flagged deviation from "never adopt a change inside its own error bar" -- justified because the justification is a proven defect, not the Elo measurement. A follow-up crash anomaly in this run (`crash:agent died ... caused by agent@engine`) was traced to the process kill from stopping the match, not a real fault: `worker.py` catches all exceptions and reports them as `crash:<traceback>`, whereas `agent died` is `arena.py`'s message for a vanished subprocess; a subsequent 24-game match run to natural completion reported "no crashes, illegal moves, or flags". Promoted to `checkpoints/repfix2/`; `REFERENCE.txt` -> `repfix2`. |
| #5 LMR shaping, re-test SPRT vs repfix2 | 853 (manually stopped) | 52.6% (+263=371-219) | +18 +/- 18 | **INCONCLUSIVE -- not adopted** | Item 5 re-measured against the current reference after `repfix`/`repfix2` changed the baseline. Reproduced the same small positive it showed against v1: **+14 to +18 Elo in both independent matchups** (881 games vs v1, 853 games vs repfix2), never reaching the +3.664 accept bound in either (LLR flat around +0.7-1.4). This looks like a real effect of roughly 10-18 Elo, i.e. below the 8-Elo threshold the test is powered for, and resolving it properly would need ~2000+ games. Per METHODOLOGY.md's "never adopt a change whose measured effect is inside its own error bar", **not adopted** -- the CI still touches zero. Stopped early to free the CPU for a Stockfish depth-20 ACPL analysis run in another session (rule 4: no overlapping CPU-heavy work during/around a timed match). `engine/` restored to `checkpoints/repfix2/`; `candidates/item5/` and `candidates/repfix_item5/` kept on disk. **This is the best remaining candidate if anyone wants to spend the games on it.** |
| contempt (CONTEMPT=20cp), SPRT vs repfix2 | 530 (manually stopped at the 500 flat rule) | 47.1% (+132=235-163) | -20 +/- 22 | **REJECTED at 20cp** | Draws scored as `draw_score(ply)` = -20cp for us / +20cp for the opponent (sign flipped by ply parity, since search_root always starts on our move -- a fixed value would make a draw read as bad for both sides at once, which is incoherent). Applied to repetition, 50-move and stalemate returns. Motivation: with draws at a flat 0 the engine declines a repetition the moment its eval reads +1cp, far inside its own evaluation error. Perft, `tests/test_repetition.py`, `tests/test_history_chain.py` and smoke all green. **Mechanically very effective and directionally wrong**: threefold draws collapsed to 21% (from 41% for repfix2, 62.6% for repfix), but the score went to 132W/163L. Reading: the positions where repetitions arise are ones our eval is not reliable enough to judge -- declining them walks into losses more often than wins, so 20cp is far too aggressive. **Caveat on the measurement, stated so it is not over-read:** self-play is the weakest possible test for contempt, because its whole value is converting draws into wins against *weaker* opposition, and in self-play the opponent is a near-identical twin. A smaller value (~8-10cp) aiming for self-play-neutral could still be positive in the live field and is worth a future run; 20cp is not. `engine/` reverted to `checkpoints/repfix2/`; `candidates/contempt/` kept on disk. |
| #5 LMR shaping, pooled run1+run2 vs repfix2 | 2436 (853+1583, run2 died mid-flight, pooled per plan) | 52.5% (+751=1058-627) | +18 +/- 10 | **ACCEPTED (formal, LLR +3.92)** -- new reference | See "UPDATE 2026-09-08" section above for full detail, including the disclosed process-death deviation. Promoted to `checkpoints/item5/`; `REFERENCE.txt` -> `item5`. `build/` untouched. |
| #5 LMR shaping, SPRT vs v1 | 881 (manually stopped, NOT a verdict) | 52.0% (+126=664-91) | +14 +/- 11 | **INCONCLUSIVE -- re-test required** | 3-way mutually-exclusive `mscores[ply][i]` LMR check (killers/counter-moves reduce less, bad-history quiets reduce more, good history reduces less) replacing the single `history > 4000` rule. Smoke test + perft (0 failures) passed. Unlike items 2-4 this showed a real positive trend: LLR climbed to +2.2 by game ~490, sagged to +1.8 by ~840, recovered to +2.44 by game 881 -- genuinely trending toward the +3.664 accept bound but never reaching it. **Manually stopped mid-flight, and NOT because it was flat**: the `repfix` correctness bug (see next row) was discovered during this run, and since item 5 was being measured against v1 -- which stops being the reference if `repfix` is adopted -- item 5 would need re-measuring against the new baseline anyway. This row is therefore not a keep/reject verdict, it is an unfinished measurement. **Item 5 is the most promising of items 2-5 and should be re-tested against whatever `checkpoints/REFERENCE.txt` names once `repfix` resolves.** `candidates/item5/` kept on disk. |
| repfix: repetition detection was dead | 522 (formal SPRT decision) | 55.9% (+125=334-63) | **+41 +/- 18** | **ACCEPTED** -- new reference | **Correctness bug in the currently-submitted v1 engine, found by investigating live competition results, not by a planned experiment.** Live rated rounds 46-53 split perfectly by colour: all four games as White drawn by threefold repetition (rounds 46, 48, 52, 53), all four as Black won by checkmate (47, 49, 50, 51). Root cause in `is_repetition()`: agent.py stores history one index per ply (real key at even indices, placeholder 0 at odd), and `info[0]` puts the current position at index `rep_len-1`, so same-side-to-move ancestors are at `rep_len-3, -5, ...`. The scan started at `rep_len-2` and stepped by 2, walking the **opposite-parity** chain -- and since `compute_hash()` xors `ZOBRIST_SIDE` for black, those entries can never equal the current key, with the rest of that chain being the placeholder zeros. Net effect: **`is_repetition()` could never return True; the search was completely blind to repetition draws**, so it never scored a repeating line as 0 and would shuffle into a threefold without seeing it (exactly the `Rfe1/Reb1/Re1/Reb1/Re1` pattern in the round-46 log). Fix is one line, `i = rep_len - 2` -> `i = rep_len - 3`. Proven in the real compiled numba function by a new regression test, `tests/test_repetition.py`: v1 **fails** it (blind), the fix **passes** all three cases (detects a genuine repetition, no false positive, still respects the halfmove horizon). Smoke test + perft (0 failures) passed. **SPRT vs `checkpoints/v1` crossed the ACCEPT bound at game 518 (LLR +3.725), final 522 games: +125 =334 -63, 55.9%, +41 +/- 18 Elo. No crashes, illegal moves or flags.** Termination breakdown (from the new instrumentation): `draw:threefold` 62.6%, `mate` 36.0%, `draw:material` 1.3%. Self-play draw rate fell from the 75.4% item2-5 baseline to 62.6% even though the *opponent* in this match (v1) is still repetition-blind and keeps shuffling into threefolds. **This is the first formally accepted change of the session, and by far the largest** (best of items 2-5 was item 5's unproven +14). Promoted to `checkpoints/repfix/`; `checkpoints/REFERENCE.txt` -> `repfix`. Note this bug was reviewed by eye earlier in this session and wrongly declared "not a bug" -- reading the code was not enough, only tracing the indices exposed it. **The fix is likely PARTIAL:** `agent.py` still writes placeholder zeros for opponent-to-move positions, so repetitions of those positions still cannot be matched against real game history -- see the `repfix2` row. |

## What changed and what didn't

**Implemented and tested:** Item 1 from TASK3.md, "early stop on a stable PV" —
added a `stable_iters` counter in `search_root` (engine/ca_search.py) that
breaks the iterative-deepening loop once the best move has held for 4+
iterations past depth 4 with score movement <=30cp (gated at depth>=8). Tested
over 400 total games against a fixed SF@2500 opponent. **Rejected** — the
pooled effect did not clear its error bar, and the point estimate got weaker,
not stronger, with more games. The code has been reverted; `engine/ca_search.py`
is byte-identical to `build/ca_search.py` again (verified with `diff`).

**Current per-item status** (priority order from TASK3.md):
- Item 2 (continuation history): implemented, smoke-tested, perft-clean,
  measured via SPRT against v1 (639 games, manually stopped -- see Results
  table for the full rationale). **Rejected** -- no measurable effect vs v1.
  `engine/` reverted to `checkpoints/v1/`; draft kept in `candidates/item2/`.
  `checkpoints/REFERENCE.txt` still points at `v1`.
- Item 3 (history gravity): implemented, smoke-tested, perft-clean, measured
  via SPRT against v1 (1017 games, manually stopped -- see Results table).
  **Rejected** -- no measurable effect vs v1. `engine/` reverted to
  `checkpoints/v1/`; draft kept in `candidates/item3/`.
- Item 4 (improving flag): implemented, smoke-tested, perft-clean, measured
  via SPRT against v1 (376 games, formal REJECT -- see Results table).
  **Rejected** -- a real, sizeable regression (-37 Elo), not a wash; nps
  comparison ruled out a speed cause. `engine/` reverted to
  `checkpoints/v1/`; draft kept in `candidates/item4/`.
- Item 5 (better LMR shaping): **ACCEPTED 2026-09-08**, pooled 2436 games vs
  `repfix2` (+18 +/- 10 Elo, formal SPRT accept, LLR +3.92). See the "UPDATE
  2026-09-08" section above. `checkpoints/REFERENCE.txt` -> `item5`.
  `engine/` == `checkpoints/item5`. `build/` still untouched (v1).
- **repfix (repetition detection):** highest-priority item -- a real
  correctness bug in the live submitted engine, one-line fix, proven by
  `tests/test_repetition.py` (v1 fails, fix passes). **SPRT in progress**;
  see `overnight_logs/repfix_sprt_run1.log`.
- Item 6 (singular extensions): explicitly out of scope for unattended work
  -- changes core loop semantics and needs a manually reviewed diff.
- **CORRECTION to an earlier entry in this file.** An earlier version of this
  section stated that `is_repetition()` "correctly scores a repeatable
  position as exactly 0 inside the search (confirmed by reading the code --
  this is NOT a bug, the search does know repetition draws)." **That was
  wrong.** Reading the code was not sufficient; tracing the indices showed
  the detection never fires at all. See the `repfix` row in the Results
  table. The contempt idea below is still a legitimate future item, but it
  was proposed on a false premise -- the actual cause of the observed
  repetition draws was the bug, not a missing draw-aversion term.
- **Backlog item (not in TASK3.md's original 6): contempt / draw
  aversion.** With no draw-aversion term anywhere in `ca_eval.py`, once no
  alternative move scores strictly above 0, a draw is tied-for-best and the
  search has no preference against it. Proposed
  fix: bias the draw-return value away from exactly 0 (positive when the
  engine's own root side is ahead materially, so it keeps pressing; neutral
  or negative when behind, so it's still willing to take a genuine draw) --
  standard "contempt". **Deprioritised** until the `repfix` result is known:
  with repetition detection actually working, the engine may already stop
  drifting into these draws, and contempt on top of a working detector is a
  much smaller, more speculative gain. Flagged as **moderate risk, not for
  blind unattended implementation**, same caution class as item 6: it changes core draw
  semantics (repetition/50-move return value used throughout `negamax`), and
  a miscalibrated or wrong-signed version could make the engine avoid
  legitimate defensive draws when actually losing, costing more games than
  it wins. Queued strictly behind items 3-5, and its design (in particular,
  how "ahead/behind" is judged, and at which node the sign flips relative to
  root) should be reviewed before it's coded, not authored blind the way
  item 2/3 were.

Items 4-5 (and then contempt) are queued strictly sequentially behind item
3's result.

## Submission state

`build/` is still byte-identical to the originally submitted, validated v1
and stays that way until the mandatory Phase 5 net-effect check (v1 vs the
fully-modified engine, both fast SPRT and a slow 60s+0.5s confirmation) has
passed -- this is the only condition under which `build/` will be touched.
`engine/` now holds `checkpoints/item5` (repfix + repfix2 + item5 LMR
shaping, formally accepted 2026-09-08), so `engine/` and `build/` are
*intentionally* not identical -- `engine/` has moved three accepted steps
past what `build/` still ships. `checkpoints/REFERENCE.txt` = `item5`.
**Open, blocking, needs the user:** `REVIEW_FINDINGS.md` Phase 0 flags that
which zip is actually live on the aichessathon.com dashboard cannot be
determined from this machine, and two of the four built zips are still v1 --
this must be resolved before any new submission zip is uploaded (a fresh zip
was built regardless, see below, since the user asked for it directly; this
does not resolve the dashboard question, it only produces the artifact).

**2026-09-08, later same session:** at the user's explicit request, `build/`
was updated to `checkpoints/item5` (copied over the previous v1 contents,
confirmed identical to `checkpoints/item5` with `diff -rq`) and a smoke test
run directly against `build/agent.get_move()` on 3 FENs (startpos, an
Italian-ish middlegame position, a K+P endgame) -- all 3 returned legal moves
in ~1-1.3s cold. `submission_item5.zip` built from `build/` and validated by
extracting to a scratch dir and diffing against `build/`: 0 differences.
**Not yet uploaded** -- that is still gated on the same open dashboard
question above (a wrong upload wastes one of 10 daily submission slots), left
to the user.

A fresh `submission_new.zip` was built directly from `build/` (agent.py at the
root, alongside ca_eval.py / ca_movegen.py / ca_position.py / ca_search.py /
ca_tables.py) and validated by extracting it to a clean directory and diffing
against `build/` -- 0 differences. It is content-identical to the currently
submitted v1; the only reason to swap it in is if the existing submission.zip
is suspected stale, since no gameplay-affecting change was made.

## Explicitly not verified

- No absolute (FIDE/CCRL-calibrated) Elo number exists or can exist on this
  machine -- see NO_STOCKFISH.md.
- Items 2-6 from TASK3.md's priority list: not implemented, not measured.
- Whether a *shorter* time control (e.g. 5s+0.05s) would materially change
  the noise/throughput trade-off for future iteration -- discussed with Theo
  but not tried.

## AUTOSAVE 2026-09-10 01:1x -- unattended stop, PC shut down

Book build and harvest were stopped early at the user's request. Nothing was
lost: `tools/book_cache.jsonl` flushes per entry, so the cache was intact at
the moment of the kill and `engine/ca_book.py` was regenerated from it.

**Book as saved:** 6,888 entries, **0 illegal** (every stored move verified
legal against python-chess at generation time), **308/308 pool start positions
covered**, 532 KB. Depths 1 and 2 COMPLETE, depth 3 partial (~2,180 of 4,975).
30s of our own engine per position (~18M nodes, ~2.7x what the live search
manages in a real game).

**Harvest as saved:** 6,740 game PGNs in `tools/pgns_public/`, position pool
fully enumerated at 308 (0 singletons). Resumable -- `tools/fetch_games.py`
skips already-fetched games.

### State at shutdown
- `checkpoints/REFERENCE.txt` = `openingcap`
- `build/` == `checkpoints/openingcap`, and `submission_openingcap.zip`
  (31.9 MB) was built from it and validated end-to-end: 0 diff vs `build/`,
  agent.py at ROOT, tablebase loads from the extracted copy, 3/3 smoke
  positions legal, KPvK returned in 0.00s. **Ready to upload as v6.**
  The book is NOT in that zip.
- `engine/` = openingcap + book lookup + the 6,888-entry `ca_book.py`.
  So `engine/` != `build/` intentionally.

### NEXT STEPS, in priority order
1. **The book is UNTESTED.** SPRT `engine/` vs `checkpoints/openingcap` before
   adopting or shipping it. Estimated +10 to +30 Elo but that is a guess. A
   book makes our opening deterministic, so a subtly bad entry is replayed
   against every opponent reaching that position -- a risk we do not currently
   carry. Gate first with `tests/test_book.py`, then perft / repetition /
   history-chain / tt-mate since `agent.py` changed.
2. **Finish the harvest** (~6,700 of ~17,900 done). Coverage is DATA-limited,
   not plateaued: held-out hit rate at move 2 rose 45% -> 51% between 1,800 and
   2,614 training games and was still climbing ~1.6% per 200 games. The full
   set plausibly reaches move 2 ~70%, move 3 ~40%.
3. **Rebuild the book against the fuller reply model** once harvested. The
   target list grows with more games; the cache carries over (keyed by
   position).
4. **Do NOT build depth 4-6.** Measured: ~12.6h of compute for ~1s of clock,
   because held-out hit rates collapse to 10%/4%/2%. Better use of the same
   time: re-search the 308 start positions at 300s (2.1h) -- they are hit 87%
   of the time and would gain ~2.5 plies.
5. Possible free speedup: the Ryzen 7 2700 is natively 8c/16t but Windows
   reports **6c/12t**, so two cores look disabled in BIOS. Re-enabling would be
   ~+33% compute.

## UPDATE 2026-09-10 23:0x -- opening book SHIPPED without a proven Elo result

**Book SPRT: run 1 was structurally void.** Launched against `tests/openings_gen.fen`
(the 400-position general-purpose test set) -- zero overlap with the book's
24,319 keys, confirmed directly. The book never fired once in that run; both
engines played identical openings the whole time. Caught by the user asking
"do the test games run from set starting positions?" after ~50 minutes and
~500 games had already been logged as if meaningful. Stopped immediately.
Corrected by building `tests/openings_pool.fen` from the real 308-position
competition pool (100% overlap with book keys by construction) and relaunching.
Verified independently before trusting the relaunch: 20/20 sampled pool
positions returned in ~1ms (vs the normal ~6-9s search), confirming the book
was actually engaging this time.

**Run 2 (the real test), stopped by explicit user decision at 1135 games:**
+239 =669 -227, mean 0.505, **+4 Elo +/- 13**, LLR +0.11. Trajectory across the
run: +89(n=4) -> -7(n=252) -> +1(n=501) -> +7(n=806) -> +4(n=1135) --
oscillating around zero with a shrinking CI, never trending toward either the
+3.664 accept or -3.664 reject bound. This is the signature of a true effect
close to zero, distinct from item 5's pattern (a persistent small positive
that eventually confirmed at +18 over 2436 games). 4 anomalies total (0.35%),
split across both engines -- consistent with the documented 6-worker
contention background, not a book-specific defect.

**This directly contradicts the pre-test estimate of +10 to +30 Elo** given
earlier this session. The claim that a book move is "strictly better" than
live search was already walked back mid-session (true only at ~30s/position
and only relative to a contended-CPU 10s baseline, not a clean claim); this
SPRT is the further, harder correction: even granting the quality claim, the
measured net effect across real games is flat.

**Shipped anyway, at the user's explicit, informed decision** -- not on a
correctness argument (the repfix/repfix2/clockcap/syzygy basis) and not on a
proven Elo number. The user was shown the live SPRT trend and the project's
own history of "theoretically should help" claims failing (item 4 -37, MOVES_TO_GO
-3, contempt -20) before deciding. Recorded here in full so a future session
does not mistake this for a tested, accepted change: **the book has NOT cleared
this project's own adoption bar.** If revisited, the honest next step is either
resuming this exact SPRT (pooling with the 1135 games already played, matching
how item 5 was eventually resolved) or accepting the flat result as final.

**State:** `checkpoints/book/` created from `engine/` (openingcap + the
24,319-entry book). `REFERENCE.txt` -> `book`. `build/` synced and
`submission_book.zip` built (32.1 MB, over the 30MB remote-send limit,
desktop-app-only) -- validated end-to-end: 0 diff extracted vs `build/`, book
(24,319 entries) and tablebase both load from the extracted copy, 3/3 smoke
positions legal. **User has this file and may upload it.**

Gates run before shipping, all green: `tests/test_book.py` (0 illegal, 0
malformed, 0 unreachable -- see note below), perft, repetition, history-chain,
tt-mate.

**Bug fixed in `tests/test_book.py` during this gate run:** its collision
check compared entries on board_fen + side-to-move only, flagging two keys
that differ solely in the en-passant field as "colliding". That is wrong --
en-passant availability is real game state (it changes the legal move set by
one capture), so two different real games reaching the identical board by
different move orders, one with the ep right still live and one without, are
genuinely different positions and may correctly store different best moves.
The agent's actual lookup uses the FULL key including ep, matching how the
book was built, so there was no real ambiguity -- a Python dict cannot hold
two values under an identical full key by construction. The flawed check was
removed, not worked around.

**Also worth recording for METHODOLOGY.md's future readers:** `tests/openings.py`
/ `tests/openings_gen.fen` (the general-purpose balanced-opening sets) are the
right choice for testing SEARCH or TIME-MANAGEMENT changes. They are the WRONG
choice for testing the opening book specifically, since the book only engages
on the competition's actual curated position pool. Use
`tests/openings_pool.fen` (308 positions, built from `tools/pgns_public` +
`tools/pgns`) for any future book-related test.

## UPDATE 2026-09-11 00:2x -- REAL BUG FOUND AND FIXED: tablebase probe trusted
## wrong data for an ending we never shipped, directly causing the round-101 loss

**This is the actual root cause of "the engine throwing away winning positions",**
found by re-investigating round 101 after the earlier clock-starvation diagnosis
turned out to be incomplete.

**What was actually wrong, in order of discovery:**
1. Re-traced R101's critical move (`Qf8+`, played with 1.763s on the clock)
   assuming clock starvation. Replayed the exact position through
   `_think_time`: soft/hard budgets were ~395/632ms -- small, but the engine
   only used **10.5ms** of it and reached a nominal depth of 24. **This was
   never a time problem** -- the search had budget and didn't need it.
2. The reported score for `Qf8+` was +917 (looked winning) despite the move
   hanging the queen. Traced the position *after* the queen is lost
   (K+P vs K+R, 4 pieces): the search reported the identical +917 there too --
   impossible for that position, which is a textbook loss for the pawn side.
3. Found the actual mechanism: `_probe_tablebase` was being consulted (5
   pieces, Q+P+K vs R+K = "KQPvKR") and returning a real move
   (`f5f8` = Qf8+), even though **`engine/syzygy/` contains no KQPvKR file at
   all** -- confirmed directly from the directory listing (36 real tables:
   3-man complete, 4-man complete, and the single 5-man KRPvKR, exactly as
   documented, nothing more).
4. **python-chess's `probe_wdl`/`probe_dtz` do not consistently raise
   KeyError for material outside the shipped set.** Verified directly: of 31
   legal moves from the R101 position, 8 returned a raw WDL (no exception) and
   23 correctly raised KeyError, for the *same* unshipped KQPvKR material class
   in every case. **All 8 that succeeded reported the identical wrong
   direction** -- every queen move from an objectively winning Q+P vs K+R
   position came back, after our sign negation, as `wdl=-2`, a **confirmed
   loss**. `_probe_tablebase`'s own DTZ tie-break then picked among these
   false "losses" for the one that resists longest, landing on `Qf8+` --
   which, being trusted as a tablebase result, was returned directly by
   `get_move()` without ever reaching real search.
5. **This is not the same-shaped bug as the WDL sign bug fixed earlier this
   session (Syzygy work, 2026-09-09)** -- that one was a genuine sign
   inversion, caught and fixed, and verified against real KRvK positions. This
   is a different failure: the sign convention is correct (re-verified with an
   unambiguous textbook KQvK sanity check, wdl=+2 as expected), but the
   *scope* of what `_probe_tablebase` trusts was never actually restricted to
   what we shipped -- it relied entirely on `probe_wdl`/`probe_dtz` raising
   KeyError for anything else, and that assumption is false.

**Fix, in `engine/agent.py`:** `_SHIPPED_TABLES`, a frozenset built from the
real filenames in `syzygy/` at warmup (not a hand-maintained list that could
drift from what's actually on disk), and `_table_name(board)`, which computes
the canonical Syzygy name for a position's material using python-chess's own
`normalize_tablename` -- deliberately not a hand-rolled White/Black ordering
convention, since that function is also what `open_tablebase()` itself uses
internally, so using it as the trust gate is exactly consistent with what the
library would actually try to read. `_probe_tablebase` now checks
`_table_name(board) in _SHIPPED_TABLES` for every candidate's resulting
position before trusting anything `probe_wdl`/`probe_dtz` return, regardless
of whether the library raises.

**This is a pure gate, not a heuristic, which is why it did not need an
SPRT** (the same basis as `repfix`): it can only ever remove trust from
probe results outside our shipped set and fall through to real search --
exactly what already happens, safely, for every other position on the board.
It cannot make any *already-correct* case behave differently, only stop a
*wrong* one from being trusted. Regression risk is therefore about proving the
gate doesn't accidentally exclude real coverage, which is directly tested.

**Verified, not just argued:**
- `tests/test_tb_gate.py` (new): confirms KQPvKR is absent from the shipped
  set, confirms `_probe_tablebase` now returns `None` for the exact bug
  position, confirms `get_move` on it is still legal and specifically does
  **not** replay the round-101 blunder (`f5f8`), and confirms three genuinely
  shipped endings (KPvK, KRPvKR, KRvK) are still trusted. All pass.
- Replayed the *exact* round-101 position with the fix: with ample time
  (60s) the real search now finds `Qf4+` scored as **a forced mate**
  (29975, depth 17) instead of the false "confirmed loss". Replayed again
  under the **identical 1.763s clock pressure** as the real game: still finds
  `Qf4+` (not `Qf8+`), score +727, depth 11, in 512ms -- comfortably inside
  budget. The fix holds under the exact real-game conditions, not just with
  time to spare.
- Validated from the **extracted shipped zip itself**, not just `engine/`:
  0 diff vs `build/`, book (24,319 entries) and 36 shipped tables both load,
  and the R101 position plays `f5f4` (not the blunder) from the extracted
  copy.
- All mandatory gates green: perft, repetition, history-chain, tt-mate,
  `test_book.py` -- 0 failures across all five.

**State:** `checkpoints/tbgate/` created from `engine/` (shieldfix + this
fix). `REFERENCE.txt` -> `tbgate`. `build/` synced,
`submission_tbgate.zip` built (32.1 MB) and validated end-to-end as above.
**This supersedes `submission_shieldfix.zip` -- upload this one, not that
one.**

**Scope note, stated plainly so it isn't overclaimed:** this fix closes the
specific mechanism found (an unshipped 5-piece ending returning trusted-but-
wrong probe data). It was diagnosed and proven against one real game
(round 101); round 92's near-identical blunder (`Rc3` at 1.575s, failing to
stop a pawn promotion) was flagged with the same surface symptom (a move
played under severe time pressure that ignores the position's most urgent
need) but was **not individually re-traced through this same mechanism**
before time ran out -- it is a strong candidate for the same root cause given
how closely it matches R101's signature, but that specific claim is
inference, not verified fact, and should be checked the same way if this
project continues.

## UPDATE 2026-09-11 00:4x -- scope of the tablebase-gate fix: NOT a one-off,
## 17 distinct unshipped material classes / ~97 positions across the archive

Following the tbgate fix, checked whether R101's `KQPvKR` was a one-off or a
recurring exposure. It is emphatically the latter.

**R92 checked first, on the same hypothesis.** Traced its actual critical
moment properly (not the surface-level `Rc3` at 1.575s flagged earlier --
that turned out to be a dead end: verified directly that **no legal move at
that point stopped the promotion**, so the position was already lost by
ply113 regardless of what was played). The real moment was 8 plies earlier:
ply101, `Rxh3+` -- capturing Black's passed h-pawn outright, with check,
completely removing the only winning try in the position -- was legal and
available. The engine played `Kd4` instead. Piece count there is 7, **above**
the tablebase threshold, so this is confirmed to be a *different* mechanism
from the KQPvKR bug: replayed with 60s (no time pressure, reached the
iterative-deepening ceiling of depth 120) and the engine *still* evaluates
the position as dead equal (score=0) and still does not play `Rxh3+`. This is
a real evaluation/search-horizon weakness (a passed-pawn promotion race
outrunning what the eval rewards), not a data-integrity bug, and does **not**
have the same provable-safety fix available -- any correction here is an
eval/search change and would need real SPRT validation, which this project's
own history says is unreliable to guess right. Not attempted tonight; recorded
here rather than guessed at.

(One tangent chased and resolved during this: the reported "depth=120"
looked alarming against the documented `MAX_SEARCH_PLY=100` hard cap. Checked
directly in `ca_search.py` -- `max_depth` passed into `search_root` is
`MAX_PLY - 8 = 120` (the iterative-deepening loop's own ceiling,
`range(1, max_depth+1)`), a completely different counter from the recursive
`ply` parameter, which is independently capped at `MAX_SEARCH_PLY=100`
(line 281). No memory-safety issue; false alarm, but worth having actually
checked rather than assumed.)

**Then swept every archived game for the KQPvKR pattern's true scope**, not
just the two instances found by chance. For every position in all 61 games
with piece count <=5: computed its canonical material name and checked
shipped/unshipped.

| unshipped material | occurrences | | shipped material (for scale) | occurrences |
|---|---|---|---|---|
| KQRPvK | 20 | | KRvKR | 214 |
| KRPPvK | 15 | | KBPvK | 71 |
| KQPPvK | 12 | | KRPvK | 48 |
| KQQPvK | 12 | | KQvKR | 30 |
| KRPvKP | 10 | | KQPvK | 24 |
| KQQBvK | 8 | | KQQvK | 20 |
| KQPvKR | 4 *(the R101 bug)* | | KQvK | 14 |
| KQPvKP | 4 | | KRvKP | 10 |
| KRBvKR | 4 | | KRPvKR | 9 *(our one real 5-man)* |
| KBPPvK | 3 | | KPvKP | 9 |
| (7 more, 1-2 each) | 7 | | KPvK | 9 |

**17 distinct unshipped classes, ~97 positions total** across the archive --
this was a systematically recurring exposure, not a one-off. R81 (a game we
*won*) independently reproduced the identical mechanism for `KRPPvK` at ply150
(confirmed: `agent._table_name` -> `KRPPvK`, correctly absent from
`_SHIPPED_TABLES`, `_probe_tablebase` correctly returns `None` post-fix) --
the only reason it didn't cost that game is that the position was already so
overwhelmingly winning (K+R+2P vs bare K) that even a wrong "you're losing"
signal, had it fired there, likely wouldn't have found a move bad enough to
actually lose from. R101 was not so fortunate.

**All correctly-shipped classes were re-confirmed still trusted** (`KRvKR`,
`KRPvK`, `KQvKR`, `KQPvK`, `KQQvK`, `KQvK`, `KRvKP`, `KRPvKR`, `KPvKP`, `KPvK`,
`KPPvK`, `KRBvK` all show `shipped=yes` in the sweep) -- the gate is not
overcorrecting and falling back to search for positions we genuinely have
data for.

**Net effect of tonight's fix, stated precisely:** every one of these ~97
positions, across every future game that reaches a similarly-shaped
few-piece ending, now correctly falls through to real search instead of
risking a trusted-but-wrong tablebase verdict. This is the single
highest-confidence, highest-scope finding of the session.

## CORRECTION 2026-09-11 -- the R81/KRPPvK claim above is WRONG, struck

The "17 distinct unshipped material classes" sweep and the specific claim
that "R81 (a game we won) independently reproduced the KRPPvK mechanism" is
**incorrect and should not be relied on for that specific game.** Checked
colour properly this time (an error I made and should have caught
immediately, the same class of mistake as earlier sessions' colour mixups):
in round 81, **we are Black, and the result was 1-0 -- a LOSS**, not a win as
previously stated. The `KRPPvK` position I probed at ply150 was **White's
(the opponent's) position to move**, never a position our own `get_move()`
evaluates -- so it has no bearing on our engine's tablebase gate at all.
Retracted.

**Round 81 re-traced properly.** Material stayed exactly even for the first
90 plies, then eroded gradually and continuously from ply ~91 to the finish
(no single sharp drop) -- this is the already-documented "long grind, slowly
outplayed" pattern (13 of 15 original losses), not a discrete bug with a
clean before/after signature like R101 or R92. No further action taken on it.

**The 17-class / ~97-position sweep result itself still stands** -- that was
computed directly from material signatures across all games via
`agent._table_name`, independent of which side's move any given position was,
and does not depend on the retracted R81 framing. What is retracted is only
the specific claim that R81 was a second confirmed real-game reproduction.

**Also caught while re-checking colours: R86 was likewise misclassified**
as a win earlier (it is in fact a loss, Black, 1-0) -- flagged for proper
re-investigation, not yet done at time of this correction.
