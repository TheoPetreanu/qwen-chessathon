"""Search: iterative deepening PVS with alpha-beta, on top of the bitboard core.

Everything runs inside numba nopython code, including the iterative deepening
driver, so the whole search costs no Python interpreter time. The clock is read
through an objmode escape hatch every 2048 nodes, which is ~0.1% overhead.

Transposition table entries are packed into one int64 alongside a uint64 key:
    bits  0-31  best move
    bits 32-47  score, offset by +32768 so it fits unsigned in 16 bits
    bits 48-55  depth
    bits 56-57  bound flag (0 exact, 1 lower, 2 upper)

CANDIDATE repfix+item5: the repetition-detection fix (is_repetition walked the
wrong parity chain and could never fire -- see its docstring) PLUS TASK3.md #5,
better LMR shaping (3-way mutually-exclusive check on the move's existing
ordering score in mscores[ply][i], replacing the single history>4000 rule).
The two edits are in unrelated parts of this file and do not interact.

This is tested against the ADOPTED repfix engine, not against v1, so that the
measurement answers "does item 5 add anything on top of the fix?" rather than
re-measuring the fix's own (large, already-established) gain. See PROGRESS.md.
"""
import time
import numpy as np
from numba import njit, objmode

from ca_movegen import (
    gen_moves, make_move, unmake_move, make_null, unmake_null, in_check,
    popcount, lsb, bit, U0, U1, EMPTY, WHITE, BLACK,
    m_from, m_to, m_promo, m_piece, m_captured, m_is_castle, m_is_ep,
)
from ca_eval import evaluate, see, SEE_VALUE

MATE = 30000
MATE_IN_MAX = MATE - 256
INF = 32000
TT_BITS = 22
TT_SIZE = 1 << TT_BITS
TT_MASK = np.uint64(TT_SIZE - 1)

FLAG_EXACT, FLAG_LOWER, FLAG_UPPER = 0, 1, 2

MAX_SEARCH_PLY = 100     # stacks are MAX_PLY + 8 = 136 rows
MAX_QS_PLY = 118

# Late-move reduction table, indexed [depth][move number].
_LMR = np.zeros((64, 64), dtype=np.int64)
for _d in range(1, 64):
    for _m in range(1, 64):
        _LMR[_d][_m] = int(0.80 + np.log(_d) * np.log(_m) / 2.25)
LMR = _LMR


def new_tt():
    return (np.zeros(TT_SIZE, dtype=np.uint64),
            np.zeros(TT_SIZE, dtype=np.int64))


def new_heuristics():
    killers = np.zeros((160, 2), dtype=np.int32)
    history = np.zeros((12, 64), dtype=np.int64)
    counter = np.zeros((12, 64), dtype=np.int32)
    return killers, history, counter


# =============================================================================
# Transposition table
# =============================================================================
@njit(cache=False, inline='always')
def tt_pack(move, score, depth, flag):
    s = np.int64(score) + np.int64(32768)
    return (np.int64(np.uint32(move)) |
            (s << 32) | (np.int64(depth) << 48) | (np.int64(flag) << 56))


@njit(cache=False, inline='always')
def tt_unpack_move(data):
    return np.int32(data & np.int64(0xFFFFFFFF))


@njit(cache=False, inline='always')
def tt_unpack_score(data):
    return np.int64((data >> 32) & np.int64(0xFFFF)) - np.int64(32768)


@njit(cache=False, inline='always')
def tt_unpack_depth(data):
    return np.int64((data >> 48) & np.int64(0xFF))


@njit(cache=False, inline='always')
def tt_unpack_flag(data):
    return np.int64((data >> 56) & np.int64(0x3))


