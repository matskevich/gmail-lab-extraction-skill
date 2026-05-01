# gmail-lab-extraction-skill

agent-first self-hosted open-source toolkit for exporting lab/result history from gmail onto a local computer, preserving raw evidence and deriving usable metadata locally.

agent handoff docs:
- `START_HERE_FOR_AGENTS.md`
- `AGENTS.md`
- `docs/agent_install.md`
- `docs/api_first_architecture.md`
- `docs/self_hosted_product.md`
- `docs/architecture.md`
- `docs/completeness_framework.md`
- `docs/test_strategy.md`
- `docs/release_checklist.md`
- `docs/release_verdict.md`
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

who it is for:
- ai agents that need a replayable filesystem + manifest contract instead of ad hoc browser clicking
- human operators who run the tool locally against their own gmail and want to keep the evidence on disk

python substrate status:
- `gmail_lab/` now contains the first `api-first` local substrate for:
  - app layout under `~/.gmail-lab/`
  - `state.db`
  - message archive
  - evidence archive
  - discovery/evidence/claims/analysis manifests
  - ownership + sample-draw claim derivation
- this is the foundation for the future `gmail api first` lane; current live extraction still happens through the legacy scripts

what it does not do:
- external site login automation
- guaranteed parsing of every encrypted or vector-locked pdf
- generic provider support for every lab portal
- hosted multi-tenant sync

truthful claim:
- this repo can pull analyses that are actually extractable from gmail surface and lay them out locally with explicit provenance + metadata status
- for supported providers, it can also follow tokenized portal links from the email and export the result pdf without manual browser clicks
- it still does not solve arbitrary portal-only cases that require a full username/password/2fa login flow
- current release verdict: `browser-first self-hosted alpha`; see `docs/release_verdict.md`

product direction:
- product boundary: self-hosted, local-first, agent-first, operator-controlled
- production should be `gmail api first`
- browser/cdp should remain a fallback and debugging lane
- see `docs/self_hosted_product.md`, `docs/agent_first_roadmap.md`, and `docs/api_first_architecture.md`

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

by default this copies the bundled Codex skills into `~/.codex/skills/`:

- `gmail-lab-export`
- `gmail-browser-attachments`

to also install the Claude Code skill into `~/.claude/skills/`:

```bash
INSTALL_CLAUDE_SKILLS=1 ./install.sh
```

### option 2: install through codex skill-installer from github

after publishing this repo to github:

```bash
"${PYTHON_BIN:-.venv/bin/python}" "$HOME/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo <owner>/gmail-lab-extraction-skill \
  --path skills/gmail-browser-attachments
```

restart codex after install so the new skill is discovered.

for Claude Code and generic-agent setup, see `docs/agent_install.md`.

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

derive claims after messages and evidence are recorded:

