---
name: gmail-browser-attachments
description: Extract Gmail lab/result assets from a logged-in Google Chrome session via Chrome DevTools Protocol when Gmail MCP lacks scopes or Gmail's normal download flow is unreliable. Use it to pull PDF, JPG, PNG, or Gmail inline image assets into the local workspace from search queries, specific order IDs, or known Gmail threads, then OCR image-based results.
---

# Gmail Browser Attachments

use this skill when:
- the Gmail connector can see the mailbox but cannot download attachments because of scope gaps
- manual browser download is unreliable because PDFs or images open in a viewer and never land on disk
- you need more than native attachments, including inline result images rendered in the email body
- you need OCR after extraction for image-based lab results
- you already have a logged-in Chrome profile and the task is read-only mailbox extraction

## core idea

do not depend on AppleScript JS injection or the normal Chrome download manager.

instead:
1. launch a cloned Chrome profile with `--remote-debugging-port`
2. connect to the Gmail page through Chrome DevTools Protocol
3. read `download_url` or Gmail inline asset URLs in page context
4. call `fetch(..., { credentials: 'include' })`
5. stream bytes back over CDP and write the file locally

this avoids:
- cross-origin cookie problems
- disabled `allow javascript from apple events`
- flaky Gmail preview and download behavior

covered asset classes:
- `native attachments`: PDFs, JPGs, PNGs, and other Gmail attachments with `download_url`
- `gmail inline image assets`: images rendered through `view=fimg` / `attid`
- `ocr lane`: OCR over extracted image results
- `passworded pdf text lane`: `pdftotext` first, then password-aware OCR fallback when hints are available

not covered:
- `portal-link / personal cabinet` cases with no Gmail attachment surface
- provider flows that require a separate username/password login
- guaranteed parsing of every encrypted or vector-locked PDF

## quick start

1. start a cloned Chrome profile in a separate shell:
```bash
"$HOME/.codex/skills/gmail-browser-attachments/scripts/start_chrome_cdp_clone.sh"
```

2. find the Gmail page websocket:
```bash
WS_URL="$("$HOME/.codex/skills/gmail-browser-attachments/scripts/gmail_find_page_ws_url.sh" 9222)"
echo "$WS_URL"
```

3. run a sanity check:
```bash
node "$HOME/.codex/skills/gmail-browser-attachments/scripts/chrome_cdp_eval.mjs" \
  "$WS_URL" \
  'document.title'
```

or use the one-shot check:
```bash
"$HOME/.codex/skills/gmail-browser-attachments/scripts/gmail_smoke_check.sh" 9222
```

4. fetch one attachment by needle:
```bash
node "$HOME/.codex/skills/gmail-browser-attachments/scripts/gmail_fetch_attachment_via_cdp.mjs" \
  "$WS_URL" \
  'order-123' \
  ./downloads
```

5. collect native attachments and inline assets from a query:
```bash
node "$HOME/.codex/skills/gmail-browser-attachments/scripts/gmail_collect_attachments_from_query.mjs" \
  "$WS_URL" \
  'from:lab@example.com order-123' \
  'order-123' \
  ./downloads
```

6. collect only inline images:
```bash
node "$HOME/.codex/skills/gmail-browser-attachments/scripts/gmail_collect_inline_assets_from_query.mjs" \
  "$WS_URL" \
  'from:sender@example.com after:2024-01-01 before:2024-01-31' \
  'Result' \
  ./downloads
```

7. OCR image assets:
```bash
python3 "$HOME/.codex/skills/gmail-browser-attachments/scripts/ocr_image_assets.py" \
  ./downloads \
  ./ocr
```

dependency note:
- `tesseract` is required for image-heavy targets
- `pdftotext` and `pdftoppm` are required for passworded or scanned PDF text extraction
- on macOS the practical install is:
```bash
brew install tesseract poppler
```

8. if a PDF is password-protected, pass hints to the repo runner or the text extractor:
```bash
python3 ./scripts/extract_pdf_text.py ./downloads ./pdf_text \
  --prompt-secrets \
  --remember-secret session
```