# =============================================================================
# Repetition
# =============================================================================
@njit(cache=False)
def is_repetition(rep_hist, rep_len, key, halfmove):
    """True if `key` already occurred since the last irreversible move.

    One earlier occurrence is treated as a draw inside the search: if the
    position can be reached again the opponent can force the third repetition,
    and the referee claims it.

    The current position lives at index rep_len-1, so same-side-to-move
    ancestors are at rep_len-3, rep_len-5, ... Starting the walk at rep_len-2
    (as this did before) steps down the OPPOSITE parity chain: those entries
    always have the other side to move, and compute_hash() xors ZOBRIST_SIDE
    for black, so they can never equal `key`. The remaining entries on that
    chain are the placeholder zeros agent.py writes between our own observed
    positions. The net effect was that this function could never return True
    and the search was completely blind to repetition draws -- it would shuffle
    into a threefold without ever scoring the line as a draw. See PROGRESS.md.
    """
    i = rep_len - 3
    # The pre-search game history is stored one entry per *our* move with a
    # placeholder between, so a halfmove clock of h spans up to 2h entries.
    limit = rep_len - 1 - 2 * halfmove
    if limit < 0:
        limit = 0
    while i >= limit:
        if rep_hist[i] == key:
            return True
        i -= 2
    return False


# =============================================================================
# Move ordering
# =============================================================================
@njit(cache=False)
def score_moves(bb, occ, mail, st, mv, n, out, tt_move, killers, history,
                counter, ply, prev_piece, prev_to):
    cm = np.int32(0)
    if prev_piece >= 0:
        cm = counter[prev_piece][prev_to]
    k0 = killers[ply][0]
    k1 = killers[ply][1]
    for i in range(n):
        m = mv[i]
        if m == tt_move:
            out[i] = np.int64(1) << 40
            continue
        cap = m_captured(m)
        promo = m_promo(m)
        if promo == 4:
            out[i] = np.int64(900000) + (np.int64(1) << 20)
        elif cap != EMPTY or m_is_ep(m):
            victim = 0 if m_is_ep(m) else np.int64(cap) % 6
            attacker = np.int64(m_piece(m)) % 6
            out[i] = np.int64(800000) + SEE_VALUE[victim] * 16 - SEE_VALUE[attacker]
        elif promo != 0:
            out[i] = np.int64(700000) + promo
        elif m == k0:
            out[i] = np.int64(600000)
        elif m == k1:
            out[i] = np.int64(590000)
        elif m == cm:
            out[i] = np.int64(580000)
        else:
            out[i] = history[m_piece(m)][m_to(m)]


@njit(cache=False)
def score_moves_q(mv, n, out):
    """Quiescence ordering: pure MVV-LVA. No killers or history here -- the
    node count is dominated by captures and allocating heuristic tables per
    node would cost far more than the ordering gains."""
    for i in range(n):
        m = mv[i]
        promo = m_promo(m)
        cap = m_captured(m)
        if promo == 4:
            out[i] = np.int64(900000)
        elif cap != EMPTY or m_is_ep(m):
            victim = np.int64(0) if m_is_ep(m) else np.int64(cap) % 6
            attacker = np.int64(m_piece(m)) % 6
            out[i] = np.int64(800000) + SEE_VALUE[victim] * 16 - SEE_VALUE[attacker]
        else:
            out[i] = np.int64(0)


@njit(cache=False, inline='always')
def pick_best(mv, sc, n, start):
    """Selection sort one element at a time: most nodes fail high early, so
    fully sorting the list would be wasted work."""
    best = start
    for j in range(start + 1, n):
        if sc[j] > sc[best]:
            best = j
    if best != start:
        mv[start], mv[best] = mv[best], mv[start]
        sc[start], sc[best] = sc[best], sc[start]
    return mv[start]


# =============================================================================
# Quiescence
# =============================================================================
@njit(cache=False)
def qsearch(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
            alpha, beta, ply, info, ctrl):
    info[1] += 1
    if (info[1] & 2047) == 0:
        with objmode(now='float64'):
            now = time.time()
        if now >= ctrl[0]:
            info[2] = 1
    if info[2] != 0:
        return np.int64(0)
    if ply >= MAX_QS_PLY:
        return evaluate(bb, occ, mail, st)

    checked = in_check(bb, occ, st)
    best = -INF
    if not checked:
        best = evaluate(bb, occ, mail, st)
        if best >= beta:
            return best
        if best > alpha:
            alpha = best

    n = gen_moves(bb, occ, mail, st, moves[ply], not checked)
    if n == 0:
        if checked:
            return -MATE + ply
        return best

    score_moves_q(moves[ply], n, mscores[ply])

    for i in range(n):
        m = pick_best(moves[ply], mscores[ply], n, i)
        cap = m_captured(m)
        if not checked and (cap != EMPTY or m_is_ep(m)):
            # delta pruning: even winning this piece outright would not raise alpha
            victim = np.int64(0) if m_is_ep(m) else np.int64(cap) % 6
            if best + SEE_VALUE[victim] + 200 < alpha and m_promo(m) == 0:
                continue
            if see(bb, occ, mail, np.int64(m_from(m)), np.int64(m_to(m)), st[0]) < 0:
                continue
        make_move(bb, occ, mail, st, hsh, undo, undo_h, ply, m)
        v = -qsearch(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                     -beta, -alpha, ply + 1, info, ctrl)
        unmake_move(bb, occ, mail, st, hsh, undo, undo_h, ply, m)
        if info[2] != 0:
            return np.int64(0)
        if v > best:
            best = v
            if v > alpha:
                alpha = v
                if v >= beta:
                    break
    return best