```bash
gmail-lab derive-claims
gmail-lab emit-claims-manifest --output ./claims_manifest.tsv
gmail-lab emit-analysis-manifest --output ./analysis_manifest.tsv
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

## quick self-hosted path

for a new agent/operator pair, the shortest honest path is:

1. prepare a small target file, for example `./tmp/my_targets.tsv`
2. start the chrome cdp clone by running the export script or the bundled skill helper
3. run one logged export into a local run directory
4. inspect the manifests before trusting the final filenames

minimal path:

```bash
mkdir -p ./tmp
cp ./examples/targets.tsv ./tmp/my_targets.tsv
./scripts/run_gmail_lab_export.sh ./tmp/my_targets.tsv ./runs/my-first-run
```

after the run, inspect:
- `./runs/my-first-run/run_manifest.tsv`
- `./runs/my-first-run/asset_manifest.tsv`
- `./runs/my-first-run/raw/`
- `./runs/my-first-run/final/`

read `asset_manifest.tsv` before trusting `final/`. `final/` is a convenience view; rows with `analysis_date_status=fallback` stay in `raw/` as `status=needs_review` until a real artifact, thread, provider, or filename date is recovered.

if you are testing historical mailbox recovery rather than just one export, also run:

```bash
./scripts/run_regression_suite.sh ./tmp/private_regression_targets.tsv ./tmp/live-regression
```

then inspect:
- `./tmp/live-regression/regression_manifest.tsv`
- `./tmp/live-regression/regression_summary.tsv`

run a logged, reproducible extraction batch:

```bash
./scripts/run_gmail_lab_export.sh ./examples/targets.tsv
```

run a live regression corpus against known historical cases:

```bash
./scripts/run_regression_suite.sh ./examples/regression_targets.tsv
```

for real mailbox validation, keep the actual targets in a gitignored local file such as `tmp/private_regression_targets.tsv` instead of committing personal order ids into `examples/`.

each regression run also writes `regression_summary.tsv`, which condenses per-case pass/fail, landed assets, filtered inline noise, and the resolved gmail thread into one agent-readable table.

for a full private validation against the user's personal health lab inventory:

```bash
./scripts/build_health_validation_corpus.py --inventory /path/to/private_inventory.tsv --out-dir ./tmp/health-full-validation-YYYYmmdd
./scripts/run_gmail_discovery.sh ./tmp/health-full-validation-YYYYmmdd/gmail_targets.tsv ./tmp/health-full-validation-YYYYmmdd/discovery
./scripts/run_regression_suite.sh ./tmp/health-full-validation-YYYYmmdd/regression_targets.tsv ./tmp/health-full-validation-YYYYmmdd/regression
./scripts/run_gmail_lab_export.sh ./tmp/health-full-validation-YYYYmmdd/gmail_targets.tsv ./tmp/health-full-validation-YYYYmmdd/export
PORTAL_PATIENT_HINT='<last-name>' ./scripts/run_portal_lab_export.sh ./tmp/health-full-validation-YYYYmmdd/portal_targets.tsv ./tmp/health-full-validation-YYYYmmdd/portal
./scripts/audit_health_validation.py --oracle ./tmp/health-full-validation-YYYYmmdd/oracle.tsv --export-run ./tmp/health-full-validation-YYYYmmdd/export --portal-run ./tmp/health-full-validation-YYYYmmdd/portal --out ./tmp/health-full-validation-YYYYmmdd/coverage_report.md
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

regression runs create:
- `runs/regression-YYYYmmdd-HHMMSS/regression_manifest.tsv`
- `runs/regression-YYYYmmdd-HHMMSS/regression_summary.tsv`
- `runs/regression-YYYYmmdd-HHMMSS/raw/`
- `runs/regression-YYYYmmdd-HHMMSS/logs/`

discovery semantics:
- `discovery_manifest.tsv` answers `what exists in the mailbox and of what class?`
- `run_manifest.tsv` answers `what raw bytes actually landed?`
- `regression_summary.tsv` answers `did the historical case pass cleanly, what landed, what inline noise was filtered, and which gmail thread was actually opened?`
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
invitro	<gmail_message_id_or_locator>	<row_needle?>	<patient_last_name_hint?>
```

if many portal rows use the same patient gate, pass the hint once for the whole run:

```bash
PORTAL_PATIENT_HINT='<last-name>' ./scripts/run_portal_lab_export.sh ./tmp/portal_targets.tsv ./tmp/portal-run
```

when the hint is not in the tsv or env and the script has a tty, it prompts once before processing rows. provider tabs are closed after each row so a batch run should not leave a stack of portal pages open.

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
  - `status` = `ok|missing_raw|non_result|sidecar|needs_review`
- obvious non-result support attachments stay in `raw/`, are marked `non_result`, and are not promoted into `final/`
- formal sidecars such as `.sig` stay in `raw/`, are marked `sidecar`, and are not promoted as clinical result files
- assets whose only date is the run date fallback are marked `needs_review` and are not promoted into `final/`

claims layer:
- `claims_manifest.tsv` records:
  - `owner_name`, `owner_status`, `owner_source`, `owner_evidence`
  - `analysis_date`, `analysis_date_source`
  - `sample_draw_date`, `sample_draw_time`, `sample_draw_datetime`
  - `sample_draw_status`, `sample_draw_source`, `sample_draw_evidence`
  - provider/category/confidence plus evidence refs
- `analysis_manifest.tsv` is the thinner downstream view for sinks and agents
- current owner statuses:
  - `confirmed_owner`
  - `likely_owner`
  - `weak_owner`
  - `unknown_owner`
  - `non_owner`
- current sample-draw statuses:
  - `direct`
  - `inferred_date_only`
  - `proxy_analysis_date`
  - `missing`

password-protected pdf lane:
- the runners also create `pdf_text/<target>/pdf_text_manifest.tsv`
- password values are resolved by `gmail_lab/core/secrets/`; gmail extraction only supplies hints and context
- extraction order is:
  - plain `pdftotext`
  - password-aware `pdftotext` using local secret candidates
  - password-aware `pdftoppm` + `tesseract` OCR fallback
- password candidates can come from:
  - gmail/provider hints such as `password is your birth date DDMMYYYY`
  - local session cache, OS keychain, or encrypted local fallback
  - explicit email text when the email contains a concrete password
  - explicit run-level env hints:
    - `PDF_BIRTH_DATE=<local-birth-date>`
    - `PDF_PASSWORD_CANDIDATES=<candidate-1>,<candidate-2>`
  - an explicit tty prompt through `--prompt-secrets` or `PDF_PASSWORD_PROMPT=1`
- practical run-level example:

```bash
PDF_BIRTH_DATE='<local-birth-date>' \
PDF_PASSWORD_CANDIDATES='<candidate-1>,<candidate-2>' \
./scripts/run_gmail_lab_export.sh ./tmp/my_targets.tsv ./runs/my-first-run
```

- prompt example for a local one-off run:

```bash
./scripts/extract_pdf_text.py ./runs/my-first-run/raw ./tmp/pdf-text-check \
  --prompt-secrets \
  --remember-secret session
