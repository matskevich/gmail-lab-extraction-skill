#!/bin/zsh
set -euo pipefail

PORT="${PORT:-9222}"
URL="${1:-https://mail.google.com/mail/u/0/#inbox}"
TARGET_ROOT="${TARGET_ROOT:-$HOME/.gmail-lab/chrome-cdp-profile}"
RESET_PROFILE="${RESET_PROFILE:-0}"
CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if [[ "$RESET_PROFILE" == "1" ]]; then
  case "$TARGET_ROOT" in
    "$HOME/.gmail-lab/"*)
      if command -v python3 >/dev/null 2>&1; then
        python3 - <<'PY' "$TARGET_ROOT"
import shutil
import sys
shutil.rmtree(sys.argv[1], ignore_errors=True)
PY
      else
        rm -rf "$TARGET_ROOT"
      fi
      ;;
    *)
      echo "refusing RESET_PROFILE outside ~/.gmail-lab: $TARGET_ROOT" >&2
      exit 2
      ;;
  esac
fi

mkdir -p "$TARGET_ROOT"

echo "starting persistent chrome cdp profile"
echo "  target: $TARGET_ROOT"
echo "  port:   $PORT"
echo "  url:    $URL"
echo "  note:   log into Gmail in this window once; later runs reuse this profile"

exec "$CHROME_APP" \
  --user-data-dir="$TARGET_ROOT" \
  --remote-debugging-port="$PORT" \
  "$URL"
