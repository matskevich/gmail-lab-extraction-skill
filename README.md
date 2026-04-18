# gmail-lab-extraction-skill

repo + codex skill for extracting gmail lab/result assets from a logged-in chrome session when gmail connector scopes are insufficient or chrome's normal download flow is flaky.

agent handoff docs:
- `AGENTS.md`
- `docs/api_first_architecture.md`
- `docs/architecture.md`
- `docs/completeness_framework.md`
- `docs/test_strategy.md`
- `docs/goals_review.md`
- `docs/agent_patterns.md`
- `schemas/*.schema.json`

what it does:
- extracts native gmail attachments via cdp
- extracts gmail inline image assets rendered through `view=fimg` / `attid`
- follows tokenized portal links from gmail for supported providers
- runs ocr over extracted image assets
- extracts text from normal and password-hinted PDFs, with OCR fallback for scanned PDFs
- derives `analysis_date` + `owner` metadata and materializes canonical filenames in `final/`
- writes run logs, manifests, and per-target outputs

python substrate status:
- `gmail_lab/` now contains the first `api-first` local substrate for:
  - app layout under `~/.gmail-lab/`
  - `state.db`
  - message archive
  - evidence archive
  - discovery/evidence manifests
- this is the foundation for the future `gmail api first` lane; current live extraction still happens through the legacy scripts

what it does not do:
- external site login automation
- guaranteed parsing of every encrypted or vector-locked pdf
- generic provider support for every lab portal

truthful claim:
- this repo can pull all analyses that are actually extractable from gmail surface
- for supported providers, it can also follow tokenized portal links from the email and export the result pdf without manual browser clicks
- it still does not solve arbitrary portal-only cases that require a full username/password/2fa login flow

product direction:
- production should be `gmail api first`
- browser/cdp should remain a fallback and debugging lane
- see `docs/api_first_architecture.md`

completeness rule:
- historical recovery has two separate goals:
  - `discovery`: prove that candidate mails exist
  - `acquisition`: land raw bytes locally
- partial-ready mails matter for completeness testing even if a later full-ready mail supersedes them in downstream truth

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

bootstrap the local-first substrate:

```bash
gmail-lab init
gmail-lab identity-status
```

run a discovery-only pass before raw acquisition:

```bash
./scripts/run_gmail_discovery.sh ./examples/targets.tsv
```

expected OCR/PDF helpers:
- `tesseract` for image-heavy email assets and OCR fallback
- `pdftotext` for text-first PDF extraction
- `pdftoppm` for scanned/passworded PDF page rendering before OCR

on macOS the practical install is usually:

```bash
brew install tesseract poppler
```

run a logged, reproducible extraction batch:

```bash
./scripts/run_gmail_lab_export.sh ./examples/targets.tsv
```

run a live regression corpus against known historical cases:

```bash
./scripts/run_regression_suite.sh ./examples/regression_targets.tsv
```

re-run only the derivative lanes after installing missing OCR/PDF tools:

```bash
./scripts/rerun_enrichment.py ./runs/run-YYYYmmdd-HHMMSS
```

that creates:
- `runs/run-YYYYmmdd-HHMMSS/raw/`
- `runs/run-YYYYmmdd-HHMMSS/final/`
- `runs/run-YYYYmmdd-HHMMSS/ocr/`
- `runs/run-YYYYmmdd-HHMMSS/pdf_text/`
- `runs/run-YYYYmmdd-HHMMSS/logs/`
- `runs/run-YYYYmmdd-HHMMSS/run_manifest.tsv`
- `runs/run-YYYYmmdd-HHMMSS/asset_manifest.tsv`

discovery-only runs create:
- `runs/discovery-YYYYmmdd-HHMMSS/discovery_manifest.tsv`
- `runs/discovery-YYYYmmdd-HHMMSS/logs/`

discovery semantics:
- `discovery_manifest.tsv` answers `what exists in the mailbox and of what class?`
- `run_manifest.tsv` answers `what raw bytes actually landed?`
- these are different questions and must not be collapsed

run manifest semantics:
- `status` = acquisition only (`ok|extract_fail`)
- `ocr_status` = image OCR lane status
- `pdf_text_status` = PDF text/OCR lane status
- `enrichment_status` = rolled-up derivative status
- missing system tools now show as `missing_dependency`, not as fake download failure

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

password-protected pdf lane:
- the runners also create `pdf_text/<target>/pdf_text_manifest.tsv`
- extraction order is:
  - plain `pdftotext`
  - password-aware `pdftotext` using inferred candidates
  - password-aware `pdftoppm` + `tesseract` OCR fallback
- password candidates can come from:
  - provider metadata such as `birthDate`
  - gmail thread text such as `password is your birth date DDMMYYYY`
  - explicit env hints:
    - `PDF_BIRTH_DATE=1984-10-26`
    - `PDF_PASSWORD_CANDIDATES=26101984,19841026`
- manifests keep `password_source`, but redact the concrete password value
- `pdf_text_manifest.tsv` status now distinguishes `missing_dependency` from real extraction failure

image-heavy targets:
- if the medical document is an inline image or an attached `.jpg/.png`, `tesseract` is the main dependency
- if the medical document is a scanned PDF, you need both `poppler` (`pdftoppm` / `pdftotext`) and `tesseract`
- `ocr_manifest.tsv` status now distinguishes `missing_dependency` from OCR runtime failure

date policy:
- every exported asset gets a date in `final/`
- source priority is:
  - provider result page
  - gmail thread / received date
  - contextual artifact date from OCR or extracted PDF text
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
see [`examples/regression_targets.tsv`](./examples/regression_targets.tsv) for live regression inputs.
