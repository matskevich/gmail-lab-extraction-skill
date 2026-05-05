# architecture

## system shape

the repo has 5 layers:

1. discovery
- search the mailbox for candidate medical threads
- distinguish `candidate_attachment`, `candidate_inline_only`, `candidate_portal_only`, `candidate_context_only`

2. extraction
- gmail api runner fetches native attachment bytes from mailbox MIME state
- gmail collectors fetch bytes from gmail page context via cdp
- portal runners open a provider result page and fetch bytes there

3. derivation
- OCR runs on image assets
- PDF text extraction runs on normal and password-hinted PDFs
- metadata derivation assigns `analysis_date`, `owner`, `provider`, and confidence

4. materialization
- `final/` gets canonical filenames
- `asset_manifest.tsv` becomes the bridge to downstream ingest

5. promotion
- downstream systems should read `asset_manifest.tsv`, not guess from filenames

## modules

### gmail extraction
- `scripts/run_gmail_api_export.py`
- `skills/gmail-browser-attachments/scripts/gmail_collect_attachments_from_query.mjs`
- `skills/gmail-browser-attachments/scripts/gmail_collect_inline_assets_from_query.mjs`

responsibility:
- search gmail through API or browser fallback
- traverse MIME parts and fetch `attachmentId` bytes when API OAuth is available
- open the matching thread
- warm the thread so below-the-fold attachment controls can hydrate before asset collection
- fetch visible assets with page-context credentials
- return:
  - `query`
  - `rowNeedle`
  - `thread`
  - `saved`

must not do:
- ownership truth claims
- file classification into medical taxonomy
- provider-specific portal logic

preferred lane:
- use `scripts/run_gmail_api_export.py` for gmail-native attachments when OAuth/token is available
- use persistent browser/CDP for inline Gmail UI assets, auth-broken rescue, and regression/debugging
- run `gmail-lab diagnose-gmail-acquisition` before treating a live mailbox run as available

### portal extraction
- `scripts/run_portal_lab_export.sh`
- `scripts/gmail_collect_portal_links.mjs`
- `providers/*.mjs`

responsibility:
- resolve a portal link from a gmail thread
- open the provider page
- run provider-specific download logic

current boundary:
- a working invitro anonymous-link adapter exists
- username/password/2fa providers still need separate adapters

### OCR
- `skills/gmail-browser-attachments/scripts/ocr_image_assets.py`

responsibility:
- convert extracted image assets into text
- produce `ocr_manifest.tsv`
- classify missing OCR tooling as `missing_dependency`, not as acquisition failure

must not do:
- choose the final date blindly from any found number

### PDF text extraction
- `scripts/extract_pdf_text.py`

responsibility:
- extract text from PDFs after raw bytes land locally
- try plain text extraction first
- if needed, ask `gmail_lab/core/secrets/SecretResolver` for password candidates from local runtime secrets
- fall back to rendering pages + OCR when the PDF is scanned
- classify absent `pdftotext` / `pdftoppm` / `tesseract` as enrichment debt

must not do:
- store concrete passwords in manifests
- assume every encrypted PDF is solvable without hints
- treat provider/email hints as secret values

### secret resolution
- `gmail_lab/core/secrets/models.py`
- `gmail_lab/core/secrets/store.py`
- `gmail_lab/core/secrets/resolver.py`

responsibility:
- keep password hints separate from password values
- resolve local candidates from env, prompt, session cache, OS keychain, encrypted local fallback, and explicit email passwords
- support scopes:
  - `attachment_sha256`
  - `gmail_thread`
  - `provider_identity`
  - `identity`
- emit only redacted outcome metadata into manifests

must not do:
- write raw passwords or dates of birth into repo files, target TSVs, logs, issue templates, or manifests
- use plaintext `config.yaml` as the long-term secret store

### metadata derivation
- `scripts/derive_asset_metadata.py`

responsibility:
- combine thread context, provider page metadata, OCR output, and file names
- choose:
  - `analysis_date`
  - `analysis_date_source`
  - `analysis_date_status`
  - `owner_name`
  - `owner_source`
  - `owner_status`
  - `provider`
  - `provider_source`
  - `confidence`

important rule:
- metadata is a claim layer
- raw extraction is an evidence layer
- do not merge them

## data flow

```text
targets.tsv / portal_targets.tsv / regression_targets.tsv
  -> discovery / regression corpus
  -> discovery_manifest.tsv
  -> runner
  -> raw/ + logs/ + run_manifest.tsv / regression_summary.tsv
  -> OCR for images
  -> PDF text extraction for PDFs
  -> derive_asset_metadata.py
  -> final/ + asset_manifest.tsv

existing run recovery:
- `scripts/rerun_enrichment.py` replays only OCR/PDF-text + metadata on an existing `raw/` run
- use it after installing missing local binaries instead of re-downloading from Gmail
```

## manifest semantics

### discovery_manifest.tsv
- one row per target / query before raw download
- `discovery_class` answers what class of thread this is:
  - `candidate_attachment`
  - `candidate_inline_only`
  - `candidate_portal_only`
  - `candidate_context_only`
- this is the right surface for mailbox completeness audits

### run_manifest.tsv
- one row per target / query
- `status` = acquisition only
- `ocr_status` / `pdf_text_status` / `enrichment_status` = derivative lanes
- missing local binaries must not downgrade `status` from `ok` to failure

### regression_summary.tsv
- one row per historical regression target
- operator-facing truth for:
  - final row status
  - landed attachment / inline counts
  - filtered inline noise summary
  - resolved gmail thread title and href
- use this file to review whether a live regression was green and clean without reopening every json log

### asset_manifest.tsv
- one row per concrete file
- truth for date / owner / provider / confidence
- `status=non_result` means the raw file was preserved but intentionally not promoted into `final/`
- `status=sidecar` means a formal companion file, such as `.sig`, was preserved in `raw/` but not promoted as a clinical result file
- `status=needs_review` means acquisition landed the raw file but metadata is too weak for promotion; the current trigger is `analysis_date_status=fallback`

## design choices for agent-friendliness

- stable entrypoints
- explicit manifests
- provenance preserved
- separate layers for extraction vs inference
- status enums instead of implicit prose

## design limits

- not every mail with a result link is extractable by the gmail layer
- not every provider page exposes a stable downloadable response
- a clean canonical filename does not mean the date is direct evidence; use the source/status columns
- discovery completeness still depends on maintaining a real regression corpus of historical cases
