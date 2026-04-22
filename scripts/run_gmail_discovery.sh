#!/bin/zsh
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: scripts/run_gmail_discovery.sh <targets.tsv> [run-dir]" >&2
  echo "tsv format: <gmail query><TAB><row needle><TAB><mode?>" >&2
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
RUN_DIR_INPUT="${2:-$REPO_ROOT/runs/discovery-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="$(python3 - <<'PY' "$RUN_DIR_INPUT"
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
PORT="${PORT:-9222}"
LOCK_DIR="${TMPDIR:-/tmp}/gmail-lab-cdp-port-${PORT}.lock"

LOG_DIR="$RUN_DIR/logs"
MANIFEST_TSV="$RUN_DIR/discovery_manifest.tsv"
META_TXT="$RUN_DIR/run_meta.txt"
SMOKE_LOG="$LOG_DIR/smoke_check.log"

mkdir -p "$LOG_DIR"

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

{
  echo "run_dir=$RUN_DIR"
  echo "targets_file=$TARGETS_FILE"
  echo "port=$PORT"
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$META_TXT"

echo -e "line_no\tslug\tdiscovery_status\tdiscovery_class\tattachment_candidate_count\tdownload_url_count\tinline_candidate_count\tscanning_for_viruses\tjson_log\tstderr_log\tquery\tneedle" > "$MANIFEST_TSV"

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

"$SKILL_DIR/scripts/gmail_smoke_check.sh" "$PORT" >"$SMOKE_LOG" 2>&1
WS_URL="$("$SKILL_DIR/scripts/gmail_find_page_ws_url.sh" "$PORT")"
if [[ -z "$WS_URL" ]]; then
  echo "failed to resolve gmail page websocket on port $PORT" >&2
  exit 1
fi

line_no=0
while IFS=$'\t' read -r query needle _mode; do
  [[ -z "${query// }" ]] && continue
  [[ "${query#\#}" != "$query" ]] && continue

  line_no=$((line_no + 1))
  slug="$(slugify "${line_no}-${needle}")"
  json_log="$LOG_DIR/$slug.discovery.json"
  stderr_log="$LOG_DIR/$slug.discovery.stderr.log"

  row_status="ok"
  if ! node "$SKILL_DIR/scripts/gmail_discover_thread_from_query.mjs" "$WS_URL" "$query" "$needle" >"$json_log" 2>"$stderr_log"; then
    row_status="discover_fail"
  fi

  stats="$(python3 - <<'PY' "$json_log" "$row_status"
import json
import sys
path, row_status = sys.argv[1], sys.argv[2]
if row_status != "ok":
    print("\t".join(["unknown", "0", "0", "0", "false"]))
    raise SystemExit(0)
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)
d = data.get("diagnostics", {})
print("\t".join([
    data.get("discoveryClass", "unknown"),
    str(d.get("attachmentCandidateCount", 0)),
    str(d.get("downloadUrlCount", 0)),
    str(d.get("inlineCandidateCount", 0)),
    str(bool(d.get("scanningForViruses", False))).lower(),
]))
PY
)"

  discovery_class="${stats%%$'\t'*}"
  rest="${stats#*$'\t'}"
  attachment_candidate_count="${rest%%$'\t'*}"
  rest="${rest#*$'\t'}"
  download_url_count="${rest%%$'\t'*}"
  rest="${rest#*$'\t'}"
  inline_candidate_count="${rest%%$'\t'*}"
  scanning_for_viruses="${rest#*$'\t'}"

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$line_no" "$slug" "$row_status" "$discovery_class" "$attachment_candidate_count" "$download_url_count" "$inline_candidate_count" "$scanning_for_viruses" "$json_log" "$stderr_log" "$query" "$needle" \
    >> "$MANIFEST_TSV"
done < "$TARGETS_FILE"

echo "$RUN_DIR"
