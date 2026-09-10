"""Precompute our OWN opening replies for the competition's start-position pool.

Every rated game begins from one of a finite set of curated FENs (measured: 307
positions, Chao1 also 307, i.e. fully enumerated -- see tools/fetch_games.py).
Engine play from them is highly convergent, so storing the top-N opponent
replies keeps us in book for most games well past the opening:

    replies stored | our move 1     2     3     4     5     6
    top-1          |       100%   72%   61%   57%   55%   54%
    top-2          |       100%   91%   88%   87%   86%   86%
    top-3          |       100%   97%   96%   96%   96%   96%

Our first six moves cost 42.9s of a 120s clock in real games, and every one of
our seven losses finished under 10s, so handing that clock back to the endgame
is the point. A stored move is also searched far longer than the ~6s we can
afford at the board.

Everything here is our own engine's analysis of public FENs. No third-party
book is involved -- generic polyglot books were tested and cover these
positions barely at all (PROGRESS.md).

Targets come from REAL game paths in the harvested PGNs, not a synthetic
expansion, so compute is spent only on positions that actually occur.

Do NOT run while a match is live (rule 4). Resumable: results append to a
JSONL cache, so re-running skips work already done and rebuilds the module.

Usage:
    .venv\\Scripts\\python.exe tools\\build_book.py --depth 6 --topm 3 --ms 15000
"""
import argparse, glob, io, json, logging, os, sys, time
import multiprocessing as mp

logging.disable(logging.CRITICAL)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_ENGINE = None


def _init(engine_dir):
    """Each worker owns one engine process; numba JIT is paid once per worker."""
    global _ENGINE
    sys.path.insert(0, engine_dir)
    import agent
    _ENGINE = agent


def _search(args):
    """(key, fen, ms) -> (key, uci) or (key, None)."""
    key, fen, ms = args
    import chess, numpy as np, time as _t
    from ca_search import search_root
    from ca_position import MAX_PLY, move_to_uci
    a = _ENGINE
    try:
        b = chess.Board(fen)
        if b.is_game_over():
            return key, None
        a._sync_position(b)
        a._REP[0] = np.uint64(a._HSH[0])
        a._INFO[0] = 1
        now = _t.time()
        a._CTRL[0] = now + ms / 1000.0
        a._CTRL[1] = now + ms / 1000.0
        search_root(a._BB, a._OCC, a._MAIL, a._ST, a._HSH, a._UNDO, a._UNDO_H,
                    a._MOVES, a._MSCORES, a._TT_KEY, a._TT_DATA, a._KILLERS,
                    a._HISTORY, a._COUNTER, a._REP, MAX_PLY - 8, a._INFO, a._CTRL)
        uci = move_to_uci(np.int32(a._INFO[4]))
        mv = chess.Move.from_uci(uci)
        if mv not in b.legal_moves:          # never store an illegal move
            return key, None
        return key, uci
    except Exception:
        return key, None


