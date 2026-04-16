#!/bin/zsh
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: scripts/run_portal_lab_export.sh <portal_targets.tsv> [run-dir]" >&2
  echo "tsv format: <provider><TAB><locator><TAB><rowNeedle?><TAB><patientHint?>" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILL_DIR="$REPO_ROOT/skills/gmail-browser-attachments"
TARGETS_FILE="$(python3 - <<'PY' "$1"
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
RUN_DIR_INPUT="${2:-$REPO_ROOT/runs/portal-run-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="$(python3 - <<'PY' "$RUN_DIR_INPUT"
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
PORT="${PORT:-9222}"
START_CHROME="${START_CHROME:-1}"
WAIT_SECONDS="${WAIT_SECONDS:-30}"
STOP_CHROME_ON_EXIT="${STOP_CHROME_ON_EXIT:-1}"

RAW_DIR="$RUN_DIR/raw"
PDF_TEXT_DIR="$RUN_DIR/pdf_text"
LOG_DIR="$RUN_DIR/logs"
MANIFEST_TSV="$RUN_DIR/run_manifest.tsv"
META_TXT="$RUN_DIR/run_meta.txt"
ASSET_MANIFEST="$RUN_DIR/asset_manifest.tsv"
CHROME_LOG="$LOG_DIR/chrome_clone.log"
SMOKE_LOG="$LOG_DIR/smoke_check.log"

mkdir -p "$RAW_DIR" "$PDF_TEXT_DIR" "$LOG_DIR"

CHROME_PID=""
STARTED_CLONE=0

cleanup() {
  if [[ "$STARTED_CLONE" == "1" && "$STOP_CHROME_ON_EXIT" == "1" && -n "$CHROME_PID" ]]; then
    kill "$CHROME_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

{
  echo "run_dir=$RUN_DIR"
  echo "targets_file=$TARGETS_FILE"
  echo "port=$PORT"
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$META_TXT"

echo -e "line_no\tprovider\tlocator\trow_needle\tpatient_hint\tportal_url\tstatus\traw_dir\tpdf_text_manifest\tthread_json\tprovider_json\tstderr_log" > "$MANIFEST_TSV"

port_is_up() {
  python3 - <<'PY' "$PORT"
import sys, urllib.request
port = sys.argv[1]
try:
    urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
    print("up")
except Exception:
    print("down")
PY
}

slugify() {
  python3 - <<'PY' "$1"
import re, sys
value = sys.argv[1].strip().lower()
value = re.sub(r"\s+", "-", value)
value = re.sub(r"[^a-z0-9а-яё_-]+", "-", value, flags=re.IGNORECASE)
value = re.sub(r"-{2,}", "-", value).strip("-")
print(value[:80] or "target")
PY
}

browser_ws_url() {
  python3 - <<'PY' "$PORT"
import json, sys, urllib.request
port = sys.argv[1]
with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as resp:
    data = json.loads(resp.read().decode())
print(data.get("webSocketDebuggerUrl", ""))
PY
}

resolve_page_ws_url() {
  python3 - <<'PY' "$PORT" "$1"
import json, sys, time, urllib.request
port, target_id = sys.argv[1], sys.argv[2]
base = f"http://127.0.0.1:{port}"
for _ in range(30):
    with urllib.request.urlopen(base + "/json/list", timeout=3) as resp:
        data = json.loads(resp.read().decode())
    for item in data:
        if item.get("id") == target_id and item.get("webSocketDebuggerUrl"):
            print(item["webSocketDebuggerUrl"])
            raise SystemExit(0)
    time.sleep(0.5)
raise SystemExit(1)
PY
}

resolve_gmail_page_ws_url() {
  python3 - <<'PY' "$PORT"
import json, sys, time, urllib.request
port = sys.argv[1]
base = f"http://127.0.0.1:{port}"
for _ in range(30):
    with urllib.request.urlopen(base + "/json/list", timeout=3) as resp:
        data = json.loads(resp.read().decode())
    for item in data:
        if item.get("type") == "page" and "mail.google.com" in item.get("url", "") and item.get("webSocketDebuggerUrl"):
            print(item["webSocketDebuggerUrl"])
            raise SystemExit(0)
    time.sleep(0.5)
raise SystemExit(1)
PY
}

if [[ ! -f "$TARGETS_FILE" ]]; then
  echo "missing targets file: $TARGETS_FILE" >&2
  exit 1
fi

if [[ "$(port_is_up)" != "up" ]]; then
  if [[ "$START_CHROME" != "1" ]]; then
    echo "cdp port $PORT is down and START_CHROME=0" >&2
    exit 1
  fi
  "$SKILL_DIR/scripts/start_chrome_cdp_clone.sh" >"$CHROME_LOG" 2>&1 &
  CHROME_PID=$!
  STARTED_CLONE=1
  echo "$CHROME_PID" > "$RUN_DIR/chrome_clone.pid"
  for _ in $(seq 1 "$WAIT_SECONDS"); do
    [[ "$(port_is_up)" == "up" ]] && break
    sleep 1
  done
fi

if [[ "$(port_is_up)" != "up" ]]; then
  echo "failed to start or reach cdp port $PORT" >&2
  exit 1
fi

BROWSER_WS_URL="$(browser_ws_url)"
GMAIL_WS_URL="$("$SKILL_DIR/scripts/gmail_find_page_ws_url.sh" "$PORT" "" "https://mail.google.com/mail/u/0/#inbox")"
if [[ -z "$GMAIL_WS_URL" && -n "$BROWSER_WS_URL" ]]; then
  node "$SKILL_DIR/scripts/chrome_cdp_create_target.mjs" "$BROWSER_WS_URL" "https://mail.google.com/mail/u/0/#inbox" >/dev/null 2>&1 || true
  GMAIL_WS_URL="$(resolve_gmail_page_ws_url || true)"
fi
if ! "$SKILL_DIR/scripts/gmail_smoke_check.sh" "$PORT" >"$SMOKE_LOG" 2>&1; then
  echo "warning: smoke check failed, continuing with resolved gmail ws" >>"$SMOKE_LOG"
fi
if [[ -z "$GMAIL_WS_URL" || -z "$BROWSER_WS_URL" ]]; then
  echo "failed to resolve gmail page or browser websocket (gmail_ws=$GMAIL_WS_URL browser_ws=$BROWSER_WS_URL)" >&2
  exit 1
fi

line_no=0
while IFS=$'\t' read -r provider locator row_needle patient_hint; do
  [[ -z "${provider// }" ]] && continue
  [[ "${provider#\#}" != "$provider" ]] && continue

  line_no=$((line_no + 1))
  slug="$(slugify "${line_no}-${provider}-${locator}")"
  target_raw="$RAW_DIR/$slug"
  target_pdf_text="$PDF_TEXT_DIR/$slug"
  thread_json="$LOG_DIR/$slug.thread.json"
  provider_json="$LOG_DIR/$slug.provider.json"
  stderr_log="$LOG_DIR/$slug.stderr.log"
  pdf_text_manifest="$target_pdf_text/pdf_text_manifest.tsv"
  mkdir -p "$target_raw" "$target_pdf_text"

  row_status="ok"
  portal_url=""
  patient_hint="${patient_hint:-}"

  if ! node "$REPO_ROOT/scripts/gmail_collect_portal_links.mjs" "$GMAIL_WS_URL" "$locator" "${row_needle:-}" >"$thread_json" 2>"$stderr_log"; then
    row_status="thread_fail"
  fi

  if [[ "$row_status" == "ok" ]]; then
    portal_url="$(python3 - <<'PY' "$thread_json" "$provider"
import json, sys
path, provider = sys.argv[1], sys.argv[2].lower()
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)
links = data.get("links", [])
for item in links:
    href = item.get("href", "")
    if provider == "invitro" and ("lk.invitro.ru" in href or "lk3.invitro.ru" in href):
        print(href)
        break
PY
)"
    if [[ -z "$portal_url" ]]; then
      row_status="portal_link_missing"
    fi
  fi

  if [[ "$row_status" == "ok" && -z "${patient_hint:-}" ]]; then
    patient_hint="$(python3 - <<'PY' "$thread_json" "$provider"
import json, re, sys
from urllib.parse import unquote
path, provider = sys.argv[1], sys.argv[2].lower()
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)
attachment_names = [unquote(x) for x in data.get("attachmentNames", [])]
body_snippet = unquote(data.get("bodySnippet", ""))
title = unquote(data.get("title", ""))
hint = ""
if provider == "invitro":
    candidates = attachment_names + [body_snippet, title]
    for name in candidates:
        m = re.search(r'_([A-Za-zА-Яа-яЁё-]+)\.(pdf|jpg|jpeg|png)\b', name, re.IGNORECASE)
        if m:
            hint = m.group(1).lower()
            break
