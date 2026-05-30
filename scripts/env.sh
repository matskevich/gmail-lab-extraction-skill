#!/bin/zsh

# Prefer the repo-local OCR/PDF toolchain when present so runs do not depend on
# system-wide Homebrew or admin rights.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_OCR_ENV="$REPO_ROOT/../.local/envs/gmail-ocr"

if [[ -d "$LOCAL_OCR_ENV/bin" ]]; then
  export PATH="$LOCAL_OCR_ENV/bin:$PATH"
fi
