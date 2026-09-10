"""One-off: measure how many full moves self-play games actually last, to sanity
check MOVES_TO_GO in engine/agent.py against real game lengths rather than a
guess. Not part of the shipped build.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
import arena
from openings import BALANCED

A = arena.Engine("engine", "agent")
B = arena.Engine("engine", "agent")

lengths = []
for i, fen in enumerate(BALANCED):
    for a_is_white in (True, False):
        white, black = (A, B) if a_is_white else (B, A)
        res, why, board = arena.play(white, black, fen, base_ms=3000, inc_ms=30)
        n = board.fullmove_number
        lengths.append(n)
        print("game %2d  %-12s result=%-8s reason=%-8s fullmoves=%d" %
              (len(lengths), fen[:20], res, why, n), flush=True)

A.close(); B.close()

lengths.sort()
n = len(lengths)
print("\n=== SUMMARY ===")
print("games:", n)
print("mean fullmoves:", sum(lengths) / n)
print("median:", lengths[n // 2])
print("min/max:", lengths[0], lengths[-1])
print("all:", lengths)
