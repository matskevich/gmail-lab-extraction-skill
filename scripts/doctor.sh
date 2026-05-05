#!/bin/zsh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILL_DIR="$REPO_ROOT/skills/gmail-browser-attachments"
PORT="${PORT:-9222}"
CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

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
if command -v "$PYTHON_BIN" >/dev/null 2>&1 || [[ -x "$PYTHON_BIN" ]]; then
  python_version="$("$PYTHON_BIN" - <<'PY'
import sys
print(sys.version.split()[0])
PY
)"
  if "$PYTHON_BIN" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
  then
    printf 'ok\tpython\t%s\t%s\n' "$PYTHON_BIN" "$python_version"
  else
    printf 'bad\tpython\t%s\t%s (need >=3.11)\n' "$PYTHON_BIN" "$python_version"
  fi
else
  printf 'missing\tpython\t%s\n' "$PYTHON_BIN"
fi
check_bin rsync
check_bin file
check_bin pdftotext
check_bin pdftoppm
check_bin tesseract

echo
echo "== python modules =="
"$PYTHON_BIN" - <<'PY'
modules = [
    ("googleapiclient.discovery", "gmail_api_client"),
    ("google_auth_oauthlib.flow", "gmail_oauth"),
]
for module, label in modules:
    try:
        __import__(module)
    except Exception as exc:
        print(f"missing\t{label}\t{exc}")
    else:
        print(f"ok\t{label}\t{module}")
PY

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
node --check "$SKILL_DIR/scripts/gmail_assert_authenticated.mjs"
node --check "$SKILL_DIR/scripts/chrome_cdp_create_target.mjs"
node --check "$SKILL_DIR/scripts/chrome_cdp_close_target.mjs"
"$PYTHON_BIN" -m py_compile "$SKILL_DIR/scripts/ocr_image_assets.py"
"$PYTHON_BIN" -m py_compile "$REPO_ROOT/scripts/run_gmail_api_export.py"
zsh -n "$SKILL_DIR/scripts/start_chrome_cdp_clone.sh"
zsh -n "$SKILL_DIR/scripts/start_chrome_cdp_profile.sh"
zsh -n "$SKILL_DIR/scripts/gmail_find_page_ws_url.sh"
zsh -n "$SKILL_DIR/scripts/gmail_smoke_check.sh"
zsh -n "$REPO_ROOT/scripts/run_gmail_discovery.sh"
zsh -n "$REPO_ROOT/scripts/run_gmail_lab_export.sh"
zsh -n "$REPO_ROOT/scripts/run_portal_lab_export.sh"
zsh -n "$REPO_ROOT/scripts/run_regression_suite.sh"
echo "ok\tsyntax\tall checked"

echo
echo "== cdp port =="
"$PYTHON_BIN" - <<'PY' "$PORT"
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
