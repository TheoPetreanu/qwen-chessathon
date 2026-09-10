"""Harvest public game PGNs from aichessathon.com.

Every rated game starts from a curated FEN chosen by the organisers. The size
and repeat structure of that position pool decides whether a self-built opening
table is worth building: a small pool that recurs means precomputing our own
move for each position pays off on most games, a large one means it almost
never fires. Our own 9 archived PGNs (8 distinct FENs, 1 repeat) are far too
few to tell. Every team's games are public, so measure it properly.

Also produces real PGNs for ACPL analysis (tools/acpl_analysis.py), which is
otherwise blocked -- the dashboard CSV export carries results and clocks but no
moves.

Read-only fetching of public pages. Be polite: default delay, modest counts.

Usage:
    .venv\\Scripts\\python.exe tools\\fetch_games.py --teams 8 --per-team 12 \\
        --out tools\\pgns_public
"""
import argparse, os, re, time, urllib.request, collections

UA = {"User-Agent": "Mozilla/5.0 (chessathon research; contact via site)"}
BASE = "https://aichessathon.com"


def get(url, timeout=60):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout
    ).read().decode("utf8", "replace")


def team_ids(limit):
    h = get(BASE + "/leaderboard")
    seen, out = set(), []
    for t in re.findall(r"/team/([0-9a-f\-]{36})", h):
        if t not in seen:
            seen.add(t); out.append(t)
        if len(out) >= limit:
            break
    return out


def game_ids(team):
    h = get("%s/team/%s?from=lb" % (BASE, team))
    seen, out = set(), []
    for g in re.findall(r"/game/([0-9a-f\-]{36})", h):
        if g not in seen:
            seen.add(g); out.append(g)
    return out


def game_pgn(gid):
    """Return (pgn_text, round, white, black) or None."""
    h = get("%s/game/%s" % (BASE, gid))
    # the PGN sits inside a Next.js streaming string chunk, JS-escaped
    i = h.find('[Event ')
    if i < 0:
        i = h.find('[Event \\"')
        if i < 0:
            return None
    seg = h[i:i + 60000]
    seg = seg.replace('\\\\n', '\n').replace('\\n', '\n')
    seg = seg.replace('\\\\"', '"').replace('\\"', '"')
    # cut at the terminating result token on the move text
    m = re.search(r"\n\n.*?(1-0|0-1|1/2-1/2|\*)\s", seg, re.S)
    pgn = seg[:m.end()] if m else seg[:8000]
    def tag(name):
        mm = re.search(r'\[%s "([^"]*)"\]' % name, pgn)
        return mm.group(1) if mm else ""
    return pgn, tag("Round"), tag("White"), tag("Black")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teams", type=int, default=8)
    ap.add_argument("--per-team", type=int, default=12)
    ap.add_argument("--delay", type=float, default=0.4)
    ap.add_argument("--out", default=os.path.join("tools", "pgns_public"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    teams = team_ids(args.teams)
    print("teams: %d" % len(teams), flush=True)
    fens = collections.Counter()
    by_round = collections.defaultdict(set)
    n = 0
    for ti, t in enumerate(teams):
        try:
            gids = game_ids(t)
        except Exception as e:
            print("  team %s failed: %s" % (t[:8], e)); continue
        for g in gids[:args.per_team]:
            path = os.path.join(args.out, g + ".pgn")
            try:
                if os.path.exists(path):
                    pgn = open(path).read()
                    rd = (re.search(r'\[Round "([^"]*)"\]', pgn) or [None, ""])[1]
                else:
                    res = game_pgn(g)
                    if not res:
                        continue
                    pgn, rd, _, _ = res
                    open(path, "w").write(pgn)
                    time.sleep(args.delay)
                mf = re.search(r'\[FEN "([^"]*)"\]', pgn)
                if mf:
                    key = " ".join(mf.group(1).split()[:4])
                    fens[key] += 1
                    by_round[rd].add(key)
                n += 1
            except Exception as e:
                print("   game %s failed: %s" % (g[:8], e))
        print("  team %d/%d  games=%d  distinct FENs=%d"
              % (ti + 1, len(teams), n, len(fens)), flush=True)

    print("\n=== POSITION POOL ===")
    print("games sampled      : %d" % n)
    print("distinct start FENs: %d" % len(fens))
    if n:
        print("reuse rate         : %.2f games per position" % (n / max(len(fens), 1)))
    print("most common positions:")
    for f, c in fens.most_common(8):
        print("  x%-3d %s" % (c, f))
    multi = [(r, len(s)) for r, s in sorted(by_round.items()) if r]
    print("\ndistinct FENs within a single round (1 would mean one position per round):")
    for r, c in multi[:12]:
        print("  round %-4s %d distinct" % (r, c))


if __name__ == "__main__":
    main()
