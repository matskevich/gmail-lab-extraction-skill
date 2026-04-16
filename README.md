# gmail-lab-extraction-skill

repo + codex skill for extracting gmail lab/result assets from a logged-in chrome session when gmail connector scopes are insufficient or chrome's normal download flow is flaky.

agent handoff docs:
- `AGENTS.md`
- `docs/architecture.md`
- `docs/goals_review.md`
- `docs/agent_patterns.md`
- `schemas/*.schema.json`

what it does:
- extracts native gmail attachments via cdp
- extracts gmail inline image assets rendered through `view=fimg` / `attid`
- follows tokenized portal links from gmail for supported providers
- runs ocr over extracted image assets
- derives `analysis_date` + `owner` metadata and materializes canonical filenames in `final/`
- writes run logs, manifests, and per-target outputs

what it does not do:
- external site login automation
- guaranteed parsing of encrypted or vector-locked pdfs
- generic provider support for every lab portal

truthful claim:
- this repo can pull all analyses that are actually extractable from gmail surface
- for supported providers, it can also follow tokenized portal links from the email and export the result pdf without manual browser clicks
- it still does not solve arbitrary portal-only cases that require a full username/password/2fa login flow

## install

### option 1: install from local clone

```bash
./install.sh
```

by default this copies the bundled skill into `~/.codex/skills/gmail-browser-attachments`.

### option 2: install through codex skill-installer from github

after publishing this repo to github:

```bash
python3 "$HOME/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo <owner>/gmail-lab-extraction-skill \
  --path skills/gmail-browser-attachments
```

restart codex after install so the new skill is discovered.

## repo use

check environment:

```bash
./scripts/doctor.sh
```

run a logged, reproducible extraction batch:

```bash
./scripts/run_gmail_lab_export.sh ./examples/targets.tsv
```

that creates:
- `runs/run-YYYYmmdd-HHMMSS/raw/`
- `runs/run-YYYYmmdd-HHMMSS/final/`
- `runs/run-YYYYmmdd-HHMMSS/ocr/`
- `runs/run-YYYYmmdd-HHMMSS/logs/`
- `runs/run-YYYYmmdd-HHMMSS/run_manifest.tsv`
- `runs/run-YYYYmmdd-HHMMSS/asset_manifest.tsv`

tsv format:

```tsv
from:lab@example.com order-123	order-123	auto
from:provider@example.com after:2024-01-01 before:2024-01-31	Result	inline
```

third column is optional:
- `auto` = native attachments + gmail inline image assets
- `inline` = only inline image assets

run portal-backed export:

```bash
./scripts/run_portal_lab_export.sh ./examples/portal_targets.tsv
```

portal tsv format:

```tsv
invitro	<gmail_message_id_or_locator>
```

current portal support:
- `invitro`
  - opens gmail thread by direct gmail id or locator
  - extracts anonymized invitro result link from the email body
  - opens provider page in the chrome clone
  - clicks `Download`
  - captures the real pdf endpoint and saves the pdf locally

metadata layer:
- `raw/` stays provenance-safe and unmodified
- `final/` contains canonical filenames with date/provider/owner prefixes
- `asset_manifest.tsv` records:
  - `analysis_date`
  - `analysis_date_source`
  - `analysis_date_status` = `direct|inferred|fallback`
  - `owner_name`
  - `owner_source`
  - `owner_status` = `likely_owner|weak_owner|unknown_owner`
  - provider + confidence

date policy:
- every exported asset gets a date in `final/`
- source priority is:
  - provider result page
  - gmail thread / received date
  - contextual OCR date on the artifact
  - filename
  - run fallback
- if the date is indirect, the filename still carries it, and `asset_manifest.tsv` keeps the source + status so downstream ingest can tell `direct` from `inferred`

portal boundary:
- current support proves `gmail thread -> tokenized portal link -> provider pdf`
- this is not yet a universal login robot for every lab cabinet
- providers with username/password/2fa/captcha still need separate adapters

## skill use

```bash
"$HOME/.codex/skills/gmail-browser-attachments/scripts/start_chrome_cdp_clone.sh"
```

```bash
WS_URL="$("$HOME/.codex/skills/gmail-browser-attachments/scripts/gmail_find_page_ws_url.sh" 9222)"
```

```bash
"$HOME/.codex/skills/gmail-browser-attachments/scripts/gmail_smoke_check.sh" 9222
```

```bash
node "$HOME/.codex/skills/gmail-browser-attachments/scripts/gmail_collect_attachments_from_query.mjs" \
  "$WS_URL" \
  'from:lab@example.com newer_than:7d' \
  'Lab Result' \
  ./downloads
```

```bash
python3 "$HOME/.codex/skills/gmail-browser-attachments/scripts/ocr_image_assets.py" \
  ./downloads \
  ./ocr
```

## examples

see [`examples/targets.tsv`](./examples/targets.tsv) for batch input format.
see [`examples/portal_targets.tsv`](./examples/portal_targets.tsv) for portal-backed export targets.
