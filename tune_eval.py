"""Texel tuning for engine/ca_eval.py term weights.

ca_eval.evaluate() reads its weight tables as njit module-level globals, which
numba freezes into the compiled function at JIT time -- mutating them from
Python afterwards is silently ignored (verified empirically: patching
MG_VALUE[1] in place and re-calling evaluate() still returns the pre-patch
score). So candidate weights cannot be tried by poking the real function.

Instead this file has its own njit function, evaluate_w(bb, occ, mail, st, W),
that is bit-for-bit the same evaluation but reads every term out of a single
flat float64 array W passed in as an ARGUMENT. Numba does not freeze argument
arrays, so changing W between calls changes the result with no recompilation.
This never touches engine/ or build/: it is a standalone copy used only to
search for better constants offline. Once tuned, the resulting numbers are
copied by hand into ca_eval.py's constants -- a pure data edit, no logic
change, so it carries none of the risk a change to the search hot path would.

Correctness gate: with W set to ca_eval's current constants, evaluate_w must
match evaluate() exactly on every sampled position. That is checked before any
tuning happens; if it doesn't match, the transcription has a bug and the tune
is not trustworthy.
"""
import sys, os, math, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
import numpy as np
from numba import njit
import chess

import ca_eval
from ca_position import new_position, from_board
from ca_movegen import (
    popcount, lsb, bit, rook_attacks, bishop_attacks, queen_attacks,
    KNIGHT_ATTACKS, KING_ATTACKS, PAWN_ATTACKS, U0, U1,
    WP, WN, WB, WR, WQ, WK, BP, BN, BB_, BR, BQ, BK, EMPTY, WHITE, BLACK,
)
from ca_tables import FILE_BB, ADJACENT_FILES, FRONT_SPAN, PASSED_MASK, KING_ZONE

NOT_FILE_A = np.uint64(0xFEFEFEFEFEFEFEFE)
NOT_FILE_H = np.uint64(0x7F7F7F7F7F7F7F7F)
S7 = np.uint64(7)
S9 = np.uint64(9)

# --- flat weight layout -------------------------------------------------
OFF_MG_VALUE = 0
OFF_EG_VALUE = OFF_MG_VALUE + 6
OFF_PST_MG = OFF_EG_VALUE + 6          # 6 x 64
OFF_PST_EG = OFF_PST_MG + 384          # 6 x 64
OFF_PASSED_MG = OFF_PST_EG + 384       # 8
OFF_PASSED_EG = OFF_PASSED_MG + 8      # 8
OFF_MOB_MG = OFF_PASSED_EG + 8         # 6
OFF_MOB_EG = OFF_MOB_MG + 6            # 6
OFF_MOB_BASE = OFF_MOB_EG + 6          # 6
OFF_KING_ATT = OFF_MOB_BASE + 6        # 6
OFF_BISHOP_PAIR_MG = OFF_KING_ATT + 6
OFF_BISHOP_PAIR_EG = OFF_BISHOP_PAIR_MG + 1
OFF_DOUBLED_MG = OFF_BISHOP_PAIR_EG + 1
OFF_DOUBLED_EG = OFF_DOUBLED_MG + 1
OFF_ISOLATED_MG = OFF_DOUBLED_EG + 1
OFF_ISOLATED_EG = OFF_ISOLATED_MG + 1
OFF_ROOK_OPEN_MG = OFF_ISOLATED_EG + 1
OFF_ROOK_OPEN_EG = OFF_ROOK_OPEN_MG + 1
OFF_ROOK_SEMI_MG = OFF_ROOK_OPEN_EG + 1
OFF_ROOK_SEMI_EG = OFF_ROOK_SEMI_MG + 1
OFF_SHIELD_MISSING_MG = OFF_ROOK_SEMI_EG + 1
OFF_TEMPO = OFF_SHIELD_MISSING_MG + 1
W_LEN = OFF_TEMPO + 1

TOTAL_PHASE = 24
PHASE_WEIGHT = np.array([0, 1, 1, 2, 4, 0], dtype=np.int64)


