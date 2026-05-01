#!/bin/zsh
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: scripts/run_regression_suite.sh <regression_targets.tsv> [run-dir]" >&2
  echo "tsv format: <gmail query><TAB><row needle><TAB><mode?><TAB><min_attachments?><TAB><min_inline?><TAB><note?>" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi
if ! "$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"python >=3.11 required, got {sys.version.split()[0]}; create .venv or set PYTHON_BIN")
PY
then
  exit 1
fi
SKILL_DIR="$REPO_ROOT/skills/gmail-browser-attachments"
TARGETS_FILE="$("$PYTHON_BIN" - <<'PY' "$1"
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
RUN_DIR_INPUT="${2:-$REPO_ROOT/runs/regression-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="$("$PYTHON_BIN" - <<'PY' "$RUN_DIR_INPUT"
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
PORT="${PORT:-9222}"
LOCK_DIR="${TMPDIR:-/tmp}/gmail-lab-cdp-port-${PORT}.lock"

RAW_DIR="$RUN_DIR/raw"
LOG_DIR="$RUN_DIR/logs"
MANIFEST="$RUN_DIR/regression_manifest.tsv"
SUMMARY="$RUN_DIR/regression_summary.tsv"
SMOKE_LOG="$LOG_DIR/smoke_check.log"

mkdir -p "$RAW_DIR" "$LOG_DIR"

acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    return 0
  fi
  lock_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  echo "cdp lock is already held for port $PORT (pid=${lock_pid:-unknown}); do not run live gmail scripts in parallel" >&2
  exit 1
}

release_lock() {
  rm -rf "$LOCK_DIR"
}

acquire_lock
trap release_lock EXIT INT TERM

if [[ ! -f "$TARGETS_FILE" ]]; then
  echo "missing regression targets file: $TARGETS_FILE" >&2
  exit 1
fi

"$SKILL_DIR/scripts/gmail_smoke_check.sh" "$PORT" >"$SMOKE_LOG" 2>&1
WS_URL="$("$SKILL_DIR/scripts/gmail_find_page_ws_url.sh" "$PORT")"
if [[ -z "$WS_URL" ]]; then
  echo "failed to resolve gmail page websocket on port $PORT" >&2
  exit 1
fi

slugify() {
  "$PYTHON_BIN" - <<'PY' "$1"
import re
import sys
value = sys.argv[1].strip().lower()
value = re.sub(r"\s+", "-", value)
value = re.sub(r"[^a-z0-9а-яё_-]+", "-", value, flags=re.IGNORECASE)
value = re.sub(r"-{2,}", "-", value).strip("-")
print(value[:80] or "target")
PY
}

echo -e "line_no\tslug\tstatus\tmin_attachments\tactual_attachments\tmin_inline\tactual_inline\tquery\tneedle\tnote\tjson_log\tstderr_log" > "$MANIFEST"

line_no=0
while IFS=$'\t' read -r query needle mode min_attachments min_inline note; do
  [[ -z "${query// }" ]] && continue
  [[ "${query#\#}" != "$query" ]] && continue

  line_no=$((line_no + 1))
  mode="${mode:-auto}"
  min_attachments="${min_attachments:-0}"
  min_inline="${min_inline:-0}"
  note="${note:-}"
  slug="$(slugify "${line_no}-${needle}")"
  target_raw="$RAW_DIR/$slug"
  json_log="$LOG_DIR/$slug.extract.json"
  stderr_log="$LOG_DIR/$slug.extract.stderr.log"
  mkdir -p "$target_raw"

  if [[ "$mode" == "inline" ]]; then
    collector=(node "$SKILL_DIR/scripts/gmail_collect_inline_assets_from_query.mjs" "$WS_URL" "$query" "$needle" "$target_raw")
  else
    collector=(node "$SKILL_DIR/scripts/gmail_collect_attachments_from_query.mjs" "$WS_URL" "$query" "$needle" "$target_raw")
  fi

  row_status="extract_fail"
  if "${collector[@]}" >"$json_log" 2>"$stderr_log"; then
    row_status="ok"
  fi

  counts="$("$PYTHON_BIN" - <<'PY' "$json_log" "$row_status"
import json
import sys
path, row_status = sys.argv[1], sys.argv[2]
if row_status != "ok":
    print("0\t0")
    raise SystemExit(0)
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)
saved = data.get("saved", [])
attachments = sum(1 for item in saved if item.get("kind") == "attachment")
inline = sum(1 for item in saved if item.get("kind") == "inline")
print(f"{attachments}\t{inline}")
PY
)"

  actual_attachments="${counts%%$'\t'*}"
  actual_inline="${counts#*$'\t'}"

  if [[ "$row_status" == "ok" ]]; then
    if (( actual_attachments < min_attachments )) || (( actual_inline < min_inline )); then
      row_status="assert_fail"
    else
      row_status="pass"
    fi
  fi

  echo -e "${line_no}\t${slug}\t${row_status}\t${min_attachments}\t${actual_attachments}\t${min_inline}\t${actual_inline}\t${query}\t${needle}\t${note}\t${json_log}\t${stderr_log}" >> "$MANIFEST"
done < "$TARGETS_FILE"

"$PYTHON_BIN" "$REPO_ROOT/scripts/summarize_regression_run.py" "$RUN_DIR" "$SUMMARY" >/dev/null

echo "$MANIFEST"