def targets(pgn_dirs, depth, topm):
    """Positions where WE would need a stored answer, walking only real games."""
    import chess, chess.pgn, collections
    games = []
    skipped = 0
    for d in pgn_dirs:
        for p in glob.glob(os.path.join(d, "*.pgn")):
            try:
                g = chess.pgn.read_game(io.StringIO(open(p).read()))
            except Exception:
                # A harvested PGN can be truncated mid-move when the source
                # page's fallback 8000-char cutoff lands before any result
                # token (see fetch_games.py, game_pgn()) -- rare (~0.03% of a
                # 14k-file harvest) but fatal to the parser if not caught here.
                skipped += 1
                continue
            if g and g.headers.get("FEN"):
                mvs = [n.move for n in g.mainline()]
                if len(mvs) >= 4:
                    games.append((g.headers["FEN"], mvs))
    if skipped:
        print("  (skipped %d unparseable PGNs)" % skipped, flush=True)
    freq = collections.defaultdict(collections.Counter)
    for fen, mvs in games:
        b = chess.Board(fen)
        for m in mvs[:2 * depth + 4]:
            freq[b.board_fen() + (" w" if b.turn else " b")][m.uci()] += 1
            b.push(m)
    # Record the SHALLOWEST depth at which each position occurs, and how often.
    # Order matters: a run that is cut short must still have complete coverage
    # of the early moves, which are hit in ~100% of games, rather than an
    # arbitrary alphabetical slice spread thinly across all depths.
    # BOTH colours. A pooled position has one side to move; when we are that
    # side we move first (our plies are even), and when we are the other colour
    # the opponent moves first and our plies are odd. Generating only the even
    # parity -- as an earlier version did -- silently halves real coverage to
    # ~48% of games while appearing to cover 96%, because the 96% figure is
    # conditional on having the first move.
    need, meta = {}, {}
    for fen, mvs in games:
        for parity in (0, 1):
            b = chess.Board(fen); ours = 0
            for i, m in enumerate(mvs):
                if ours >= depth:
                    break
                k = b.board_fen() + (" w" if b.turn else " b")
                if i % 2 == parity:
                    full = b.fen()
                    key = " ".join(full.split()[:4])
                    need[key] = full
                    d, c = meta.get(key, (99, 0))
                    meta[key] = (min(d, ours + 1), c + 1)
                    ours += 1
                else:
                    if m.uci() not in [u for u, _ in freq[k].most_common(topm)]:
                        break
                b.push(m)
    return need, meta, len(games)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default=os.path.join(ROOT, "checkpoints", "openingcap"))
    ap.add_argument("--pgn-dirs", nargs="*",
                    default=[os.path.join(ROOT, "tools", "pgns_public"),
                             os.path.join(ROOT, "tools", "pgns")])
    ap.add_argument("--depth", type=int, default=6, help="how many of OUR moves deep")
    ap.add_argument("--topm", type=int, default=3, help="opponent replies covered")
    ap.add_argument("--ms", type=int, default=15000)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--cache", default=os.path.join(ROOT, "tools", "book_cache.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "engine", "ca_book.py"))
    ap.add_argument("--budget-h", type=float, default=0.0, help="stop after N hours")
    args = ap.parse_args()

    need, meta, ngames = targets(args.pgn_dirs, args.depth, args.topm)
    done = {}
    if os.path.exists(args.cache):
        for ln in open(args.cache):
            try:
                r = json.loads(ln)
                done[r["k"]] = r["m"]
            except Exception:
                pass
    # shallowest first, and within a depth the most frequently occurring first,
    # so an interrupted run still yields a coherent, maximally useful book
    order = sorted(need, key=lambda k: (meta[k][0], -meta[k][1], k))
    todo = [(k, need[k], args.ms) for k in order if k not in done]
    bydepth = {}
    for k in need:
        bydepth[meta[k][0]] = bydepth.get(meta[k][0], 0) + 1
    print("games=%d  targets=%d  cached=%d  todo=%d  workers=%d  %dms each"
          % (ngames, len(need), len(done), len(todo), args.workers, args.ms), flush=True)
    print("targets by our-move depth: "
          + "  ".join("d%d=%d" % (d, bydepth[d]) for d in sorted(bydepth)), flush=True)
    est = len(todo) * args.ms / 1000.0 / max(args.workers, 1) / 3600.0
    print("estimated %.1f h (before contention)" % est, flush=True)

    t0 = time.time()
    if todo:
        cache = open(args.cache, "a")
        with mp.Pool(args.workers, initializer=_init, initargs=(args.engine,)) as pool:
            for i, (k, uci) in enumerate(pool.imap_unordered(_search, todo, chunksize=1)):
                if uci:
                    done[k] = uci
                    cache.write(json.dumps({"k": k, "m": uci}) + "\n"); cache.flush()
                if (i + 1) % 25 == 0:
                    el = time.time() - t0
                    print("  %5d/%d  %.2f h elapsed, ~%.2f h left  (%d stored)"
                          % (i + 1, len(todo), el / 3600.0,
                             (el / (i + 1)) * (len(todo) - i - 1) / 3600.0, len(done)),
                          flush=True)
                if args.budget_h and (time.time() - t0) / 3600.0 > args.budget_h:
                    print("  budget reached, stopping early", flush=True)
                    pool.terminate(); break
        cache.close()

    with open(args.out, "w") as fh:
        fh.write('"""Precomputed opening replies for the competition start-position pool.\n\n'
                 'Generated by tools/build_book.py: depth=%d of our moves, top-%d opponent\n'
                 'replies, %d ms of OUR engine per position. Keys are the raw first four\n'
                 'FEN fields exactly as the referee sends them -- deliberately not\n'
                 'round-tripped through python-chess, whose ep_square is set after any\n'
                 'double push while the referee emits the field only when the capture is\n'
                 'legal. Any miss falls through to normal search.\n"""\n\n'
                 % (args.depth, args.topm, args.ms))
        fh.write("BOOK = {\n")
        for k in sorted(done):
            fh.write('    "%s": "%s",\n' % (k, done[k]))
        fh.write("}\n")
    print("\nwrote %s: %d entries, %.1f KB, %.2f h"
          % (args.out, len(done), os.path.getsize(args.out) / 1024.0,
             (time.time() - t0) / 3600.0))


if __name__ == "__main__":
    mp.freeze_support()
    main()