def pack_default_weights():
    W = np.zeros(W_LEN, dtype=np.float64)
    W[OFF_MG_VALUE:OFF_MG_VALUE + 6] = ca_eval.MG_VALUE
    W[OFF_EG_VALUE:OFF_EG_VALUE + 6] = ca_eval.EG_VALUE
    W[OFF_PST_MG:OFF_PST_MG + 384] = ca_eval.PST_MG.reshape(-1)
    W[OFF_PST_EG:OFF_PST_EG + 384] = ca_eval.PST_EG.reshape(-1)
    W[OFF_PASSED_MG:OFF_PASSED_MG + 8] = ca_eval.PASSED_MG
    W[OFF_PASSED_EG:OFF_PASSED_EG + 8] = ca_eval.PASSED_EG
    W[OFF_MOB_MG:OFF_MOB_MG + 6] = ca_eval.MOB_MG
    W[OFF_MOB_EG:OFF_MOB_EG + 6] = ca_eval.MOB_EG
    W[OFF_MOB_BASE:OFF_MOB_BASE + 6] = ca_eval.MOB_BASE
    W[OFF_KING_ATT:OFF_KING_ATT + 6] = ca_eval.KING_ATT_WEIGHT
    W[OFF_BISHOP_PAIR_MG] = ca_eval.BISHOP_PAIR_MG
    W[OFF_BISHOP_PAIR_EG] = ca_eval.BISHOP_PAIR_EG
    W[OFF_DOUBLED_MG] = ca_eval.DOUBLED_MG
    W[OFF_DOUBLED_EG] = ca_eval.DOUBLED_EG
    W[OFF_ISOLATED_MG] = ca_eval.ISOLATED_MG
    W[OFF_ISOLATED_EG] = ca_eval.ISOLATED_EG
    W[OFF_ROOK_OPEN_MG] = ca_eval.ROOK_OPEN_MG
    W[OFF_ROOK_OPEN_EG] = ca_eval.ROOK_OPEN_EG
    W[OFF_ROOK_SEMI_MG] = ca_eval.ROOK_SEMI_MG
    W[OFF_ROOK_SEMI_EG] = ca_eval.ROOK_SEMI_EG
    W[OFF_SHIELD_MISSING_MG] = ca_eval.SHIELD_MISSING_MG
    W[OFF_TEMPO] = ca_eval.TEMPO
    return W


# Indices (within the flat array) of terms we actually tune. PSTs are left
# fixed: 768 parameters against a few hundred self-play positions would
# overfit badly, so only the hand-set scalar term weights are in play.
def tunable_indices():
    idx = []
    idx += list(range(OFF_MG_VALUE + 1, OFF_MG_VALUE + 5))   # N,B,R,Q (skip P,K)
    idx += list(range(OFF_EG_VALUE + 1, OFF_EG_VALUE + 5))
    idx += list(range(OFF_PASSED_MG, OFF_PASSED_MG + 8))
    idx += list(range(OFF_PASSED_EG, OFF_PASSED_EG + 8))
    idx += list(range(OFF_MOB_MG + 1, OFF_MOB_MG + 5))
    idx += list(range(OFF_MOB_EG + 1, OFF_MOB_EG + 5))
    idx += [OFF_BISHOP_PAIR_MG, OFF_BISHOP_PAIR_EG,
            OFF_DOUBLED_MG, OFF_DOUBLED_EG,
            OFF_ISOLATED_MG, OFF_ISOLATED_EG,
            OFF_ROOK_OPEN_MG, OFF_ROOK_OPEN_EG,
            OFF_ROOK_SEMI_MG, OFF_ROOK_SEMI_EG,
            OFF_SHIELD_MISSING_MG, OFF_TEMPO]
    return idx


@njit(cache=False, inline='always')
def pawn_attacks_bb(pawns, is_white):
    if is_white:
        return ((pawns & NOT_FILE_A) << S7) | ((pawns & NOT_FILE_H) << S9)
    return ((pawns & NOT_FILE_A) >> S9) | ((pawns & NOT_FILE_H) >> S7)


