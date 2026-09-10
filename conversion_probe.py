"""Phase 2 probe: does our engine still throw the won positions it drew?

For each EPD in tools/conversion_test.epd, ask a given engine build for its move
at a realistic competition budget, then score the position before and after with
the local Stockfish. Reports the eval delta, so "keeps it winning" vs "throws it"
is a number, not an opinion.

POST-HOC DIAGNOSTIC ONLY. Do not run while a gauntlet match is live.

Usage:
    .venv\\Scripts\\python.exe tools\\conversion_probe.py <engine_dir> [--depth 20] [--ms 120000]
"""
import argparse, glob, os, sys
import chess, chess.engine


def find_sf():
    for p in ["tools/stockfish/*stockfish*", "tools/stockfish/*.exe",
              "tools/stockfish/**/*stockfish*"]:
        for hit in glob.glob(p, recursive=True):
            if os.path.isfile(hit):
                return hit
    sys.exit("Stockfish not found")


def cp(score, pov):
    s = score.pov(pov)
    if s.is_mate():
        m = s.mate()
        return (10000 - abs(m) * 10) * (1 if m > 0 else -1)
    return s.score()


def parse_epd(path):
    out = []
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fen_part = line.split(" bm ")[0].strip()
        bm = line.split(" bm ")[1].split(";")[0].strip() if " bm " in line else "?"
        ident = line.split('id "')[1].split('"')[0] if 'id "' in line else "?"
        note = line.split('c0 "')[1].split('"')[0] if 'c0 "' in line else ""
        board = chess.Board(fen_part + " 0 1")
        out.append((board, bm, ident, note))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("engine_dir")
    ap.add_argument("--depth", type=int, default=20)
    ap.add_argument("--ms", type=float, default=120000.0)
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", a.engine_dir))
    import agent

    sf = chess.engine.SimpleEngine.popen_uci(find_sf())
    sf.configure({"Threads": 4, "Hash": 512})
    lim = chess.engine.Limit(depth=a.depth)

    print("engine_dir: %s   budget=%.0fms   sf depth=%d\n" % (a.engine_dir, a.ms, a.depth))
    for board, bm, ident, note in parse_epd("tools/conversion_test.epd"):
        us = board.turn
        before = cp(sf.analyse(board, lim)["score"], us)
        uci = agent.get_move(board.fen(), a.ms)
        mv = chess.Move.from_uci(uci)
        legal = mv in board.legal_moves
        san = board.san(mv) if legal else "ILLEGAL"
        board.push(mv)
        after = cp(sf.analyse(board, lim)["score"], us)
        delta = after - before
        flag = "KEEPS IT" if delta > -100 else ("THROWS IT" if delta < -400 else "leaks")
        print("%-18s bm=%-6s played=%-7s  %+6d -> %+6d  (%+d)  %s"
              % (ident, bm, san, before, after, delta, flag))
        if note:
            print("%-18s   was: %s" % ("", note))
    sf.quit()


if __name__ == "__main__":
    main()
