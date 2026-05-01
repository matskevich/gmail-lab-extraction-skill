#!/bin/zsh
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: scripts/run_portal_lab_export.sh <portal_targets.tsv> [run-dir]" >&2
  echo "tsv format: <provider><TAB><locator><TAB><rowNeedle?><TAB><patientHint?>" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi
SKILL_DIR="$REPO_ROOT/skills/gmail-browser-attachments"
TARGETS_FILE="$("$PYTHON_BIN" - <<'PY' "$1"
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
RUN_DIR_INPUT="${2:-$REPO_ROOT/runs/portal-run-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="$("$PYTHON_BIN" - <<'PY' "$RUN_DIR_INPUT"
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
PORT="${PORT:-9222}"
START_CHROME="${START_CHROME:-1}"
WAIT_SECONDS="${WAIT_SECONDS:-30}"
STOP_CHROME_ON_EXIT="${STOP_CHROME_ON_EXIT:-1}"
LOCK_DIR="${TMPDIR:-/tmp}/gmail-lab-cdp-port-${PORT}.lock"
GLOBAL_PATIENT_HINT="${PORTAL_PATIENT_HINT:-}"
PROMPT_PORTAL_PATIENT_HINT="${PROMPT_PORTAL_PATIENT_HINT:-1}"

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
  rm -rf "$LOCK_DIR"
}

acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    return 0
  fi
  lock_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  echo "cdp lock is already held for port $PORT (pid=${lock_pid:-unknown}); do not run live gmail scripts in parallel" >&2
  exit 1
}

acquire_lock
trap cleanup EXIT INT TERM

