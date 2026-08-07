#!/bin/bash
# Download the Lichess puzzle database (CC0), used to supply themed practice
# puzzles on whatever weaknesses your own games reveal.
#
#   ./build/get_puzzle_db.sh
#
# ~290 MB compressed, downloaded once. The download resumes if interrupted, and
# the file is only moved into place after it verifies, so a half-finished
# download can never look like a good one.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/data/raw/lichess_db_puzzle.csv.zst"
URL="https://database.lichess.org/lichess_db_puzzle.csv.zst"

mkdir -p "$(dirname "$DEST")"

if [ -f "$DEST" ] && zstd -t "$DEST" 2>/dev/null; then
  echo "Already present and valid: $DEST"
  exit 0
fi

if ! command -v zstd >/dev/null; then
  echo "Need 'zstd' to read the database."
  echo "  macOS:  brew install zstd"
  echo "  Linux:  sudo apt install zstd"
  exit 1
fi

echo "Downloading the Lichess puzzle database (~290 MB, one time)..."
# -C - resumes a partial file rather than starting over
if ! curl -L --retry 3 --retry-delay 2 -C - -o "$DEST.part" "$URL"; then
  echo "Download failed. Re-run this script to resume where it stopped."
  exit 1
fi

echo "Verifying..."
if ! zstd -t "$DEST.part" 2>/dev/null; then
  echo "The downloaded file is corrupt. Delete $DEST.part and try again."
  exit 1
fi

mv "$DEST.part" "$DEST"
echo "Ready: $DEST"