password policy:
- email/provider text supplies hints, not secret values
- local runtime supplies secrets through prompt, session cache, keychain, encrypted local fallback, or env for automation
- never persist the concrete password in manifests; only keep redacted `password_source`, `secret_scope`, and `secret_persistence`

status policy:
- treat `status` in `run_manifest.tsv` as acquisition only
- read `ocr_status`, `pdf_text_status`, and `enrichment_status` before calling a run “failed”
- if OCR/PDF helpers are absent, expect `missing_dependency` rather than `extract_fail`
- after installing missing helpers, prefer `./scripts/rerun_enrichment.py <run-dir>` over re-downloading the same raw assets

proven live cases:
- a recent medical-result email with a native PDF attachment -> PDF extracted
- a historical email with only inline images -> `7 jpg` extracted + `7 txt` via OCR

## batch mode

TSV format:
```tsv
from:lab@example.com order-123	order-123
from:provider@example.com claim-456	claim-456
```

run:
```bash
"$HOME/.codex/skills/gmail-browser-attachments/scripts/gmail_collect_batch_from_tsv.sh" \
  "$WS_URL" \
  ./targets.tsv \
  ./downloads
```

## workflow rules

- prefer a cloned profile; Chrome blocks remote debugging on the default data dir
- keep the clone read-only from the mailbox perspective unless the user explicitly asks for mutation
- write downloads into a caller-provided folder first; taxonomy or promotion happens later
- if you need a different Chrome profile, set `PROFILE_DIR=Profile 1` before `start_chrome_cdp_clone.sh`
- if login state in the clone is stale, rerun with `REFRESH_PROFILE=1`

## failure modes

- `DevTools remote debugging requires a non-default data directory`
  use `start_chrome_cdp_clone.sh`

- `no attachments found for row`
  first hypothesis: Gmail hydrated the thread slowly
  second hypothesis: the email has no real Gmail attachment and only a portal link
  third hypothesis: the row needle matched the wrong conversation

- inline asset extraction returns noise
  logos or tiny icons can leak in; prefer bounded sender/date queries

- OCR output is weak
  the image may be low-resolution, rotated, or embedded in a PDF that this lane does not parse

- passworded PDF still fails
  first hypothesis: the thread/provider context never exposed the password rule
  second hypothesis: the password pattern is provider-specific and needs an explicit hint
  third hypothesis: the PDF is image-only and needs OCR fallback

- repeated duplicates or ugly filenames
  the scripts sanitize names and suffix duplicates, but dedupe should still happen before promotion into a truth layer

- Gmail page websocket not found
  confirm the cloned Chrome is still running and `mail.google.com` is open

## scripts

- `scripts/start_chrome_cdp_clone.sh`
  clone a local Chrome profile into `/tmp` and launch Chrome with CDP enabled

- `scripts/gmail_find_page_ws_url.sh`
  return the first Gmail page websocket from the local CDP endpoint

- `scripts/chrome_cdp_eval.mjs`
  evaluate arbitrary JS on a page websocket

- `scripts/gmail_inbox_snapshot.mjs`
  print inbox page title, URL, and the first visible rows

- `scripts/gmail_smoke_check.sh`
  answer `is the stack alive right now?`

- `scripts/gmail_fetch_attachment_via_cdp.mjs`
  fetch one native attachment or inline image from the current Gmail thread by needle

- `scripts/gmail_collect_attachments_from_query.mjs`
  drive search -> open row -> expand thread -> fetch visible native attachments and inline image assets

- `scripts/gmail_collect_inline_assets_from_query.mjs`
  fetch only inline images from a query or thread

- `scripts/gmail_collect_batch_from_tsv.sh`
  iterate `query<TAB>needle` targets for repeated extraction

- `scripts/ocr_image_assets.py`
  OCR extracted image assets into `.txt` files plus `ocr_manifest.tsv`
