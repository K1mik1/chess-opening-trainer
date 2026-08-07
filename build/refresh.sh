#!/bin/bash
# =============================================================================
# Re-read your recent chess.com games and rebuild the exercises around whatever
# you are getting wrong lately.
#
#   ./build/refresh.sh
#
# Safe to run any time. Everything is incremental: months already downloaded
# and games already analysed are skipped, so a routine run costs a couple of
# minutes even though the first one takes longer.
#
# This is what the fortnightly launchd job runs. It is a plain shell script
# with no dependency on Claude or any network service beyond chess.com.
# =============================================================================
set -uo pipefail

# Scheduled jobs (launchd, cron) start with a bare PATH, so add the usual
# places python3, stockfish and zstd get installed -- while keeping whatever
# the caller already had, which is what makes this work outside Homebrew.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

LOG_DIR="$ROOT/data/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/refresh-$(date +%Y-%m-%d).log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "=== refresh starting ==="

# ---- preflight -------------------------------------------------------------
if ! command -v python3 >/dev/null; then
  log "FATAL: python3 not found"; exit 1
fi
if ! python3 -c "import chess" 2>/dev/null; then
  log "FATAL: python-chess missing. Install with: pip3 install chess"; exit 1
fi
if ! command -v stockfish >/dev/null; then
  log "FATAL: stockfish not found. Install with: brew install stockfish"; exit 1
fi

USERNAME=$(python3 -c "import sys;sys.path.insert(0,'build');import conf;print(conf.username())" 2>/dev/null)
if [ -z "$USERNAME" ]; then
  log "FATAL: no chess.com username set."
  log "       Run:  ./setup.sh   (or python3 build/fetch_games.py --username YOUR_NAME)"
  exit 1
fi
log "user: $USERNAME"

# The exercises currently in the app. If anything below fails we leave this
# file exactly as it is -- a failed refresh must never take away your practice.
BACKUP=""
if [ -f app/exercises.js ]; then
  BACKUP="$(mktemp)"
  cp app/exercises.js "$BACKUP"
fi
restore_on_fail() {
  if [ -n "$BACKUP" ] && [ -f "$BACKUP" ]; then
    cp "$BACKUP" app/exercises.js
    log "restored the previous exercises.js"
  fi
  log "=== refresh FAILED (your existing exercises are untouched) ==="
  exit 1
}

# ---- 1. download -----------------------------------------------------------
log "1/3 fetching games from chess.com..."
if ! python3 build/fetch_games.py >>"$LOG" 2>&1; then
  log "fetch failed (offline?)"; restore_on_fail
fi

# ---- 2. analyse ------------------------------------------------------------
log "2/3 analysing with Stockfish (this is the slow part)..."
if ! python3 build/analyze_games.py >>"$LOG" 2>&1; then
  log "analysis failed"; restore_on_fail
fi

# ---- 3. rebuild exercises --------------------------------------------------
log "3/3 rebuilding exercises..."
if ! python3 build/build_exercises.py >>"$LOG" 2>&1; then
  log "exercise build failed"; restore_on_fail
fi

# A plain-text copy of the report, so you can read where you stand without
# opening the app.
python3 build/weaknesses.py > "$ROOT/data/report.txt" 2>>"$LOG" || true

[ -n "$BACKUP" ] && rm -f "$BACKUP"

log "=== refresh complete ==="
tail -20 "$ROOT/data/report.txt" 2>/dev/null | tee -a "$LOG"

# keep the log directory from growing forever
find "$LOG_DIR" -name 'refresh-*.log' -mtime +90 -delete 2>/dev/null || true
exit 0
