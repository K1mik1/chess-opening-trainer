#!/bin/bash
# =============================================================================
# Re-read your recent chess.com games, rebuild the exercises and lessons around
# whatever you are getting wrong lately, and reweight the opening repertoire
# around whatever you are actually playing.
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
# The repertoire is now data-driven too (course weights come from your recent
# games), so it gets the same treatment: rebuilt every refresh, and rolled
# back untouched if anything downstream fails.
BACKUP_REP=""
if [ -f app/repertoire.js ]; then
  BACKUP_REP="$(mktemp)"
  cp app/repertoire.js "$BACKUP_REP"
fi
restore_on_fail() {
  if [ -n "$BACKUP" ] && [ -f "$BACKUP" ]; then
    cp "$BACKUP" app/exercises.js
    log "restored the previous exercises.js"
  fi
  if [ -n "$BACKUP_REP" ] && [ -f "$BACKUP_REP" ]; then
    cp "$BACKUP_REP" app/repertoire.js
    log "restored the previous repertoire.js"
  fi
  log "=== refresh FAILED (your existing practice is untouched) ==="
  exit 1
}

# ---- 1. download -----------------------------------------------------------
log "1/5 fetching games from chess.com..."
if ! python3 build/fetch_games.py >>"$LOG" 2>&1; then
  log "fetch failed (offline?)"; restore_on_fail
fi

# ---- 2. analyse ------------------------------------------------------------
log "2/5 analysing with Stockfish (this is the slow part)..."
if ! python3 build/analyze_games.py >>"$LOG" 2>&1; then
  log "analysis failed"; restore_on_fail
fi

# ---- 3. rebuild exercises and lessons --------------------------------------
log "3/5 rebuilding exercises and lessons..."
if ! python3 build/build_exercises.py >>"$LOG" 2>&1; then
  log "exercise build failed"; restore_on_fail
fi

# ---- 4. which openings are you meeting with no answer? ---------------------
# Reported, not acted on: adding a course changes what you drill every
# morning, so it stays a decision you make. See build/derive_lines.py for
# turning a gap into lines.
log "4/5 checking for unanswered openings..."
python3 build/gaps.py > "$ROOT/data/gaps.txt" 2>>"$LOG" || true

# ---- 5. reweight and rebuild the repertoire --------------------------------
# Course weights are recomputed from the games just analysed, so the openings
# the daily session introduces first follow what you are actually playing and
# losing to rather than a fixed curriculum. Engine verdicts are cached in
# build/engine_verified.json, so this does not re-run Stockfish.
log "5/5 reweighting the repertoire..."
if ! python3 build/generate.py >>"$LOG" 2>&1; then
  log "repertoire rebuild failed"; restore_on_fail
fi

# A plain-text copy of the report, so you can read where you stand without
# opening the app.
python3 build/weaknesses.py > "$ROOT/data/report.txt" 2>>"$LOG" || true

[ -n "$BACKUP" ] && rm -f "$BACKUP"
[ -n "$BACKUP_REP" ] && rm -f "$BACKUP_REP"

log "=== refresh complete ==="
tail -20 "$ROOT/data/report.txt" 2>/dev/null | tee -a "$LOG"

# keep the log directory from growing forever
find "$LOG_DIR" -name 'refresh-*.log' -mtime +90 -delete 2>/dev/null || true
exit 0
