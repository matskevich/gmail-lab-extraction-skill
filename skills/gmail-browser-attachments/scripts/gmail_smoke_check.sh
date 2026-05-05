#!/bin/zsh
set -euo pipefail

PORT="${1:-9222}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "== version =="
python3 - <<'PY' "$PORT"
import json
import sys
import urllib.request
port = sys.argv[1]
with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as resp:
    data = json.loads(resp.read().decode())
print(json.dumps({"Browser": data.get("Browser"), "Protocol-Version": data.get("Protocol-Version")}, ensure_ascii=False, indent=2))
PY

echo
echo "== page ws =="
WS_URL="$("$SCRIPT_DIR/gmail_find_page_ws_url.sh" "$PORT")"
if [[ -z "$WS_URL" ]]; then
  echo "gmail_page_ws_url: missing"
  exit 1
fi
echo "$WS_URL"

echo
echo "== inbox snapshot =="
node "$SCRIPT_DIR/gmail_inbox_snapshot.mjs" "$WS_URL" 5

echo
echo "== auth gate =="
node "$SCRIPT_DIR/gmail_assert_authenticated.mjs" "$WS_URL"