# =============================================================================
# Main search
# =============================================================================
@njit(cache=False)
def negamax(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
            tt_key, tt_data, killers, history, counter, rep_hist,
            depth, alpha, beta, ply, is_pv, prev_piece, prev_to,
            info, ctrl):
    info[1] += 1
    if (info[1] & 2047) == 0:
        with objmode(now='float64'):
            now = time.time()
        if now >= ctrl[0]:
            info[2] = 1
    if info[2] != 0:
        return np.int64(0)

    if ply > info[3]:
        info[3] = ply

    # Hard ply cap. Check extensions can lengthen a forcing line indefinitely,
    # and the move/undo stacks are fixed size with numba bounds checking off,
    # so overrunning them would corrupt memory rather than raise.
    if ply >= MAX_SEARCH_PLY:
        return evaluate(bb, occ, mail, st)

    root = (ply == 0)

    if not root:
        # draws
        if st[3] >= 100:
            return np.int64(0)
        if is_repetition(rep_hist, info[0], hsh[0], st[3]):
            return np.int64(0)
        # mate distance pruning
        if alpha < -MATE + ply:
            alpha = -MATE + ply
        if beta > MATE - ply - 1:
            beta = MATE - ply - 1
        if alpha >= beta:
            return alpha

    checked = in_check(bb, occ, st)
    if checked:
        depth += 1                     # check extension

    if depth <= 0:
        return qsearch(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                       alpha, beta, ply, info, ctrl)

    # --- transposition probe -------------------------------------------------
    idx = np.int64(hsh[0] & TT_MASK)
    tt_move = np.int32(0)
    if tt_key[idx] == hsh[0]:
        data = tt_data[idx]
        tt_move = tt_unpack_move(data)
        if not root and tt_unpack_depth(data) >= depth:
            s = tt_unpack_score(data)
            if s > MATE_IN_MAX:
                s -= ply
            elif s < -MATE_IN_MAX:
                s += ply
            f = tt_unpack_flag(data)
            if f == FLAG_EXACT:
                return s
            if f == FLAG_LOWER and s >= beta:
                return s
            if f == FLAG_UPPER and s <= alpha:
                return s

    static = evaluate(bb, occ, mail, st) if not checked else np.int64(-INF)

    # --- whole-node pruning --------------------------------------------------
    if not is_pv and not checked and abs(beta) < MATE_IN_MAX:
        # reverse futility: we are so far ahead that giving back a margin still fails high
        if depth <= 7 and static - 85 * depth >= beta:
            return static
        # razoring: so far behind that only a tactical shot saves us
        if depth <= 3 and static + 180 * depth < alpha:
            v = qsearch(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                        alpha, beta, ply, info, ctrl)
            if v < alpha:
                return v
        # null move: give the opponent a free move; if we are still winning, cut
        side = st[0]
        base = np.int64(0) if side == WHITE else np.int64(6)
        big_material = (bb[base + 1] | bb[base + 2] | bb[base + 3] | bb[base + 4])
        if depth >= 3 and static >= beta and big_material != 0:
            r = 3 + depth // 4
            if r > depth - 1:
                r = depth - 1
            make_null(st, hsh, undo, undo_h, ply)
            rep_hist[info[0]] = hsh[0]
            info[0] += 1
            v = -negamax(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                         tt_key, tt_data, killers, history, counter, rep_hist,
                         depth - 1 - r, -beta, -beta + 1, ply + 1, False,
                         np.int64(-1), np.int64(0), info, ctrl)
            info[0] -= 1
            unmake_null(st, hsh, undo, undo_h, ply)
            if info[2] != 0:
                return np.int64(0)
            if v >= beta:
                if v > MATE_IN_MAX:
                    v = beta
                return v

    # --- internal iterative reduction ---------------------------------------
    if tt_move == 0 and depth >= 5 and is_pv:
        depth -= 1

    n = gen_moves(bb, occ, mail, st, moves[ply], False)
    if n == 0:
        if checked:
            return -MATE + ply
        return np.int64(0)

    score_moves(bb, occ, mail, st, moves[ply], n, mscores[ply], tt_move,
                killers, history, counter, ply, prev_piece, prev_to)

    best = -INF
    best_move = np.int32(0)
    orig_alpha = alpha
    quiets_tried = 0

    for i in range(n):
        m = pick_best(moves[ply], mscores[ply], n, i)
        is_cap = (m_captured(m) != EMPTY) or m_is_ep(m)
        is_quiet = (not is_cap) and m_promo(m) == 0

        # --- move-level pruning on quiet moves -------------------------------
        if not root and is_quiet and best > -MATE_IN_MAX and not checked:
            if depth <= 6 and static + 110 + 105 * depth <= alpha:
                continue
            if depth <= 4 and quiets_tried > 4 + depth * depth:
                continue
        if not root and is_cap and depth <= 5 and best > -MATE_IN_MAX and not checked:
            if see(bb, occ, mail, np.int64(m_from(m)), np.int64(m_to(m)), st[0]) < -60 * depth:
                continue

        if is_quiet:
            quiets_tried += 1

        make_move(bb, occ, mail, st, hsh, undo, undo_h, ply, m)
        rep_hist[info[0]] = hsh[0]
        info[0] += 1

        # --- late move reductions --------------------------------------------
        new_depth = depth - 1
        v = np.int64(0)
        if i == 0:
            v = -negamax(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                         tt_key, tt_data, killers, history, counter, rep_hist,
                         new_depth, -beta, -alpha, ply + 1, is_pv,
                         np.int64(m_piece(m)), np.int64(m_to(m)), info, ctrl)
        else:
            r = np.int64(0)
            if is_quiet and depth >= 3 and i >= 3:
                di = depth if depth < 63 else 63
                mi = i if i < 63 else 63
                r = LMR[di][mi]
                if is_pv:
                    r -= 1
                sc = mscores[ply][i]
                if sc >= 580000:      # killer or counter-move
                    r -= 1
                elif sc < -4000:      # bad combined history
                    r += 1
                elif sc > 4000:       # good history
                    r -= 1
                if r < 0:
                    r = 0
                if r > new_depth - 1:
                    r = new_depth - 1
            v = -negamax(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                         tt_key, tt_data, killers, history, counter, rep_hist,
                         new_depth - r, -alpha - 1, -alpha, ply + 1, False,
                         np.int64(m_piece(m)), np.int64(m_to(m)), info, ctrl)
            if v > alpha and r > 0:
                v = -negamax(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                             tt_key, tt_data, killers, history, counter, rep_hist,
                             new_depth, -alpha - 1, -alpha, ply + 1, False,
                             np.int64(m_piece(m)), np.int64(m_to(m)), info, ctrl)
            if v > alpha and v < beta:
                v = -negamax(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                             tt_key, tt_data, killers, history, counter, rep_hist,
                             new_depth, -beta, -alpha, ply + 1, True,
                             np.int64(m_piece(m)), np.int64(m_to(m)), info, ctrl)

        info[0] -= 1
        unmake_move(bb, occ, mail, st, hsh, undo, undo_h, ply, m)
        if info[2] != 0:
            return np.int64(0)

        if v > best:
            best = v
            best_move = m
            if v > alpha:
                alpha = v
                if v >= beta:
                    if is_quiet:
                        if killers[ply][0] != m:
                            killers[ply][1] = killers[ply][0]
                            killers[ply][0] = m
                        bonus = depth * depth
                        h = history[m_piece(m)][m_to(m)] + bonus
                        if h > 16384:
                            h = 16384
                        history[m_piece(m)][m_to(m)] = h
                        if prev_piece >= 0:
                            counter[prev_piece][prev_to] = m
                        # penalise the quiet moves that were tried and failed
                        for j in range(i):
                            pm = moves[ply][j]
                            if (m_captured(pm) == EMPTY and not m_is_ep(pm)
                                    and m_promo(pm) == 0):
                                ph = history[m_piece(pm)][m_to(pm)] - bonus
                                if ph < -16384:
                                    ph = -16384
                                history[m_piece(pm)][m_to(pm)] = ph
                    break

    # --- store ---------------------------------------------------------------
    if info[2] == 0:
        flag = FLAG_EXACT
        if best <= orig_alpha:
            flag = FLAG_UPPER
        elif best >= beta:
            flag = FLAG_LOWER
        s = best
        if s > MATE_IN_MAX:
            s += ply
        elif s < -MATE_IN_MAX:
            s -= ply
        if tt_key[idx] != hsh[0] or depth >= tt_unpack_depth(tt_data[idx]) - 2:
            tt_key[idx] = hsh[0]
            tt_data[idx] = tt_pack(best_move, s, depth, flag)
    return best