@njit(cache=False)
def evaluate_w(bb, occ, mail, st, W):
    """Same evaluation as ca_eval.evaluate(), parameterised on W (float64)."""
    mg = 0.0
    eg = 0.0
    phase = 0

    wp = bb[WP]
    bp = bb[BP]
    all_occ = occ[2]
    w_pawn_att = pawn_attacks_bb(wp, True)
    b_pawn_att = pawn_attacks_bb(bp, False)
    wksq = lsb(bb[WK])
    bksq = lsb(bb[BK])
    w_zone = KING_ZONE[WHITE][wksq]
    b_zone = KING_ZONE[BLACK][bksq]
    w_danger = 0.0
    b_danger = 0.0

    for colour in range(2):
        base = 0 if colour == WHITE else 6
        sign = 1.0 if colour == WHITE else -1.0
        own_occ = occ[colour]
        own_pawns = wp if colour == WHITE else bp
        enemy_pawn_att = b_pawn_att if colour == WHITE else w_pawn_att
        enemy_zone = b_zone if colour == WHITE else w_zone
        mob_area = ~(own_occ | enemy_pawn_att)

        for pt in range(6):
            pieces = bb[base + pt]
            while pieces:
                sq = lsb(pieces)
                pieces &= pieces - U1
                rel = sq if colour == WHITE else sq ^ 56
                mg += sign * (W[OFF_MG_VALUE + pt] + W[OFF_PST_MG + pt * 64 + rel])
                eg += sign * (W[OFF_EG_VALUE + pt] + W[OFF_PST_EG + pt * 64 + rel])
                phase += PHASE_WEIGHT[pt]

                if pt == 1:
                    att = KNIGHT_ATTACKS[sq]
                elif pt == 2:
                    att = bishop_attacks(sq, all_occ)
                elif pt == 3:
                    att = rook_attacks(sq, all_occ)
                elif pt == 4:
                    att = queen_attacks(sq, all_occ)
                else:
                    att = U0

                if pt >= 1 and pt <= 4:
                    m = popcount(att & mob_area) - W[OFF_MOB_BASE + pt]
                    mg += sign * m * W[OFF_MOB_MG + pt]
                    eg += sign * m * W[OFF_MOB_EG + pt]
                    zone_hits = popcount(att & enemy_zone)
                    if zone_hits > 0:
                        d = W[OFF_KING_ATT + pt] * zone_hits
                        if colour == WHITE:
                            b_danger += d
                        else:
                            w_danger += d

                if pt == 3:
                    f = sq & 7
                    if (FILE_BB[f] & own_pawns) == 0:
                        enemy_pawns = bp if colour == WHITE else wp
                        if (FILE_BB[f] & enemy_pawns) == 0:
                            mg += sign * W[OFF_ROOK_OPEN_MG]
                            eg += sign * W[OFF_ROOK_OPEN_EG]
                        else:
                            mg += sign * W[OFF_ROOK_SEMI_MG]
                            eg += sign * W[OFF_ROOK_SEMI_EG]

                if pt == 0:
                    f = sq & 7
                    enemy_pawns = bp if colour == WHITE else wp
                    if (PASSED_MASK[colour][sq] & enemy_pawns) == 0:
                        r = (sq >> 3) if colour == WHITE else 7 - (sq >> 3)
                        mg += sign * W[OFF_PASSED_MG + r]
                        eg += sign * W[OFF_PASSED_EG + r]
                        if (bit(sq) & (w_pawn_att if colour == WHITE else b_pawn_att)) != 0:
                            # matches the original's integer ">> 2": floor
                            # division, not truncation, so it agrees exactly
                            # at the (integer-valued) default weights
                            eg += sign * math.floor(W[OFF_PASSED_EG + r] / 4.0)
                    if (ADJACENT_FILES[f] & own_pawns) == 0:
                        mg += sign * W[OFF_ISOLATED_MG]
                        eg += sign * W[OFF_ISOLATED_EG]
                    if (FRONT_SPAN[colour][sq] & own_pawns) != 0:
                        mg += sign * W[OFF_DOUBLED_MG]
                        eg += sign * W[OFF_DOUBLED_EG]

        if popcount(bb[base + 2]) >= 2:
            mg += sign * W[OFF_BISHOP_PAIR_MG]
            eg += sign * W[OFF_BISHOP_PAIR_EG]

    for colour in range(2):
        ksq = wksq if colour == WHITE else bksq
        own_pawns = wp if colour == WHITE else bp
        sign = 1.0 if colour == WHITE else -1.0
        kf = ksq & 7
        lo = kf - 1 if kf > 0 else 0
        hi = kf + 1 if kf < 7 else 7
        for f in range(lo, hi + 1):
            if (FILE_BB[f] & own_pawns & FRONT_SPAN[colour][ksq - (ksq & 7) + f]) == 0:
                mg += sign * W[OFF_SHIELD_MISSING_MG]

    if w_danger > 0:
        d = w_danger if w_danger < 40 else 40.0
        mg -= math.floor((d * d) / 4.0)
    if b_danger > 0:
        d = b_danger if b_danger < 40 else 40.0
        mg += math.floor((d * d) / 4.0)

    if phase > TOTAL_PHASE:
        phase = TOTAL_PHASE
    num = mg * phase + eg * (TOTAL_PHASE - phase)
    # truncate toward zero, matching the original's explicit branch (Python's
    # integer // floors toward -inf, which is why it isn't used directly there)
    if num >= 0:
        score = math.floor(num / TOTAL_PHASE)
    else:
        score = -math.floor((-num) / TOTAL_PHASE)

    if st[0] == BLACK:
        score = -score
    return score + W[OFF_TEMPO]


