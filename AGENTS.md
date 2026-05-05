# gmail-lab-extraction-skill agent contract

purpose:
- extract lab/result artifacts from gmail and supported portal links into local files
- preserve provenance in `raw/`
- derive machine-usable metadata in `asset_manifest.tsv`
- materialize human-usable canonical names in `final/`

read this first if you are a new agent:
1. `START_HERE_FOR_AGENTS.md`
2. `README.md`
3. `docs/agent_install.md`
4. `docs/google_api_setup.md`
5. `docs/acquisition_auth_router.md`
6. `docs/api_first_architecture.md`
7. `docs/architecture.md`
8. `docs/completeness_framework.md`
9. `docs/test_strategy.md`
10. `docs/goals_review.md`
11. `schemas/*.schema.json`

current truth:
- gmail api native attachments: working through `scripts/run_gmail_api_export.py` when OAuth/token is available
- gmail native attachments: working
- gmail inline image assets: working
- image OCR lane: working
- password-hinted PDF text extraction: working
- metadata derivation for `analysis_date` and `owner`: working on gmail runs
- portal-backed invitro export for anonymous result links: working
- long-term production direction: `gmail api first`, browser fallback second
- python package substrate:
  - `gmail_lab/core/store/state.py`
  - `gmail_lab/core/store/messages.py`
  - `gmail_lab/core/store/evidence.py`
  - `gmail_lab/core/claims/derive.py`
  - `gmail_lab/core/claims/ownership.py`
  - `gmail_lab/core/claims/sample_date.py`
  - `gmail_lab/core/manifests/discovery.py`
  - `gmail_lab/core/manifests/evidence.py`
  - `gmail_lab/core/manifests/claims.py`
  - `gmail_lab/core/manifests/analyses.py`
  - `gmail_lab/transports/cli.py`
  - this layer is the start of the agent-first replayable core; it should stay deterministic and log-independent

known sharp edge:
- historical partial-ready mails can regress if attachment controls hydrate only after scroll or delayed Gmail rendering
- browser/CDP profile clones can lose Gmail auth; `gmail_not_authenticated` is an acquisition/auth blocker, not a PDF password result
- keep old cases in a regression corpus; one recent green smoke run is not enough

non-goals:
- this repo is not a generic browser automation framework
- this repo is not a universal lab-login robot
- this repo should not mutate mailbox state by default

repo entrypoints:
- agent packaging:
  - `skills/gmail-lab-export`
  - `skills/gmail-browser-attachments`
  - `.claude/skills/gmail-lab-export`
  - `docs/agent_install.md`
- `./scripts/doctor.sh`
- `gmail-lab diagnose-gmail-acquisition`
- `./scripts/run_gmail_discovery.sh ./examples/targets.tsv`
- `./scripts/run_gmail_api_export.py ./examples/targets.tsv ./runs/gmail-api-run`
- `./scripts/run_gmail_lab_export.sh ./examples/targets.tsv`
- `./scripts/run_regression_suite.sh ./examples/regression_targets.tsv`
- `./scripts/run_portal_lab_export.sh ./examples/portal_targets.tsv`
- `./scripts/rerun_enrichment.py ./runs/<existing-run>` after missing OCR/PDF binaries are installed
- `gmail-lab derive-claims`
- `gmail-lab emit-claims-manifest --output ./claims_manifest.tsv`
- `gmail-lab emit-analysis-manifest --output ./analysis_manifest.tsv`

artifact contract:
- `discovery_manifest.tsv` = per-target mailbox discovery truth
- `evidence_manifest.tsv` = per-file raw evidence truth for the new local substrate
- `claims_manifest.tsv` = per-file owner/date/sample-draw truth with provenance
- `analysis_manifest.tsv` = thinner downstream table for sinks and agents
- `raw/` = provenance-safe extracted files, never renamed in place
- `ocr/` = OCR derivatives for image assets
- `pdf_text/` = extracted or OCR'd text for PDF assets, including password-hinted PDFs
- `final/` = canonical filenames with `date__provider__owner__original`
- `run_manifest.tsv` = per-target execution log
- `asset_manifest.tsv` = per-file metadata truth layer for downstream ingest
- `discovery_manifest.tsv` must exist before claiming mailbox completeness
- `run_manifest.tsv/status` means acquisition only; enrichment lives in `ocr_status`, `pdf_text_status`, `enrichment_status`

date policy:
- every artifact must end with an `analysis_date`
- source priority:
1. provider page
2. gmail thread / received date
 3. contextual artifact date from OCR or PDF text
4. filename
5. run fallback
- keep the source in `asset_manifest.tsv`; do not hide an inferred date behind a clean filename

owner policy:
- never silently claim ownership when the evidence is weak
- preferred statuses:
  - `confirmed_owner`
  - `likely_owner`
  - `weak_owner`
  - `unknown_owner`
  - `non_owner`
- ambiguous rows must remain explicit

sample draw policy:
- keep `sample_draw_datetime` distinct from `analysis_date` and `message.internal_date`
- if only the date is explicit, use:
  - `sample_draw_date=<yyyy-mm-dd>`
  - `sample_draw_status=inferred_date_only`
- if sample draw is missing but analysis date exists, use:
  - `sample_draw_status=proxy_analysis_date`
- never silently collapse these into one date field

enrichment policy:
- do not mark a row as failed just because OCR helpers are missing
- prefer `missing_dependency` over generic `fail` when `tesseract`, `pdftotext`, or `pdftoppm` are absent
- raw evidence can be `ok` while enrichment is still blocked

safe change rules:
- prefer adding new provider adapters over complicating the gmail collectors
- keep password inference in the PDF text lane, not in the collectors
- prefer new manifest fields over implicit parsing assumptions
- keep modules small and single-purpose
- if you add a new status or column, update:
  - `README.md`
  - `docs/architecture.md`
  - `docs/goals_review.md`
  - matching file in `schemas/`

anti-patterns:
- mixing raw extraction with truth claims
- inferring provider from incidental URLs or JSON keys
- trusting OCR dates without context
- renaming files in `raw/`
- adding portal login logic into gmail-only collectors

next likely work:
- add more provider adapters only after the current transport pattern stays stable across more live cases
- improve owner/date extraction with provider-specific parsers once more real cases exist
