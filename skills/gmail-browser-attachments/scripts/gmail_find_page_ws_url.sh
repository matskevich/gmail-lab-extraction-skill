#!/bin/zsh
set -euo pipefail

PORT="${1:-9222}"
TITLE_NEEDLE="${2:-}"
TARGET_URL="${3:-https://mail.google.com/mail/u/0/#inbox}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

BROWSER_WS_URL="$(python3 - <<'PY' "$PORT"
import json
import sys
import urllib.request

port = sys.argv[1]
base = f"http://127.0.0.1:{port}"
with urllib.request.urlopen(base + "/json/version", timeout=3) as resp:
    data = json.loads(resp.read().decode())
print(data.get("webSocketDebuggerUrl", ""))
PY
)"

FOUND_WS="$(python3 - <<'PY' "$PORT" "$TITLE_NEEDLE"
import json
import sys
import time
import urllib.request

port, needle = sys.argv[1], sys.argv[2]
base = f"http://127.0.0.1:{port}"


def fetch_json(path: str):
    with urllib.request.urlopen(base + path, timeout=3) as resp:
        return json.loads(resp.read().decode())


def find_ws(targets):
    for item in targets:
        if item.get("type") != "page":
            continue
        url = item.get("url", "")
        title = item.get("title", "")
        if "mail.google.com" not in url:
            continue
        if needle and needle not in url and needle not in title:
            continue
        ws = item.get("webSocketDebuggerUrl", "")
        if ws:
            return ws
    return ""


try:
    targets = fetch_json("/json/list")
    ws = find_ws(targets)
    if ws:
        print(ws)
except Exception:
    pass
PY
)"

if [[ -n "${FOUND_WS:-}" ]]; then
  printf '%s\n' "$FOUND_WS"
  exit 0
fi

if [[ -n "${BROWSER_WS_URL:-}" ]]; then
  node "$SCRIPT_DIR/chrome_cdp_create_target.mjs" "$BROWSER_WS_URL" "$TARGET_URL" >/dev/null 2>&1 || true
  python3 - <<'PY' "$PORT" "$TITLE_NEEDLE"
import json
import sys
import time
import urllib.request

port, needle = sys.argv[1], sys.argv[2]
base = f"http://127.0.0.1:{port}"

def fetch_json(path: str):
    with urllib.request.urlopen(base + path, timeout=3) as resp:
        return json.loads(resp.read().decode())

for _ in range(12):
    time.sleep(0.5)
    try:
        targets = fetch_json("/json/list")
    except Exception:
        continue
    for item in targets:
        if item.get("type") != "page":
            continue
        url = item.get("url", "")
        title = item.get("title", "")
        if "mail.google.com" not in url:
            continue
        if needle and needle not in url and needle not in title:
            continue
        ws = item.get("webSocketDebuggerUrl", "")
        if ws:
            print(ws)
            raise SystemExit(0)
PY
fi
