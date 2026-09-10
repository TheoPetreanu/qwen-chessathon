"""
ACPL / per-move diagnostic for AI Chessathon games ("Endgame" team).

Scores every completed game from Endgame's point of view with the local
Stockfish sparring binary. POST-HOC DIAGNOSTIC ONLY -- never touches engine/,
build/ or the zip, so it is the same permitted status as tools/stockfish/ in
tests. Do NOT run while a gauntlet match is live (rule 4: competing CPU load
corrupts timing) -- check the process list first.

Usage (Windows, from repo root):
    .venv\\Scripts\\python.exe tools\\acpl_analysis.py tools\\pgns
    .venv\\Scripts\\python.exe tools\\acpl_analysis.py tools\\pgns --depth 20

Outputs: console summary + acpl_report.csv (one row per Endgame move).

v2 fix: the previous version called engine.analyse() on already-terminal
positions, which returns a degenerate Mate(0) that flipped sign. Every
delivered checkmate and decided position then dumped ~19990 fake cpl into the
mean (that is where the bogus ACPL=298 came from). This version scores terminal
nodes directly and caps per-move cpl, so the reported ACPL is trustworthy.
"""
import argparse, csv, glob, os, sys, chess, chess.engine, chess.pgn
from chess.engine import PovScore, Mate, Cp

TEAM = "Endgame"
MATE_CP = 10000
CPL_CAP = 1000          # cap per-move cpl so one disaster can't dominate the mean
MISTAKE = 80
BLUNDER = 150

def find_sf(explicit):
    if explicit:
        return explicit
    for p in ["tools/stockfish/*stockfish*", "tools/stockfish/**/*stockfish*",
              "tools/stockfish/*.exe", "**/stockfish*.exe"]:
        for hit in glob.glob(p, recursive=True):
            if os.path.isfile(hit):
                return hit
    sys.exit("Stockfish not found. Pass --sf <path>.")

def terminal_score(board):
    """Return a PovScore for a game-over board WITHOUT calling the engine.
    Uses a large Cp rather than Mate(0), whose sign is ambiguous."""
    if board.is_checkmate():
        return PovScore(Cp(-MATE_CP), board.turn)     # side to move is mated -> lost
    # stalemate, insufficient material, 75-move, fivefold, etc.
    return PovScore(Cp(0), board.turn)

