# architecture

## system shape

the repo has 4 layers:

1. extraction
- gmail collectors fetch bytes from gmail page context via cdp
- portal runners open a provider result page and fetch bytes there

2. derivation
- OCR runs on image assets
- metadata derivation assigns `analysis_date`, `owner`, `provider`, and confidence

3. materialization
- `final/` gets canonical filenames
- `asset_manifest.tsv` becomes the bridge to downstream ingest

4. promotion
- downstream systems should read `asset_manifest.tsv`, not guess from filenames

## modules

### gmail extraction
- `skills/gmail-browser-attachments/scripts/gmail_collect_attachments_from_query.mjs`
- `skills/gmail-browser-attachments/scripts/gmail_collect_inline_assets_from_query.mjs`

responsibility:
- search gmail
- open the matching thread
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

must not do:
- choose the final date blindly from any found number

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
targets.tsv / portal_targets.tsv
  -> runner
  -> raw/ + logs/ + run_manifest.tsv
  -> OCR for images
  -> derive_asset_metadata.py
  -> final/ + asset_manifest.tsv
```

## manifest semantics

### run_manifest.tsv
- one row per target / query
- execution status only

### asset_manifest.tsv
- one row per concrete file
- truth for date / owner / provider / confidence

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
