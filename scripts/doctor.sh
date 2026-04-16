#!/bin/zsh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILL_DIR="$REPO_ROOT/skills/gmail-browser-attachments"
PORT="${PORT:-9222}"
CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

check_bin() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    printf 'ok\t%s\t%s\n' "$name" "$(command -v "$name")"
  else
    printf 'missing\t%s\t-\n' "$name"
  fi
}

echo "== bins =="
check_bin node
check_bin python3
check_bin rsync
check_bin file
check_bin pdftotext
check_bin pdftoppm
check_bin tesseract

echo
echo "== paths =="
if [[ -x "$CHROME_APP" ]]; then
  printf 'ok\tchrome_app\t%s\n' "$CHROME_APP"
else
  printf 'missing\tchrome_app\t%s\n' "$CHROME_APP"
fi

if [[ -f "$SKILL_DIR/SKILL.md" ]]; then
  printf 'ok\tskill_dir\t%s\n' "$SKILL_DIR"
else
  printf 'missing\tskill_dir\t%s\n' "$SKILL_DIR"
fi

echo
echo "== syntax =="
node --check "$SKILL_DIR/scripts/gmail_collect_attachments_from_query.mjs"
node --check "$SKILL_DIR/scripts/gmail_collect_inline_assets_from_query.mjs"
node --check "$SKILL_DIR/scripts/gmail_fetch_attachment_via_cdp.mjs"
python3 -m py_compile "$SKILL_DIR/scripts/ocr_image_assets.py"
zsh -n "$SKILL_DIR/scripts/start_chrome_cdp_clone.sh"
zsh -n "$SKILL_DIR/scripts/gmail_find_page_ws_url.sh"
zsh -n "$SKILL_DIR/scripts/gmail_smoke_check.sh"
echo "ok\tsyntax\tall checked"

echo
echo "== cdp port =="
python3 - <<'PY' "$PORT"
import json
import sys
import urllib.request

port = sys.argv[1]
url = f"http://127.0.0.1:{port}/json/version"
try:
    with urllib.request.urlopen(url, timeout=2) as resp:
        data = json.loads(resp.read().decode())
    print(f"ok\tcdp\t{data.get('Browser', '')}")
except Exception as exc:
    print(f"down\tcdp\t{exc}")
PY