def cpval(score, pov):
    s = score.pov(pov)
    if s.is_mate():
        m = s.mate()
        sign = 1 if m > 0 else -1                      # m==0 means "mated" -> negative
        return (MATE_CP - abs(m) * 10) * sign
    return s.score()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--sf", default=None)
    ap.add_argument("--depth", type=int, default=20)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--hash", type=int, default=512)
    a = ap.parse_args()

    sf = find_sf(a.sf)
    eng = chess.engine.SimpleEngine.popen_uci(sf)
    eng.configure({"Threads": a.threads, "Hash": a.hash})
    lim = chess.engine.Limit(depth=a.depth)
    print(f"Stockfish: {sf}   depth={a.depth} threads={a.threads}\n")

    csv_rows, summ = [], []
    paths = sorted(glob.glob(os.path.join(a.folder, "*.pgn")))
    if not paths:
        sys.exit(f"No PGNs in {a.folder}")

    for path in paths:
        with open(path) as f:
            g = chess.pgn.read_game(f)
        white, black = g.headers["White"], g.headers["Black"]
        if TEAM not in (white, black):
            continue
        endg = chess.WHITE if white == TEAM else chess.BLACK
        endg_white = endg == chess.WHITE
        opp = black if endg_white else white
        result = g.headers["Result"]; term = g.headers.get("Termination", "")
        tag = os.path.basename(path)

        board = g.board()
        moves = []
        node = g
        while node.variations:
            nxt = node.variation(0); mv = nxt.move
            moves.append((mv, board.san(mv), board.turn))
            board.push(mv); node = nxt

        # one score per position (start + after every ply), terminal-safe
        board = g.board()
        scores, bests = [], []
        info = eng.analyse(board, lim)
        scores.append(info["score"]); bests.append(info["pv"][0] if info.get("pv") else None)
        for mv, san, stm in moves:
            board.push(mv)
            if board.is_game_over(claim_draw=False):
                scores.append(terminal_score(board)); bests.append(None)
            else:
                info = eng.analyse(board, lim)
                scores.append(info["score"]); bests.append(info["pv"][0] if info.get("pv") else None)

        board = g.board()
        rows = []; peak = -10**9; peak_ply = None
        for i, (mv, san, stm) in enumerate(moves):
            before = cpval(scores[i], stm)
            after = cpval(scores[i + 1], stm)
            after_endg = cpval(scores[i + 1], endg)
            if after_endg > peak: peak = after_endg; peak_ply = (i + 1, san)
            if stm == endg:
                bmv = bests[i]
                bsan = board.san(bmv) if bmv else "-"
                cpl = min(max(0, before - after), CPL_CAP)
                rows.append((i + 1, san, before, after, cpl, bsan, after_endg))
            board.push(mv)

        final = cpval(scores[-1], endg)
        cpls = [r[4] for r in rows]
        acpl = sum(cpls) / len(cpls) if cpls else 0
        comp = [r[4] for r in rows if abs(r[2]) < 300]        # move quality while still competitive
        comp_acpl = sum(comp) / len(comp) if comp else 0
        won = (result == "1-0" and endg_white) or (result == "0-1" and not endg_white)
        lost = (result == "1-0" and not endg_white) or (result == "0-1" and endg_white)
        rlabel = "WIN" if won else ("LOSS" if lost else "draw")
        # conversion verdict for draws
        if rlabel == "draw":
            v = "THREW A WIN (peak +{})".format(peak) if peak >= 150 else \
                ("gave up edge (peak +{})".format(peak) if peak >= 60 else "level throughout")
        else:
            v = rlabel
        summ.append((tag, "W" if endg_white else "B", opp, rlabel, term,
                     acpl, comp_acpl, peak, peak_ply, final, v))

        print(f"=== {tag}  Endgame({'W' if endg_white else 'B'}) vs {opp}  {result} [{term}] ===")
        print(f"    ACPL={acpl:.0f} | competitive ACPL(|e|<300)={comp_acpl:.0f} | "
              f"peak {peak:+d}@ply{peak_ply} | final {final:+d} | {v}")
        for r in rows:
            if r[4] >= MISTAKE:
                fl = "BLUNDER" if r[4] >= BLUNDER else "mistake"
                print(f"      ply{r[0]:>3} {r[1]:<7} played={r[3]:+6d}  best {r[5]:<7}={r[2]:+6d}  cpl={r[4]:>4}  {fl}")
        print()
        for r in rows:
            csv_rows.append([tag, opp, "W" if endg_white else "B", r[0], r[1],
                             r[2], r[3], r[4], r[5], r[6]])

    eng.quit()

    with open("acpl_report.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["game", "opp", "color", "ply", "played", "eval_before",
                     "eval_after", "cpl", "best", "eval_after_endgame_pov"])
        wr.writerows(csv_rows)

    print("########## SUMMARY ##########")
    allc = [r[7] for r in csv_rows]
    comp_all = [r[7] for r in csv_rows if abs(r[5]) < 300]
    print(f"Aggregate ACPL: {sum(allc)/len(allc):.0f} ({len(allc)} moves) | "
          f"competitive ACPL: {sum(comp_all)/len(comp_all):.0f} ({len(comp_all)} moves)\n")
    for s in summ:
        print(f"  {s[0]:<44} {s[1]} vs {s[2]:<15} {s[3]:<5} acpl={s[5]:>3.0f} "
              f"comp={s[6]:>3.0f} peak={s[7]:+5d} final={s[9]:+5d} | {s[10]}")
    print("\nWrote acpl_report.csv")

if __name__ == "__main__":
    main()
