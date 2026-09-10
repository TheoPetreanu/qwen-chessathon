#!/bin/bash
# Wait for the book build to write its output, validate + record it, stop the
# harvest cleanly, then shut down. Abort any time with:  shutdown /a
cd "C:/Users/theop/Documents/chessathon"
LOG=overnight_logs/build_book.log

echo "[$(date +%H:%M:%S)] waiting for book build to finish..."
while ! grep -q "^wrote " "$LOG" 2>/dev/null; do sleep 30; done
echo "[$(date +%H:%M:%S)] build finished: $(grep '^wrote ' $LOG)"

# stop the harvest so it is not killed mid-write by the shutdown
taskkill //F //FI "IMAGENAME eq python.exe" //FI "WINDOWTITLE eq *fetch_games*" >/dev/null 2>&1
for p in $(wmic process where "name='python.exe'" get ProcessId,CommandLine 2>/dev/null | grep fetch_games | grep -oE '[0-9]+$'); do
  taskkill //F //PID "$p" >/dev/null 2>&1
done
echo "[$(date +%H:%M:%S)] harvest stopped"

# validate the shipped artifact (structural only: no engine import needed)
.venv/Scripts/python.exe - <<'PY' > overnight_logs/book_validation.txt 2>&1
import json, glob, re, os
import chess
n_ok = n_bad = 0
try:
    import sys; sys.path.insert(0, 'engine')
    from ca_book import BOOK
except Exception as e:
    BOOK = {}; print('ca_book.py MISSING/UNREADABLE:', e)
for k, m in BOOK.items():
    try:
        b = chess.Board(k + ' 0 1')
        if chess.Move.from_uci(m) in b.legal_moves: n_ok += 1
        else: n_bad += 1
    except Exception: n_bad += 1
pool = set()
for p in glob.glob('tools/pgns_public/*.pgn'):
    mm = re.search(r'\[FEN "([^"]*)"\]', open(p).read())
    if mm: pool.add(' '.join(mm.group(1).split()[:4]))
print('entries      :', len(BOOK))
print('legal        :', n_ok)
print('ILLEGAL      :', n_bad)
print('pool starts  : %d/%d' % (len(set(BOOK) & pool), len(pool)))
print('size KB      : %.0f' % (os.path.getsize('engine/ca_book.py')/1024 if os.path.exists('engine/ca_book.py') else 0))
print('pgns harvested:', len(glob.glob('tools/pgns_public/*.pgn')))
PY
echo "[$(date +%H:%M:%S)] validation:"; cat overnight_logs/book_validation.txt

# record state for the next session
{
  echo ""
  echo "## AUTOSAVE $(date +%Y-%m-%d\ %H:%M) -- unattended finish, PC shut down"
  echo ""
  echo "Book build finished and was validated automatically. Raw numbers:"
  echo ""
  echo '```'
  cat overnight_logs/book_validation.txt
  echo '```'
  echo ""
  echo "State at shutdown:"
  echo "- \`checkpoints/REFERENCE.txt\` = $(cat checkpoints/REFERENCE.txt)"
  echo "- \`build/\` and \`submission_openingcap.zip\` = openingcap (adopted, +18 +/- 11). Book NOT in the zip."
  echo "- \`engine/\` = openingcap + book lookup + the generated \`engine/ca_book.py\`."
  echo "- Book cache \`tools/book_cache.jsonl\` is resumable; rerun build_book.py to extend."
  echo "- Harvest was stopped mid-run; it is resumable (already-fetched games are skipped)."
  echo ""
  echo "**NEXT STEP: the book is UNTESTED.** Run an SPRT of \`engine/\` vs"
  echo "\`checkpoints/openingcap\` before adopting or shipping it. Estimated effect"
  echo "was +10 to +30 Elo but that is a guess, and the book makes our opening"
  echo "deterministic, so a bad entry repeats against every opponent who reaches it."
} >> PROGRESS.md
echo "[$(date +%H:%M:%S)] PROGRESS.md updated"

echo "[$(date +%H:%M:%S)] shutting down in 120s -- abort with: shutdown /a"
shutdown //s //t 120 //c "Chessathon book build complete - saved and shutting down"