{
  echo "run_dir=$RUN_DIR"
  echo "targets_file=$TARGETS_FILE"
  echo "port=$PORT"
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$META_TXT"

echo -e "line_no\tprovider\tlocator\trow_needle\tpatient_hint\tportal_url\tstatus\tpdf_text_status\tenrichment_status\traw_dir\tpdf_text_manifest\tthread_json\tprovider_json\tstderr_log" > "$MANIFEST_TSV"

port_is_up() {
  "$PYTHON_BIN" - <<'PY' "$PORT"
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
  "$PYTHON_BIN" - <<'PY' "$1"
import re, sys
value = sys.argv[1].strip().lower()
value = re.sub(r"\s+", "-", value)
value = re.sub(r"[^a-z0-9а-яё_-]+", "-", value, flags=re.IGNORECASE)
value = re.sub(r"-{2,}", "-", value).strip("-")
print(value[:80] or "target")
PY
}

browser_ws_url() {
  "$PYTHON_BIN" - <<'PY' "$PORT"
import json, sys, urllib.request
port = sys.argv[1]
with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as resp:
    data = json.loads(resp.read().decode())
print(data.get("webSocketDebuggerUrl", ""))
PY
}

resolve_page_ws_url() {
  "$PYTHON_BIN" - <<'PY' "$PORT" "$1"
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
  "$PYTHON_BIN" - <<'PY' "$PORT"
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

summarize_pdf_text_manifest_status() {
  "$PYTHON_BIN" - <<'PY' "$1"
import csv
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print("not_applicable")
    raise SystemExit(0)
rows = list(csv.DictReader(path.open("r", encoding="utf-8"), delimiter="\t"))
if not rows:
    print("not_applicable")
    raise SystemExit(0)
statuses = {row.get("status", "") for row in rows}
ok_statuses = {"ok_text", "ok_ocr"}
if statuses and statuses <= ok_statuses:
    print("ok")
elif "needs_password_hint" in statuses and statuses <= (ok_statuses | {"needs_password_hint"}):
    print("partial" if statuses & ok_statuses else "needs_password_hint")
elif "missing_dependency" in statuses and statuses <= (ok_statuses | {"missing_dependency"}):
    print("partial" if statuses & ok_statuses else "missing_dependency")
elif "fail" in statuses and statuses <= (ok_statuses | {"fail"}):
    print("partial" if statuses & ok_statuses else "fail")
elif "needs_password_hint" in statuses or "missing_dependency" in statuses or "fail" in statuses:
    if statuses & ok_statuses:
        print("partial")
    elif "fail" in statuses:
        print("fail")
    elif "needs_password_hint" in statuses:
        print("needs_password_hint")
    else:
        print("missing_dependency")
else:
    print("unknown")
PY
}

combine_enrichment_status() {
  "$PYTHON_BIN" - <<'PY' "$1" "$2"
import sys

row_status, pdf_status = sys.argv[1:3]
if row_status != "ok":
    print("blocked_by_extract_fail")
    raise SystemExit(0)
if pdf_status == "not_applicable":
    print("not_applicable")
elif pdf_status in {"ok", "missing_dependency", "needs_password_hint", "fail", "partial", "unknown"}:
    print(pdf_status)
else:
    print("unknown")
PY
}

has_missing_patient_hint() {
  "$PYTHON_BIN" - <<'PY' "$TARGETS_FILE"
import csv
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)
with path.open("r", encoding="utf-8", newline="") as fh:
    for row in csv.reader(fh, delimiter="\t"):
        if not row or not "".join(row).strip() or row[0].lstrip().startswith("#"):
            continue
        provider = row[0].strip().lower()
        hint = row[3].strip() if len(row) > 3 else ""
        if provider == "invitro" and not hint:
            print("yes")
            raise SystemExit(0)
print("no")
PY
}

maybe_prompt_patient_hint_once() {
  if [[ -n "$GLOBAL_PATIENT_HINT" || "$PROMPT_PORTAL_PATIENT_HINT" != "1" ]]; then
    return
  fi
  if [[ "$(has_missing_patient_hint)" != "yes" ]]; then
    return
  fi
  if [[ -r /dev/tty && -w /dev/tty ]]; then
    printf 'portal patient last-name hint (blank to keep per-row/auto only): ' > /dev/tty
    IFS= read -r GLOBAL_PATIENT_HINT < /dev/tty || GLOBAL_PATIENT_HINT=""
  fi
}

close_target() {
  local target_id_to_close="${1:-}"
  local stderr_log_to_use="${2:-/dev/null}"
  if [[ -n "$target_id_to_close" && -n "$BROWSER_WS_URL" ]]; then
    node "$SKILL_DIR/scripts/chrome_cdp_close_target.mjs" "$BROWSER_WS_URL" "$target_id_to_close" >>"$stderr_log_to_use" 2>&1 || true
  fi
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

maybe_prompt_patient_hint_once

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
  pdf_text_status="not_applicable"
  portal_url=""
  patient_hint="${patient_hint:-}"
  target_id=""
  retry_target_id=""

  if [[ -z "$patient_hint" && -n "$GLOBAL_PATIENT_HINT" ]]; then
    patient_hint="$GLOBAL_PATIENT_HINT"
  fi

  if ! node "$REPO_ROOT/scripts/gmail_collect_portal_links.mjs" "$GMAIL_WS_URL" "$locator" "${row_needle:-}" >"$thread_json" 2>"$stderr_log"; then
    row_status="thread_fail"
  fi

  if [[ "$row_status" == "ok" ]]; then
    portal_url="$("$PYTHON_BIN" - <<'PY' "$thread_json" "$provider"
import json, sys
from urllib.parse import urlparse, parse_qs
path, provider = sys.argv[1], sys.argv[2].lower()
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)
links = data.get("links", [])
for item in links:
    href = item.get("href", "")
    if provider == "invitro" and ("lk.invitro.ru" in href or "lk3.invitro.ru" in href):
        parsed = urlparse(href)
        query = parse_qs(parsed.query)
        if query.get("key"):
            print(href)
            break
PY
)"
    if [[ -z "$portal_url" ]]; then
      row_status="portal_link_missing_or_non_tokenized"
    fi
  fi

  if [[ "$row_status" == "ok" && -z "${patient_hint:-}" ]]; then
    patient_hint="$("$PYTHON_BIN" - <<'PY' "$thread_json" "$provider"
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
    target_id="$(printf '%s' "$target_json" | "$PYTHON_BIN" -c 'import json,sys; text=sys.stdin.read().strip(); print(json.loads(text)["targetId"]) if text else None' 2>/dev/null || true)"
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
          echo "provider adapter failed; retrying once with a fresh portal target" >>"$stderr_log"
          close_target "$target_id" "$stderr_log"
          target_id=""
          retry_target_json="$(node "$SKILL_DIR/scripts/chrome_cdp_create_target.mjs" "$BROWSER_WS_URL" "$portal_url" 2>>"$stderr_log" || true)"
          retry_target_id="$(printf '%s' "$retry_target_json" | "$PYTHON_BIN" -c 'import json,sys; text=sys.stdin.read().strip(); print(json.loads(text)["targetId"]) if text else None' 2>/dev/null || true)"
          retry_portal_ws_url=""
          if [[ -n "$retry_target_id" ]]; then
            retry_portal_ws_url="$(resolve_page_ws_url "$retry_target_id" || true)"
          fi
          if [[ -z "$retry_target_id" || -z "${retry_portal_ws_url:-}" ]] || ! node "$REPO_ROOT/providers/invitro_anon_result_from_link.mjs" "$retry_portal_ws_url" "$target_raw" "${patient_hint:-}" >"$provider_json" 2>>"$stderr_log"; then
            row_status="provider_fail"
          fi
        fi
        ;;
      *)
        echo "unsupported provider: $provider" >>"$stderr_log"
        row_status="unsupported_provider"
        ;;
    esac
  fi

  if [[ "$row_status" == "ok" ]]; then
    "$PYTHON_BIN" "$REPO_ROOT/scripts/extract_pdf_text.py" "$target_raw" "$target_pdf_text" --thread-json "$thread_json" --provider-json "$provider_json" >"$LOG_DIR/$slug.pdf_text.stdout.log" 2>"$LOG_DIR/$slug.pdf_text.stderr.log" || true
  fi
  if [[ ! -f "$pdf_text_manifest" ]]; then
    pdf_text_manifest="-"
  else
    pdf_text_status="$(summarize_pdf_text_manifest_status "$pdf_text_manifest")"
  fi
  enrichment_status="$(combine_enrichment_status "$row_status" "$pdf_text_status")"

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$line_no" "$provider" "$locator" "${row_needle:-}" "${patient_hint:-}" "$portal_url" "$row_status" "$pdf_text_status" "$enrichment_status" "$target_raw" "$pdf_text_manifest" "$thread_json" "$provider_json" "$stderr_log" \
    >> "$MANIFEST_TSV"

  close_target "$target_id" "$stderr_log"
  close_target "$retry_target_id" "$stderr_log"
done < "$TARGETS_FILE"

"$PYTHON_BIN" "$REPO_ROOT/scripts/derive_asset_metadata.py" "$RUN_DIR" >"$LOG_DIR/asset_metadata.stdout.log" 2>"$LOG_DIR/asset_metadata.stderr.log" || true

echo "$RUN_DIR"