def load_positions(path):
    """Returns list of (bb, occ, mail, st, result_from_stm_pov)."""
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            fen, result = line.split("\t")
            result = float(result)
            board = chess.Board(fen)
            bb, occ, mail, st, hsh = new_position()
            from_board(board, bb, occ, mail, st, hsh)
            # result is from White's POV; flip to side-to-move POV to match
            # evaluate()'s convention
            r_stm = result if st[0] == WHITE else 1.0 - result
            out.append((bb, occ, mail, st, r_stm))
    return out


def verify_match(positions, W):
    max_diff = 0
    n_mismatch = 0
    for bb, occ, mail, st, _ in positions:
        real = ca_eval.evaluate(bb, occ, mail, st)
        mine = evaluate_w(bb, occ, mail, st, W)
        diff = abs(real - mine)
        if diff > 1e-6:
            n_mismatch += 1
            max_diff = max(max_diff, diff)
    return n_mismatch, max_diff


def sigmoid(x, k):
    return 1.0 / (1.0 + math.exp(-x / k))


def total_loss(positions, W, k, W0=None, indices=None, reg_lambda=0.0):
    s = 0.0
    for bb, occ, mail, st, r in positions:
        e = evaluate_w(bb, occ, mail, st, W)
        p = sigmoid(e, k)
        s += (r - p) ** 2
    loss = s / len(positions)
    if reg_lambda > 0.0 and W0 is not None:
        # anchor tunable params to their hand-set defaults, scaled per-param,
        # so a few hundred correlated self-play positions can't swing a term
        # (e.g. a rook's value) somewhere chess-nonsensical just because this
        # small sample happened not to exercise it much
        reg = 0.0
        for i in indices:
            scale = max(abs(W0[i]), 10.0)
            reg += ((W[i] - W0[i]) / scale) ** 2
        loss += reg_lambda * reg / len(indices)
    return loss


def fit_k(positions, W):
    """Find the scaling constant K that best fits eval -> win probability,
    coarse grid search then refine -- K itself is not a term weight, just the
    logistic scale, so it doesn't need coordinate descent."""
    best_k, best_loss = 200.0, None
    for k in [80, 100, 130, 160, 200, 250, 300, 400, 500, 650, 800]:
        l = total_loss(positions, W, k)
        if best_loss is None or l < best_loss:
            best_loss, best_k = l, k
    # refine
    step = best_k / 4
    for _ in range(8):
        improved = False
        for cand in (best_k - step, best_k + step):
            if cand <= 10:
                continue
            l = total_loss(positions, W, cand)
            if l < best_loss:
                best_loss, best_k, improved = l, cand, True
        step *= 0.5
    return best_k, best_loss


def texel_tune(positions, W0, k, indices, n_epochs=6, step_frac=0.10, min_step=1.0,
               reg_lambda=0.0):
    """Classic Texel local search: for each tunable parameter, try +step/-step,
    keep whichever reduces total loss, shrink step over epochs."""
    W = W0.copy()
    loss = total_loss(positions, W, k, W0, indices, reg_lambda)
    print("initial loss (k=%.1f, lambda=%.4f): %.6f" % (k, reg_lambda, loss))
    for epoch in range(n_epochs):
        improved_any = False
        for i in indices:
            step = max(abs(W[i]) * step_frac, min_step)
            for cand_step in (step, -step):
                W[i] += cand_step
                new_loss = total_loss(positions, W, k, W0, indices, reg_lambda)
                if new_loss < loss - 1e-9:
                    loss = new_loss
                    improved_any = True
                    break
                else:
                    W[i] -= cand_step
        print("epoch %d  loss=%.6f  improved=%s" % (epoch, loss, improved_any), flush=True)
        if not improved_any:
            step_frac *= 0.5
            if step_frac < 0.01:
                break
    return W, loss