```

- persistence choices are `never|session|keychain|encrypted-file`; permanent persistence is opt-in
- manifests keep `password_source`, `secret_scope`, and `secret_persistence`, but redact the concrete password value
- encrypted PDFs with a hint and no available local secret emit `status=needs_password_hint` instead of hanging in non-interactive runs
- `pdf_text_manifest.tsv` status now distinguishes `missing_dependency` from real extraction failure

image-heavy targets:
- if the medical document is an inline image or an attached `.jpg/.png`, `tesseract` is the main dependency
- if the medical document is a scanned PDF, you need both `poppler` (`pdftoppm` / `pdftotext`) and `tesseract`
- `ocr_manifest.tsv` status now distinguishes `missing_dependency` from OCR runtime failure

date policy:
- every promoted result asset gets a date in `final/`
- source priority is:
  - provider result page
  - gmail thread / received date
  - contextual artifact date from OCR or extracted PDF text
  - filename
  - run fallback
- if the date is indirect, the filename still carries it, and `asset_manifest.tsv` keeps the source + status so downstream ingest can tell `direct` from `inferred`
- if the only date is `run_fallback`, the asset is kept out of `final/` with `status=needs_review`

portal boundary:
- current support proves `gmail thread -> tokenized portal link -> provider pdf`
- this is not yet a universal login robot for every lab cabinet
- providers with username/password/2fa/captcha still need separate adapters

release discipline:
- use [docs/release_checklist.md](docs/release_checklist.md) before calling the project ready for public alpha
- keep public examples sanitized and real mailbox regression corpora local under gitignored paths

## feedback and contribution

github is the durable intake:

- bugs: [open a bug report](https://github.com/matskevich/gmail-lab-extraction-skill/issues/new?template=bug_report.yml)
- lab/provider support: [open a provider request](https://github.com/matskevich/gmail-lab-extraction-skill/issues/new?template=provider_request.yml)
- setup help: [open a help request](https://github.com/matskevich/gmail-lab-extraction-skill/issues/new?template=help_request.yml)
- ideas and questions: [start a discussion](https://github.com/matskevich/gmail-lab-extraction-skill/discussions)

privacy rule:
- do not upload real lab files, screenshots with personal data, portal links, cookies, tokens, or unredacted manifests
- read [PRIVACY.md](PRIVACY.md) before opening an issue
- read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR
- use [docs/community_intake.md](docs/community_intake.md) for label and triage rules

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
"${PYTHON_BIN:-.venv/bin/python}" "$HOME/.codex/skills/gmail-browser-attachments/scripts/ocr_image_assets.py" \
  ./downloads \
  ./ocr
```

## examples

see [`examples/targets.tsv`](./examples/targets.tsv) for batch input format.
see [`examples/portal_targets.tsv`](./examples/portal_targets.tsv) for portal-backed export targets.
see [`examples/regression_targets.tsv`](./examples/regression_targets.tsv) for live regression inputs.

## license

MIT. See [`LICENSE`](LICENSE).