print(hint)
PY
)"
  fi

  if [[ "$row_status" == "ok" ]]; then
    target_json="$(node "$SKILL_DIR/scripts/chrome_cdp_create_target.mjs" "$BROWSER_WS_URL" "$portal_url" 2>>"$stderr_log" || true)"
    target_id="$(printf '%s' "$target_json" | python3 -c 'import json,sys; text=sys.stdin.read().strip(); print(json.loads(text)["targetId"]) if text else None' 2>/dev/null || true)"
    portal_ws_url=""
    if [[ -n "$target_id" ]]; then
      portal_ws_url="$(resolve_page_ws_url "$target_id" || true)"
    fi
    if [[ -z "$target_id" || -z "${portal_ws_url:-}" ]]; then
      row_status="portal_ws_missing"
    fi
  fi

  if [[ "$row_status" == "ok" ]]; then
    case "${provider:l}" in
      invitro)
        if ! node "$REPO_ROOT/providers/invitro_anon_result_from_link.mjs" "$portal_ws_url" "$target_raw" "${patient_hint:-}" >"$provider_json" 2>>"$stderr_log"; then
          row_status="provider_fail"
        fi
        ;;
      *)
        echo "unsupported provider: $provider" >>"$stderr_log"
        row_status="unsupported_provider"
        ;;
    esac
  fi

  python3 "$REPO_ROOT/scripts/extract_pdf_text.py" "$target_raw" "$target_pdf_text" --thread-json "$thread_json" --provider-json "$provider_json" >"$LOG_DIR/$slug.pdf_text.stdout.log" 2>"$LOG_DIR/$slug.pdf_text.stderr.log" || true
  if [[ ! -f "$pdf_text_manifest" ]]; then
    pdf_text_manifest="-"
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$line_no" "$provider" "$locator" "${row_needle:-}" "${patient_hint:-}" "$portal_url" "$row_status" "$target_raw" "$pdf_text_manifest" "$thread_json" "$provider_json" "$stderr_log" \
    >> "$MANIFEST_TSV"
done < "$TARGETS_FILE"

python3 "$REPO_ROOT/scripts/derive_asset_metadata.py" "$RUN_DIR" >"$LOG_DIR/asset_metadata.stdout.log" 2>"$LOG_DIR/asset_metadata.stderr.log" || true

echo "$RUN_DIR"
