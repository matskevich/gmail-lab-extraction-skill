#!/bin/zsh
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: scripts/run_gmail_lab_export.sh <targets.tsv> [run-dir]" >&2
  echo "tsv format: <gmail query><TAB><row needle><TAB><mode?>" >&2
  echo "mode: auto|inline (default: auto)" >&2
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
RUN_DIR_INPUT="${2:-$REPO_ROOT/runs/run-$(date +%Y%m%d-%H%M%S)}"
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
OCR_DIR="$RUN_DIR/ocr"
PDF_TEXT_DIR="$RUN_DIR/pdf_text"
LOG_DIR="$RUN_DIR/logs"
MANIFEST_TSV="$RUN_DIR/run_manifest.tsv"
META_TXT="$RUN_DIR/run_meta.txt"
ASSET_MANIFEST="$RUN_DIR/asset_manifest.tsv"
CHROME_LOG="$LOG_DIR/chrome_clone.log"
SMOKE_LOG="$LOG_DIR/smoke_check.log"

mkdir -p "$RAW_DIR" "$OCR_DIR" "$PDF_TEXT_DIR" "$LOG_DIR"

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

echo -e "line_no\tslug\tmode\tstatus\textracted_count\traw_dir\tocr_manifest\tpdf_text_manifest\tjson_log\tstderr_log\tquery\tneedle" > "$MANIFEST_TSV"

port_is_up() {
  python3 - <<'PY' "$PORT"
import sys
import urllib.request
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
import re
import sys
value = sys.argv[1].strip().lower()
value = re.sub(r"\s+", "-", value)
value = re.sub(r"[^a-z0-9а-яё_-]+", "-", value, flags=re.IGNORECASE)
value = re.sub(r"-{2,}", "-", value).strip("-")
print(value[:80] or "target")
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

"$SKILL_DIR/scripts/gmail_smoke_check.sh" "$PORT" >"$SMOKE_LOG" 2>&1
WS_URL="$("$SKILL_DIR/scripts/gmail_find_page_ws_url.sh" "$PORT")"
if [[ -z "$WS_URL" ]]; then
  echo "failed to resolve gmail page websocket on port $PORT" >&2
  exit 1
fi

line_no=0
while IFS=$'\t' read -r query needle mode; do
  [[ -z "${query// }" ]] && continue
  [[ "${query#\#}" != "$query" ]] && continue

  line_no=$((line_no + 1))
  mode="${mode:-auto}"
  slug="$(slugify "${line_no}-${needle}")"
  target_raw="$RAW_DIR/$slug"
  target_ocr="$OCR_DIR/$slug"
  target_pdf_text="$PDF_TEXT_DIR/$slug"
  json_log="$LOG_DIR/$slug.extract.json"
  stderr_log="$LOG_DIR/$slug.extract.stderr.log"
  ocr_manifest="$target_ocr/ocr_manifest.tsv"
  pdf_text_manifest="$target_pdf_text/pdf_text_manifest.tsv"
  mkdir -p "$target_raw" "$target_ocr" "$target_pdf_text"

  if [[ "$mode" == "inline" ]]; then
    collector=(node "$SKILL_DIR/scripts/gmail_collect_inline_assets_from_query.mjs" "$WS_URL" "$query" "$needle" "$target_raw")
  else
    collector=(node "$SKILL_DIR/scripts/gmail_collect_attachments_from_query.mjs" "$WS_URL" "$query" "$needle" "$target_raw")
  fi

  row_status="ok"
  if ! "${collector[@]}" >"$json_log" 2>"$stderr_log"; then
    row_status="extract_fail"
  fi

  extracted_count="$(python3 - <<'PY' "$json_log" "$row_status"
import json
import sys
path, row_status = sys.argv[1], sys.argv[2]
if row_status != "ok":
    print(0)
    raise SystemExit(0)
try:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    print(len(data.get("saved", [])))
except Exception:
    print(0)
PY
)"

  if [[ "$row_status" == "ok" ]]; then
    python3 "$SKILL_DIR/scripts/ocr_image_assets.py" "$target_raw" "$target_ocr" >"$LOG_DIR/$slug.ocr.stdout.log" 2>"$LOG_DIR/$slug.ocr.stderr.log" || row_status="ocr_fail"
  fi

  python3 "$REPO_ROOT/scripts/extract_pdf_text.py" "$target_raw" "$target_pdf_text" --thread-json "$json_log" >"$LOG_DIR/$slug.pdf_text.stdout.log" 2>"$LOG_DIR/$slug.pdf_text.stderr.log" || true

  if [[ ! -f "$ocr_manifest" ]]; then
    ocr_manifest="-"
  fi
  if [[ ! -f "$pdf_text_manifest" ]]; then
    pdf_text_manifest="-"
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$line_no" "$slug" "$mode" "$row_status" "$extracted_count" "$target_raw" "$ocr_manifest" "$pdf_text_manifest" "$json_log" "$stderr_log" "$query" "$needle" \
    >> "$MANIFEST_TSV"
done < "$TARGETS_FILE"

python3 "$REPO_ROOT/scripts/derive_asset_metadata.py" "$RUN_DIR" >"$LOG_DIR/asset_metadata.stdout.log" 2>"$LOG_DIR/asset_metadata.stderr.log" || true

echo "$RUN_DIR"