def main():
    data_path = sys.argv[1] if len(sys.argv) > 1 else "tools/texel_data.txt"
    reg_lambda = float(sys.argv[2]) if len(sys.argv) > 2 else 0.05
    positions = load_positions(data_path)
    print("loaded", len(positions), "positions")

    W0 = pack_default_weights()
    n_mismatch, max_diff = verify_match(positions, W0)
    print("correctness gate: %d/%d mismatches, max diff %.6f" %
          (n_mismatch, len(positions), max_diff))
    if n_mismatch > 0:
        print("ABORTING: evaluate_w does not match ca_eval.evaluate(); fix the transcription first.")
        return

    # held-out split so overfitting shows up as train/val loss diverging,
    # rather than only being caught later by a full gauntlet run
    rng = random.Random(1234)
    shuffled = positions[:]
    rng.shuffle(shuffled)
    n_val = max(1, len(shuffled) // 5)
    val, train = shuffled[:n_val], shuffled[n_val:]
    print("train=%d  val=%d" % (len(train), len(val)))

    k, k_loss = fit_k(train, W0)
    val_k_loss = total_loss(val, W0, k)
    print("fitted K=%.1f  baseline train loss=%.6f  baseline val loss=%.6f" %
          (k, k_loss, val_k_loss))

    indices = tunable_indices()
    print("tuning", len(indices), "parameters  reg_lambda=%.4f" % reg_lambda)
    W_tuned, tuned_loss = texel_tune(train, W0, k, indices, reg_lambda=reg_lambda)
    val_tuned_loss = total_loss(val, W_tuned, k)

    print("\n=== RESULT ===")
    print("train loss %.6f -> %.6f (%.2f%% reduction)" %
          (k_loss, tuned_loss, 100.0 * (k_loss - tuned_loss) / k_loss))
    print("val   loss %.6f -> %.6f (%.2f%% reduction)" %
          (val_k_loss, val_tuned_loss, 100.0 * (val_k_loss - val_tuned_loss) / val_k_loss))
    if val_tuned_loss > val_k_loss:
        print("WARNING: validation loss got WORSE -- this tune is overfit, do not ship it as-is.")

    names = {}
    for i in range(1, 5):
        names[OFF_MG_VALUE + i] = "MG_VALUE[%d]" % i
        names[OFF_EG_VALUE + i] = "EG_VALUE[%d]" % i
    for r in range(8):
        names[OFF_PASSED_MG + r] = "PASSED_MG[%d]" % r
        names[OFF_PASSED_EG + r] = "PASSED_EG[%d]" % r
    for i in range(1, 5):
        names[OFF_MOB_MG + i] = "MOB_MG[%d]" % i
        names[OFF_MOB_EG + i] = "MOB_EG[%d]" % i
    names[OFF_BISHOP_PAIR_MG] = "BISHOP_PAIR_MG"
    names[OFF_BISHOP_PAIR_EG] = "BISHOP_PAIR_EG"
    names[OFF_DOUBLED_MG] = "DOUBLED_MG"
    names[OFF_DOUBLED_EG] = "DOUBLED_EG"
    names[OFF_ISOLATED_MG] = "ISOLATED_MG"
    names[OFF_ISOLATED_EG] = "ISOLATED_EG"
    names[OFF_ROOK_OPEN_MG] = "ROOK_OPEN_MG"
    names[OFF_ROOK_OPEN_EG] = "ROOK_OPEN_EG"
    names[OFF_ROOK_SEMI_MG] = "ROOK_SEMI_MG"
    names[OFF_ROOK_SEMI_EG] = "ROOK_SEMI_EG"
    names[OFF_SHIELD_MISSING_MG] = "SHIELD_MISSING_MG"
    names[OFF_TEMPO] = "TEMPO"

    print("\nparameter changes (old -> new):")
    for i in indices:
        old, new = W0[i], W_tuned[i]
        if abs(old - new) > 0.05:
            print("  %-20s %8.2f -> %8.2f" % (names.get(i, "idx%d" % i), old, new))

    np.save("tools/texel_tuned_W.npy", W_tuned)
    print("\nsaved full tuned weight vector to tools/texel_tuned_W.npy")


if __name__ == "__main__":
    main()