# =============================================================================
# Iterative deepening root
#
# Runs entirely inside compiled code. Returns via `info`:
#   info[0] repetition-history length   info[1] nodes
#   info[2] stop flag                   info[3] seldepth
#   info[4] best move                   info[5] best score
#   info[6] depth completed
# ctrl[0] is the hard deadline (wall clock), ctrl[1] the soft one: we only
# begin another iteration if there is a realistic chance of finishing it.
# =============================================================================
@njit(cache=False)
def search_root(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                tt_key, tt_data, killers, history, counter, rep_hist,
                max_depth, info, ctrl):
    info[1] = 0
    info[2] = 0
    info[3] = 0
    info[4] = 0
    info[5] = 0
    info[6] = 0

    # decay history between moves rather than clearing: ordering from the
    # previous search is still mostly valid one move later
    for a in range(12):
        for b in range(64):
            history[a][b] = history[a][b] // 4
    for a in range(160):
        killers[a][0] = 0
        killers[a][1] = 0

    n = gen_moves(bb, occ, mail, st, moves[0], False)
    if n == 0:
        return np.int64(0)
    info[4] = np.int64(moves[0][0])

    score = np.int64(0)
    prev_best = np.int64(0)
    unstable = 0
    for depth in range(1, max_depth + 1):
        if depth <= 4:
            v = negamax(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                        tt_key, tt_data, killers, history, counter, rep_hist,
                        depth, -INF, INF, 0, True, np.int64(-1), np.int64(0),
                        info, ctrl)
        else:
            # aspiration window around the previous score, widened on failure
            window = np.int64(18)
            while True:
                a = score - window
                b = score + window
                if a < -INF:
                    a = -INF
                if b > INF:
                    b = INF
                v = negamax(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                            tt_key, tt_data, killers, history, counter, rep_hist,
                            depth, a, b, 0, True, np.int64(-1), np.int64(0),
                            info, ctrl)
                if info[2] != 0:
                    break
                if v <= a:
                    window *= 3
                elif v >= b:
                    window *= 3
                else:
                    break
                if window > 1200:
                    v = negamax(bb, occ, mail, st, hsh, undo, undo_h, moves, mscores,
                                tt_key, tt_data, killers, history, counter, rep_hist,
                                depth, -INF, INF, 0, True, np.int64(-1), np.int64(0),
                                info, ctrl)
                    break

        if info[2] != 0:
            break

        idx = np.int64(hsh[0] & TT_MASK)
        if tt_key[idx] == hsh[0]:
            mv = tt_unpack_move(tt_data[idx])
            if mv != 0:
                info[4] = np.int64(mv)
        if info[4] != prev_best and depth > 4:
            unstable = 2          # best move just changed: think a little longer
        elif unstable > 0:
            unstable -= 1
        prev_best = info[4]
        score = v
        info[5] = v
        info[6] = depth

        # a forced mate is found; no deeper search can improve on it
        if v > MATE_IN_MAX or v < -MATE_IN_MAX:
            break

        with objmode(now='float64'):
            now = time.time()
        limit = ctrl[1]
        if unstable > 0:
            limit = ctrl[1] + 0.6 * (ctrl[0] - ctrl[1])
        if now >= limit:
            break

    return score
