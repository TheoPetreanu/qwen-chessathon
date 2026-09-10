# Absolute rating anchor — decided, do not re-investigate

Theo has confirmed: **Stockfish is NOT installed on this machine, and nothing
is to be downloaded or installed.**

Task 4 in TASK2.md is therefore CLOSED. Do not scan the filesystem for engine
binaries again, and do not install one. A full-disk scan during a timed match
also corrupts the match timing.

Consequence to state plainly in PROGRESS.md: every Elo figure produced here is
RELATIVE to baseline/agent.py, whose absolute strength is undefined. We do not
know where this engine sits on any external scale, and no offline test
available on this machine can tell us. The only way to get a real number is to
submit and read the competition rating.
