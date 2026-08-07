#!/bin/bash
# =============================================================================
# One-command setup for a fresh clone.
#
#   ./setup.sh                        interactive
#   ./setup.sh --username NAME        non-interactive
#   ./setup.sh --username NAME --no-puzzles --no-schedule
#
# Checks your dependencies, records your chess.com username, downloads the
# puzzle database, analyses your games and builds your exercises.
#
# Everything it installs is local to this folder except the three system
# packages (python-chess, stockfish, zstd), which it will tell you how to get.
# =============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || exit 1

USERNAME=""
WANT_PUZZLES=1
WANT_SCHEDULE=""      # empty = ask
while [ $# -gt 0 ]; do
  case "$1" in
    --username) USERNAME="${2:-}"; shift 2 ;;
    --no-puzzles) WANT_PUZZLES=0; shift ;;
    --no-schedule) WANT_SCHEDULE=0; shift ;;
    --schedule) WANT_SCHEDULE=1; shift ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
done

case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux)  OS=linux ;;
  *)      OS=other ;;
esac

hint() {   # hint <package> -- how to install it on this OS
  case "$OS" in
    mac)   echo "brew install $1" ;;
    linux) echo "sudo apt install $1   (or your distro's equivalent)" ;;
    *)     echo "install '$1' for your platform" ;;
  esac
}

echo
echo "  ♞  Chess trainer setup"
echo "  ─────────────────────────────────────────────"

# ---- dependencies ----------------------------------------------------------
MISSING=0

if command -v python3 >/dev/null; then
  echo "  ✓ python3 ($(python3 -V 2>&1 | cut -d' ' -f2))"
else
  echo "  ✗ python3 not found — $(hint python3)"; MISSING=1
fi

if python3 -c "import chess" 2>/dev/null; then
  echo "  ✓ python-chess"
else
  echo "  ✗ python-chess not found"
  echo "      pip3 install chess"
  echo "      (if pip refuses with 'externally-managed-environment', use a venv:"
  echo "       python3 -m venv .venv && source .venv/bin/activate && pip install chess)"
  MISSING=1
fi

if command -v stockfish >/dev/null; then
  echo "  ✓ stockfish ($(command -v stockfish))"
else
  echo "  ✗ stockfish not found — $(hint stockfish)"; MISSING=1
fi

if command -v zstd >/dev/null; then
  echo "  ✓ zstd"
else
  echo "  ✗ zstd not found — $(hint zstd)"
  [ "$WANT_PUZZLES" -eq 1 ] && MISSING=1
fi

if [ "$MISSING" -ne 0 ]; then
  echo
  echo "  Install what's missing above, then run ./setup.sh again."
  exit 1
fi

# ---- username --------------------------------------------------------------
CURRENT=$(python3 -c "import sys;sys.path.insert(0,'build');import conf;print(conf.username())" 2>/dev/null)
if [ -z "$USERNAME" ] && [ -n "$CURRENT" ]; then
  USERNAME="$CURRENT"
  echo "  ✓ chess.com username: $USERNAME"
elif [ -z "$USERNAME" ]; then
  echo
  read -r -p "  Your chess.com username: " USERNAME
  [ -z "$USERNAME" ] && { echo "  Need a username to continue."; exit 1; }
fi

# Confirm the account exists before doing anything slow.
if ! python3 - "$USERNAME" <<'PY'
import sys, urllib.request, urllib.error
sys.path.insert(0, 'build')
import conf
name = sys.argv[1]
req = urllib.request.Request(
    f"https://api.chess.com/pub/player/{name}",
    headers={"User-Agent": conf.user_agent()})
try:
    urllib.request.urlopen(req, timeout=30)
except urllib.error.HTTPError as e:
    if e.code == 404:
        print(f"  ✗ chess.com has no player called '{name}'")
        sys.exit(1)
    print(f"  ! chess.com returned HTTP {e.code}; continuing anyway")
except Exception as e:
    print(f"  ! could not reach chess.com ({e}); continuing anyway")
PY
then exit 1; fi
python3 -c "import sys;sys.path.insert(0,'build');import conf;conf.save_local({'username':'$USERNAME'})"
echo "  ✓ saved to build/coach_config.local.json (gitignored)"

# ---- puzzle database -------------------------------------------------------
if [ "$WANT_PUZZLES" -eq 1 ]; then
  if [ -f data/raw/lichess_db_puzzle.csv.zst ]; then
    echo "  ✓ Lichess puzzle database already downloaded"
  else
    echo
    echo "  The Lichess puzzle database (~290 MB, CC0) supplies themed practice"
    echo "  puzzles matched to the weaknesses found in your games."
    bash build/get_puzzle_db.sh || {
      echo "  ! continuing without it — you'll still get exercises from your own games"; }
  fi
fi

# ---- build -----------------------------------------------------------------
echo
echo "  Building. The first analysis takes a while (Stockfish reads every move"
echo "  of every game); later refreshes are incremental and quick."
echo
bash build/refresh.sh || { echo "  Setup failed — see the log in data/logs/."; exit 1; }

# ---- schedule --------------------------------------------------------------
if [ -z "$WANT_SCHEDULE" ]; then
  echo
  read -r -p "  Refresh automatically every two weeks? [Y/n] " ans
  case "$ans" in [Nn]*) WANT_SCHEDULE=0 ;; *) WANT_SCHEDULE=1 ;; esac
fi
if [ "$WANT_SCHEDULE" -eq 1 ]; then
  bash build/install_schedule.sh || echo "  ! could not install the schedule; run build/refresh.sh by hand"
fi

echo
echo "  ─────────────────────────────────────────────"
echo "  Done. Open app/index.html in your browser."
echo
