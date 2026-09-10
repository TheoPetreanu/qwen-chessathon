"""Replay a real game up to a chosen ply WITH its true repetition history, then
ask the engine for a move.

A bare FEN cannot encode "this position has already occurred twice", so
tools/conversion_test.epd cannot test the repetition failure at all -- Stockfish
and our engine both see a winning position with no history attached. This
harness reconstructs the actual ply-by-ply history into agent._HIST (the same
representation get_move builds), so the engine faces the position exactly as it
did in the game.

POST-HOC DIAGNOSTIC ONLY. Do not run while a gauntlet match is live.

Usage:
    .venv\\Scripts\\python.exe tools\\repetition_replay.py <engine_dir> <pgn> <ply> [--ms 20000]
"""
import argparse, os, sys
import numpy as np
import chess, chess.pgn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("engine_dir")
    ap.add_argument("pgn")
    ap.add_argument("ply", type=int, help="1-based ply of the move to reconsider")
    ap.add_argument("--ms", type=float, default=20000.0)
    ap.add_argument("--warm", action="store_true",
                    help="feed every earlier position of OUR side first, so the "
                         "TT/killers/history accumulate as they did in the game")
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", a.engine_dir))
    import agent
    from ca_position import new_position, from_board

    bb, occ, mail, st, hsh = new_position()

    def key_of(board):
        # same convention agent uses: round-trip through the FEN the referee sends
        from_board(chess.Board(board.fen()), bb, occ, mail, st, hsh)
        return np.uint64(hsh[0])

    g = chess.pgn.read_game(open(a.pgn))
    moves = [n.move for n in g.mainline()]
    board = g.board()

    # positions at plies 0 .. ply-1 (everything BEFORE the move under test)
    hist = [key_of(board)]
    for m in moves[:a.ply - 1]:
        board.push(m)
        hist.append(key_of(board))
    played_san = board.san(moves[a.ply - 1])

    # which legal moves here would hand the referee a threefold?
    drawing = []
    for mv in board.legal_moves:
        board.push(mv)
        if board.is_repetition(3):
            drawing.append(board.san(board.pop()) if False else None)
            board.pop()
            # recompute san on the pre-move board
            drawing[-1] = board.san(mv)
        else:
            board.pop()

    # Optionally reproduce the in-game engine state. A single cold call has an
    # empty transposition table; in the real game the TT had been accumulating
    # for dozens of moves, and with repetition blindness it can hold scores that
    # treat a repeating line as won. Feed our earlier turns so that state builds
    # up, discarding the moves it picks (we then continue from the real game).
    if a.warm:
        rb = g.board()
        stm_target = (a.ply - 1) % 2      # 0 => white to move at the target ply
        for i, m in enumerate(moves[:a.ply - 1]):
            if i % 2 == stm_target:
                agent.get_move(rb.fen(), a.ms)
            rb.push(m)

    # hand the engine the true history: get_move appends the CURRENT position
    # itself, so seed with everything strictly before it
    if hasattr(agent, "_HIST"):
        agent._HIST[:] = hist[:-1]
        which = "_HIST (ply-by-ply)"
    else:
        # older builds: only our own turns, placeholders between
        agent._SEEN[:] = [k for i, k in enumerate(hist[:-1]) if i % 2 == (a.ply - 1) % 2]
        which = "_SEEN (our turns only)"
    agent._LAST_PIECES[0] = len(board.piece_map())

    uci = agent.get_move(board.fen(), a.ms)
    mv = chess.Move.from_uci(uci)
    san = board.san(mv) if mv in board.legal_moves else "ILLEGAL"
    board.push(mv)
    made_threefold = board.is_repetition(3)

    print("engine_dir      : %s   (%s, %d prior plies seeded)" % (a.engine_dir, which, len(hist) - 1))
    print("game            : %s  ply %d" % (os.path.basename(a.pgn), a.ply))
    print("played in game  : %s" % played_san)
    print("moves that draw : %s" % (", ".join(drawing) if drawing else "(none)"))
    print("engine plays    : %s   -> threefold? %s" % (san, made_threefold))
    print("VERDICT         : %s" % ("*** WALKS INTO THE DRAW ***" if made_threefold
                                    else "avoids the repetition"))


if __name__ == "__main__":
    main()
