"""One-off: measure nodes/sec for a given engine/ (or checkpoints/<x>/) copy
via agent.get_move, on a small fixed FEN suite.

Run this OUTSIDE any timed match -- never while tests/gauntlet.py has a match
in progress, since that would contend for CPU and distort both this
measurement and the match's own timing (METHODOLOGY.md rule: nothing else
CPU-heavy while a match runs). Not part of the shipped build.

Usage:
    .venv\\Scripts\\python.exe tools\\measure_nps.py [engine_dir]

engine_dir defaults to "engine"; pass e.g. "checkpoints/item2" to measure a
specific snapshot instead. Each FEN gets a generous fixed time_left_ms so the
_think_time formula in agent.py hands the search a comparable multi-second
budget regardless of which copy is loaded (all copies share the same formula
and DEFAULT_INC_MS unless a candidate deliberately changed it).
"""
import sys, os, time

engine_dir = sys.argv[1] if len(sys.argv) > 1 else "engine"
root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(root, "..", engine_dir))

import agent

TIME_LEFT_MS = 60000.0

# Same FENs as tests/test_perft.py's SUITE (name, fen), inlined here rather
# than imported so this tool never fights test_perft.py's own hardcoded
# 'engine'/'../engine' sys.path inserts over which engine_dir we actually want.
SUITE = [
    ("startpos", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
    ("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"),
    ("position3", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"),
    ("position4", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"),
    ("position5", "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"),
    ("position6", "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10"),
]


def main():
    print("engine_dir:", engine_dir)
    total_nodes = 0
    total_elapsed = 0.0
    for name, fen in SUITE:
        t0 = time.time()
        agent.get_move(fen, TIME_LEFT_MS)
        dt = time.time() - t0
        nodes = int(agent._INFO[1])
        total_nodes += nodes
        total_elapsed += dt
        print("  %-11s nodes=%9d  time=%5.2fs  %.3f Mnps"
              % (name, nodes, dt, nodes / dt / 1e6))
    print("\n=== TOTAL ===")
    print("%d nodes in %.2fs = %.3f Mnps" %
          (total_nodes, total_elapsed, total_nodes / total_elapsed / 1e6))


if __name__ == "__main__":
    main()
