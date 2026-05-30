#!/bin/zsh
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: scripts/run_onboarder_email_sync.sh <targets.tsv> <cds_client_dir_name> [run-name]" >&2
  echo "example: scripts/run_onboarder_email_sync.sh ./examples/targets.tsv openclaw_ilya-mutovin weekly-onboarder-20260417" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$REPO_ROOT/scripts/env.sh"

TARGETS_FILE="$(python3 - <<'PY' "$1"
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"
CDS_CLIENT_DIR_NAME="$2"
RUN_NAME_INPUT="${3:-${ONBOARDER_RUN_PREFIX:-email-onboarder}-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR_INPUT="$REPO_ROOT/runs/$RUN_NAME_INPUT"
RUN_DIR="$(python3 - <<'PY' "$RUN_DIR_INPUT"
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"

CDS_RAW_ROOT="${CDS_RAW_ROOT:-/srv/integrations/cds/raw}"
if [[ ! -d "$CDS_RAW_ROOT" ]]; then
  cat >&2 <<EOF
missing CDS_RAW_ROOT directory: $CDS_RAW_ROOT
hint: on macOS this path may not exist. Set CDS_RAW_ROOT to a mounted CDS raw folder, e.g.
  CDS_RAW_ROOT=/path/to/mounted/cds/raw ./scripts/run_onboarder_email_sync.sh "$TARGETS_FILE" "$CDS_CLIENT_DIR_NAME" "$RUN_NAME_INPUT"
EOF
  exit 1
fi

"$REPO_ROOT/scripts/doctor.sh"
"$REPO_ROOT/scripts/run_gmail_lab_export.sh" "$TARGETS_FILE" "$RUN_DIR"
python3 "$REPO_ROOT/scripts/sync_run_to_cds.py" "$RUN_DIR" "$CDS_CLIENT_DIR_NAME" --cds-raw-root "$CDS_RAW_ROOT"

python3 - <<'PY' "$RUN_DIR"
import csv
import sys
from collections import Counter
from pathlib import Path

run_dir = Path(sys.argv[1])
manifest = run_dir / "run_manifest.tsv"
rows = list(csv.DictReader(manifest.open(encoding="utf-8"), delimiter="\t"))
status_counts = Counter(row["status"] for row in rows)
print(f"run_dir={run_dir}")
print(f"status_counts={dict(status_counts)}")
print(f"target_count={len(rows)}")
if any(status != "ok" for status in status_counts):
    raise SystemExit(1)
PY
