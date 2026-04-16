#!/bin/zsh
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: gmail_collect_batch_from_tsv.sh <ws-url> <targets.tsv> <output-dir>" >&2
  echo "tsv format: <gmail search query><TAB><row needle>" >&2
  exit 2
fi

WS_URL="$1"
TSV_FILE="$2"
OUTPUT_DIR="$3"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

while IFS=$'\t' read -r query needle; do
  [[ -z "${query:-}" ]] && continue
  echo "=== $needle ==="
  node "$SCRIPT_DIR/gmail_collect_attachments_from_query.mjs" "$WS_URL" "$query" "$needle" "$OUTPUT_DIR"
done < "$TSV_FILE"
