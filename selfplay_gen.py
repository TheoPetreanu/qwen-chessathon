"""Self-play data generator for Texel tuning.

Plays engine-vs-engine games from the balanced openings (both colours), and
samples quiet positions along the way (not in check, not immediately after a
capture, clear of the opening and the very end of the game), tagging each with
the eventual game result from White's point of view. Output is a plain text
file, one "<fen> <result>" per line, result in {1.0, 0.5, 0.0}.

Not part of the shipped build -- offline data generation only.
"""
import sys, os, time, json, subprocess, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
import chess
import arena
from openings import BALANCED

BASE_MS = 600
INC_MS = 30
SAMPLE_EVERY = 4
SKIP_OPENING_PLIES = 10
SKIP_ENDGAME_PLIES = 6
RANDOM_PLIES = 4        # random legal moves played before the engines take
                        # over, so replaying the same 12 openings doesn't just
                        # reproduce near-identical games each time


def play_and_sample(white, black, start_fen, rng):
    board = chess.Board(start_fen)
    for _ in range(RANDOM_PLIES):
        if board.is_game_over():
            break
        legal = list(board.legal_moves)
        board.push(rng.choice(legal))
    clock = {chess.WHITE: BASE_MS, chess.BLACK: BASE_MS}
    engines = {chess.WHITE: white, chess.BLACK: black}
    fens = []
    while True:
        if board.is_game_over(claim_draw=True) or board.ply() >= 300:
            break
        side = board.turn
        eng = engines[side]
        t0 = time.time()
        try:
            resp = eng.move(board.fen(), int(clock[side]))
        except Exception as e:
            return None, fens
        elapsed = (time.time() - t0) * 1000.0
        clock[side] -= elapsed
        if clock[side] < 0:
            return None, fens
        clock[side] += INC_MS
        if "error" in resp:
            return None, fens
        try:
            mv = chess.Move.from_uci(resp["move"])
        except Exception:
            return None, fens
        if mv not in board.legal_moves:
            return None, fens
        is_cap = board.is_capture(mv)
        if (not board.is_check()) and (not is_cap) and board.ply() >= SKIP_OPENING_PLIES \
                and board.ply() % SAMPLE_EVERY == 0:
            fens.append(board.fen())
        board.push(mv)
        if verbose:
            pass
    if not board.is_game_over(claim_draw=True):
        return None, fens
    r = board.result(claim_draw=True)
    result = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[r]
    # drop the samples too close to the end (position no longer representative
    # of the "opinion" that produced the final result)
    fens = fens[:max(0, len(fens) - SKIP_ENDGAME_PLIES // SAMPLE_EVERY)]
    return result, fens


verbose = False


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "tools/texel_data.txt"
    replicates = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    A = arena.Engine("engine", "agent")
    B = arena.Engine("engine", "agent")
    samples = []
    game_no = 0
    try:
        for rep in range(replicates):
            for i, fen in enumerate(BALANCED):
                for a_is_white in (True, False):
                    rng = random.Random("%d-%d-%s" % (rep, i, a_is_white))
                    white, black = (A, B) if a_is_white else (B, A)
                    result, fens = play_and_sample(white, black, fen, rng)
                    game_no += 1
                    if result is None:
                        print("game %d skipped (anomaly)" % game_no, flush=True)
                        continue
                    # result is from White's POV regardless of which engine played White
                    for f in fens:
                        samples.append((f, result))
                    print("game %3d  rep=%d opening=%-20s result=%.1f  samples=%d  total=%d" %
                          (game_no, rep, fen[:20], result, len(fens),
                           len(samples)), flush=True)
    finally:
        A.close(); B.close()

    with open(out_path, "w") as f:
        for fen, result in samples:
            f.write("%s\t%.1f\n" % (fen, result))
    print("wrote", len(samples), "samples to", out_path)


if __name__ == "__main__":
    main()
