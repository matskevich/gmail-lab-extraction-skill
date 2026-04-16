#!/bin/zsh
set -euo pipefail

PORT="${PORT:-9222}"
PROFILE_DIR="${PROFILE_DIR:-Default}"
URL="${1:-https://mail.google.com/mail/u/0/#inbox}"
REFRESH="${REFRESH_PROFILE:-0}"
CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SOURCE_ROOT="$HOME/Library/Application Support/Google/Chrome"
SOURCE_PROFILE="$SOURCE_ROOT/$PROFILE_DIR"
TARGET_BASE="${TARGET_BASE:-/tmp}"
TARGET_ROOT_DEFAULT="$TARGET_BASE/codex-chrome-cdp-${PROFILE_DIR:l}"
TARGET_ROOT="${TARGET_ROOT:-$TARGET_ROOT_DEFAULT}"

if [[ ! -d "$SOURCE_PROFILE" ]]; then
  echo "missing source chrome profile: $SOURCE_PROFILE" >&2
  exit 1
fi

if [[ "$REFRESH" == "1" || ! -d "$TARGET_ROOT/$PROFILE_DIR" ]]; then
  if [[ -e "$TARGET_ROOT" ]]; then
    if command -v python3 >/dev/null 2>&1; then
      python3 - <<'PY' "$TARGET_ROOT"
import shutil
import sys
target = sys.argv[1]
shutil.rmtree(target, ignore_errors=True)
PY
    else
      rm -rf "$TARGET_ROOT" 2>/dev/null || true
    fi
  fi
  if [[ -e "$TARGET_ROOT" ]]; then
    TS="$(date +%Y%m%d-%H%M%S)"
    TARGET_ROOT="${TARGET_ROOT_DEFAULT}-${TS}"
    echo "stale clone dir not removable; using fresh target: $TARGET_ROOT"
  fi
  mkdir -p "$TARGET_ROOT"
  rsync -a --delete "$SOURCE_PROFILE" "$TARGET_ROOT/"
  if [[ -f "$SOURCE_ROOT/Local State" ]]; then
    cp "$SOURCE_ROOT/Local State" "$TARGET_ROOT/Local State"
  fi
fi

echo "starting chrome clone"
echo "  source: $SOURCE_PROFILE"
echo "  target: $TARGET_ROOT"
echo "  port:   $PORT"
echo "  url:    $URL"

exec "$CHROME_APP" \
  --user-data-dir="$TARGET_ROOT" \
  --profile-directory="$PROFILE_DIR" \
  --remote-debugging-port="$PORT" \
  "$URL"
