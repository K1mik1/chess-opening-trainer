#!/bin/bash
# =============================================================================
# Set up (or remove) the automatic fortnightly refresh.
#
#   ./build/install_schedule.sh           install / update the schedule
#   ./build/install_schedule.sh --remove  stop refreshing automatically
#   ./build/install_schedule.sh --status  is it installed? when did it last run?
#
# macOS uses launchd, which handles a sleeping laptop: if the machine is asleep
# at the scheduled time, the job runs at the next wake instead of being skipped.
# Linux falls back to a crontab entry.
#
# Either way it runs build/refresh.sh at 03:30 on the 1st and 15th of a month.
# =============================================================================
set -uo pipefail

LABEL="com.chess-coach.refresh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRON_LINE="30 3 1,15 * * cd $ROOT && /bin/bash build/refresh.sh >/dev/null 2>&1"
CRON_TAG="# chess-coach fortnightly refresh"

case "$(uname -s)" in
  Darwin) PLATFORM=mac ;;
  *)      PLATFORM=cron ;;
esac

show_logs() {
  echo "Recent runs:"
  ls -1t "$ROOT/data/logs"/refresh-*.log 2>/dev/null | head -3 | sed 's/^/  /' \
    || echo "  (none yet)"
}

# ---------------------------------------------------------------- macOS ----
mac_install() {
  mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data/logs"
  cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>              <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT/build/refresh.sh</string>
  </array>
  <key>WorkingDirectory</key>   <string>$ROOT</string>

  <!-- 03:30 on the 1st and the 15th -->
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Day</key><integer>1</integer>
          <key>Hour</key><integer>3</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Day</key><integer>15</integer>
          <key>Hour</key><integer>3</integer><key>Minute</key><integer>30</integer></dict>
  </array>

  <key>RunAtLoad</key>          <false/>
  <!-- Stockfish will happily eat every core; keep it out of the way. -->
  <key>Nice</key>               <integer>10</integer>
  <key>LowPriorityIO</key>      <true/>
  <key>ProcessType</key>        <string>Background</string>

  <key>StandardOutPath</key>    <string>$ROOT/data/logs/launchd.out.log</string>
  <key>StandardErrorPath</key>  <string>$ROOT/data/logs/launchd.err.log</string>
</dict>
</plist>
PLISTEOF

  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null \
    || launchctl load "$PLIST" 2>/dev/null \
    || { echo "Could not register the job with launchd."; exit 1; }

  echo "Automatic refresh installed (launchd)."
  echo "  runs   : 03:30 on the 1st and 15th of each month"
  echo "  logs   : $ROOT/data/logs/"
}

mac_remove() {
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null \
    || launchctl unload "$PLIST" 2>/dev/null
  rm -f "$PLIST"
  echo "Automatic refresh removed."
}

mac_status() {
  if launchctl list 2>/dev/null | grep -q "$LABEL"; then
    echo "Installed and loaded (launchd):"
    launchctl list | grep "$LABEL" | awk '{print "  last exit: "$2"  pid: "$1}'
  else
    echo "Not installed."
  fi
}

# ----------------------------------------------------------------- cron ----
cron_install() {
  mkdir -p "$ROOT/data/logs"
  if ! command -v crontab >/dev/null; then
    echo "No crontab on this system. Run build/refresh.sh from your own scheduler."
    exit 1
  fi
  # replace any previous entry of ours, keep everything else
  (crontab -l 2>/dev/null | grep -v -F "$CRON_TAG" | grep -v -F "build/refresh.sh"
   echo "$CRON_TAG"
   echo "$CRON_LINE") | crontab -
  echo "Automatic refresh installed (cron)."
  echo "  runs   : 03:30 on the 1st and 15th of each month"
  echo "  note   : cron skips runs while the machine is off; run"
  echo "           ./build/refresh.sh by hand after a long break."
  echo "  logs   : $ROOT/data/logs/"
}

cron_remove() {
  if command -v crontab >/dev/null; then
    crontab -l 2>/dev/null | grep -v -F "$CRON_TAG" | grep -v -F "build/refresh.sh" | crontab -
  fi
  echo "Automatic refresh removed."
}

cron_status() {
  if crontab -l 2>/dev/null | grep -q -F "build/refresh.sh"; then
    echo "Installed (cron):"
    crontab -l | grep -F "build/refresh.sh" | sed 's/^/  /'
  else
    echo "Not installed."
  fi
}

# ----------------------------------------------------------------- main ----
case "${1:-install}" in
  --remove) [ "$PLATFORM" = mac ] && mac_remove || cron_remove ;;
  --status) [ "$PLATFORM" = mac ] && mac_status || cron_status; show_logs ;;
  *)        [ "$PLATFORM" = mac ] && mac_install || cron_install
            echo "  check  : ./build/install_schedule.sh --status"
            echo "  remove : ./build/install_schedule.sh --remove" ;;
esac
