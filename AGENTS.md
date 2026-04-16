# gmail-lab-extraction-skill agent contract

purpose:
- extract lab/result artifacts from gmail and supported portal links into local files
- preserve provenance in `raw/`
- derive machine-usable metadata in `asset_manifest.tsv`
- materialize human-usable canonical names in `final/`

read this first if you are a new agent:
1. `README.md`
2. `docs/architecture.md`
3. `docs/goals_review.md`
4. `schemas/*.schema.json`

current truth:
- gmail native attachments: working
- gmail inline image assets: working
- image OCR lane: working
- metadata derivation for `analysis_date` and `owner`: working on gmail runs
- portal-backed invitro export for anonymous result links: working

non-goals:
- this repo is not a generic browser automation framework
- this repo is not a universal lab-login robot
- this repo should not mutate mailbox state by default

repo entrypoints:
- `./scripts/doctor.sh`
- `./scripts/run_gmail_lab_export.sh ./examples/targets.tsv`
- `./scripts/run_portal_lab_export.sh ./examples/portal_targets.tsv`

artifact contract:
- `raw/` = provenance-safe extracted files, never renamed in place
- `ocr/` = OCR derivatives for image assets
- `final/` = canonical filenames with `date__provider__owner__original`
- `run_manifest.tsv` = per-target execution log
- `asset_manifest.tsv` = per-file metadata truth layer for downstream ingest

date policy:
- every artifact must end with an `analysis_date`
- source priority:
  1. provider page
  2. gmail thread / received date
  3. contextual OCR date
  4. filename
  5. run fallback
- keep the source in `asset_manifest.tsv`; do not hide an inferred date behind a clean filename

owner policy:
- never silently claim ownership when the evidence is weak
- preferred statuses:
  - `likely_owner`
  - `weak_owner`
  - `unknown_owner`
- ambiguous rows must remain explicit

safe change rules:
- prefer adding new provider adapters over complicating the gmail collectors
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
