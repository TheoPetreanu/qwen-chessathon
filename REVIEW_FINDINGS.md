# Review findings — Phases 0-2

Every claim below is labelled **PROVEN** (test/engine output included) or
**HYPOTHESIS** (with confidence). Nothing in `engine/` was changed; the only
additions are diagnostics under `tools/`.

---

## PHASE 0 — what is actually live

**PROVEN.** Current repo state, verified by hash:

| artifact | contents | `is_repetition` | history |
|---|---|---|---|
| `build/` | **v1** | BLIND (`rep_len-2`) | `_SEEN` + zero placeholders |
| `submission.zip` | v1 | BLIND | `_SEEN` |
| `submission_new.zip` | v1 | BLIND | `_SEEN` |
| `submission_repfix.zip` | repfix | FIXED (`rep_len-3`) | `_SEEN` |
| `submission_repfix2.zip` | repfix2 | FIXED | `_HIST` ply-chain |
| `engine/` | == `checkpoints/repfix2` | FIXED | `_HIST` |

`checkpoints/REFERENCE.txt` = `repfix2` and matches `engine/` exactly.

**BLOCKING, UNRESOLVED:** which zip is live on the server cannot be determined
from this machine. Two of the four uploadable zips are v1. Timeline note:
`submission_repfix.zip` was built 16:35 local, `submission_repfix2.zip` at
20:21 local, and round 59 finished 20:13 UTC — so **round 59 may have run on
repfix (no repfix2)**. This must be confirmed on the dashboard before anything
else; it is the largest prize in the brief and it is still open.

**PROVEN.** Test suite, all green, no match running:

```
test_sprt           exit=0 failures: 0
test_repetition     exit=0 failures: 0
test_history_chain  exit=0 failures: 0
test_perft          exit=0 failures: 0
```

---

## PHASE 2 — the conversion set, and two errors in the brief

### Finding 1 — R54 is a repetition, not an endgame-technique failure. **PROVEN.**

Both `REVIEW_TASK.md` §2 and the EPD comment state R54 is *"endgame technique,
not repetition"*, and Phase 2 recommends building make-progress endgame eval on
that basis. Replaying the actual game:

| game | ply | move | occurrences of resulting position | `is_repetition(3)` |
|---|---|---|---|---|
| R54 NajeebA | 94 | Kf6 | **3** | **True** |
| R53 Agread | 68 | Qb6 | 2 | False |
| R58 AGS | 78 | Kh3 | 2 | False |
| R52 Nakamura | 36 | Nb3 | 1 | False |

`Kf6` produced an immediate threefold and ended the game. R54 is the *purest*
repetition case of the four, not a technique failure. **Building endgame
make-progress eval on R54 as the motivating example would be chasing the wrong
cause.** (Endgame eval may still be worth doing on its own merits — but this
position is not evidence for it.)

### Finding 2 — `conversion_test.epd` cannot test the failure it was built for. **PROVEN.**

A bare FEN carries no repetition history, and three of the four positions failed
*because of* history. Consequences, both observed:

- Stockfish scores the position after R58 `Kh3` at **+703** when handed the bare
  FEN, versus **0** in `acpl_analysis.py`. The difference is that
  `chess.engine.analyse(board)` transmits the move stack, so Stockfish sees the
  repetition; the EPD strips it.
- Running the EPD set through our engine, **v1 — the build that actually drew
  these games — plays the correct move in all four** at a 120s budget, matching
  Stockfish's `bm` in three:

```
conv-r53-agread    bm=c6   played=c6     +659 -> +653   KEEPS IT
conv-r58-ags       bm=Ne2  played=Kh3    +688 -> +701   KEEPS IT
conv-r54-najeeba   bm=Kd4  played=Kd4   +9920 -> +9930  KEEPS IT
conv-r52-nakamura  bm=Nf3  played=Nf3    +210 -> +223   KEEPS IT
```

So the EPD set as written **cannot distinguish v1 from repfix2** and should not
be used as the Phase 2 pass/fail gate. `tools/repetition_replay.py` (added) is
the corrected harness: it rebuilds the true ply-by-ply history into `_HIST`
before asking for a move.

### Finding 3 — R52 is the one genuine positional blunder, and it is clock-dependent. **PROVEN.**

At a 120s budget v1 plays the best move `Nf3`. At 20s and 5s it plays the game
move `Nb3`, reproducing the blunder:

```
120s: played=Nf3  +210 -> +223  KEEPS IT
 20s: played=Nb3  +303 ->  +25  leaks
  5s: played=Nb3  +198 ->  +19  leaks
```

This is a **depth/time failure, not a repetition failure** — the one position in
the set where the brief's "conversion" framing is right, and it points at the
time-management work (Phase 3 / backlog item 2), not at repetition.

### Finding 4 — the in-game failures do not reproduce offline. **PROVEN (negative result).**

For R54 I seeded the true 93-ply history and asked both builds for a move at
20s, 5s and 2s, and again with `--warm` (feeding every prior own-turn position
so the TT, killers and history accumulate as they did in the game):

| build | cold 20s | cold 5s | cold 2s | warm 5s |
|---|---|---|---|---|
| v1 | Kd4 | Kd4 | Kd4 | Kxd5 |
| repfix2 | Kxd5 | Kxd5 | Kxd5 | Kd4 |

**Every configuration avoids `Kf6`, including v1** — which played `Kf6` in the
real game. I could not reproduce the failure.

Implication: these positions **cannot serve as a regression suite** in their
current form, and any claim that "repfix fixes R53/R54/R58" is currently
**unproven** — as is the converse. repfix's value rests on its own independent
evidence (the deterministic `test_repetition.py` defect plus +41 ±18 over 522
games), not on these games.

**HYPOTHESIS (medium confidence)** for the gap: the real move was made on a much
smaller clock than any tested (R54 ended with 4.8s total remaining), and/or
depends on accumulated in-game state that a partial replay cannot recreate.
Settling it needs a full-game replay driving the engine through every one of its
own turns from move 1 under the real clock schedule.

---

## What the brief got wrong

1. **"R54 is technique, not repetition"** — false, proven above. Phase 2's
   endgame-eval recommendation loses its motivating example.
2. **The EPD set as a pass/fail gate** — cannot work; it does not encode
   history, and v1 passes all four.
3. **"Confirm repfix resolves each EPD position"** — not answerable via that
   set; needs the history-aware harness.

## What the brief got right, and stands

- Move quality is not the problem (competitive ACPL ≈ 20-30 recomputed).
- The terminal-node scoring bug in v1 of `acpl_analysis.py` was real; the
  shipped v2 fixes it (`terminal_score()` + `CPL_CAP`), verified present.
- Tablebases are the wrong spend for these draws (piece counts 11-23).
- Phase 0 is the top priority — and it is still open.

## Recommended next steps, in order

1. **Confirm the live build on the dashboard.** If it is not repfix2, upload
   `submission_repfix2.zip` before any further engineering.
2. **Do not build endgame eval on R54.** If endgame eval is wanted, motivate it
   with positions that are actually technique failures.
3. **Time management (backlog item 2)** now has direct evidence behind it: R52
   reproduces as a blunder at 20s and 5s but not at 120s.
4. **Full-game replay harness** if the thrown-win regression suite is wanted;
   the current per-position approach demonstrably cannot reproduce the failures.
