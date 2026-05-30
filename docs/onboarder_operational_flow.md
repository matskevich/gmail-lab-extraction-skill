# onboarder operational flow

this document describes the current operational email-onboarding flow that agents refer to as `onboarder`.

important truth:

- `onboarder` is an operational workflow name
- it is not a separate source directory inside this repository
- the current implementation is the combination of:
  - `scripts/run_onboarder_email_sync.sh`
  - `scripts/run_gmail_lab_export.sh`
  - `scripts/sync_run_to_cds.py`

## purpose

pull medical-looking email artifacts from a logged-in gmail chrome session, derive machine-usable text and metadata, and copy the resulting evidence bundle into the CDS raw handoff folder.

the CDS-side VPS handoff contract that this flow must satisfy is documented here:

- `/Users/mac/Documents/Codex app/singularity-club/services/client-data-store/docs/onboarder_email_handoff_contract.md`

## current entrypoint

```bash
./scripts/run_onboarder_email_sync.sh /absolute/path/to/targets.tsv openclaw_ilya-mutovin
```

arguments:

1. `targets.tsv`
   - gmail query plan
   - one row per search target / row needle
2. `cds_client_dir_name`
   - CDS raw client directory name
   - example: `openclaw_ilya-mutovin`
3. optional `run-name`
   - destination run folder name under `runs/` and CDS `from emails/`

## scheduler-facing use

the scheduler-facing command should call the wrapper above, not reconstruct the flow ad hoc.

current workstation automation shape:

- cadence: weekly
- local time assumption: monday 09:00
- job name in codex app: `Weekly Email Onboarder`

## operational flow

```text
targets.tsv
  -> doctor.sh
  -> run_gmail_lab_export.sh
  -> runs/<run-name>/
       raw/
       ocr/
       pdf_text/
       final/
       run_manifest.tsv
       asset_manifest.tsv
  -> sync_run_to_cds.py
  -> /srv/integrations/cds/raw/<client>/from emails/<run-name>/
       final/
       cds_asset_manifest.tsv
       run_manifest.tsv
       asset_manifest.tsv
       run_meta.txt
       cds_sync_manifest.tsv
       duplicate_hash_matches.tsv
```

## where the service reads email

the extractor does not use IMAP and does not depend on the codex gmail connector scopes.

it reads email by:

1. opening a local chrome profile with remote debugging
2. finding the live gmail page websocket on `9222`
3. searching gmail UI with the query from `targets.tsv`
4. opening the matching thread by `rowNeedle`
5. fetching visible attachment or inline asset bytes from the page context

primary modules:

- `skills/gmail-browser-attachments/scripts/gmail_find_page_ws_url.sh`
- `skills/gmail-browser-attachments/scripts/gmail_collect_attachments_from_query.mjs`
- `skills/gmail-browser-attachments/scripts/gmail_collect_inline_assets_from_query.mjs`

## where onboarder responsibility ends

`onboarder` owns:

- gmail / portal retrieval
- local `raw/` preservation
- OCR and PDF text extraction
- metadata derivation into `asset_manifest.tsv`
- canonical file naming into `final/`
- copying the whole materialized run into the CDS raw filesystem handoff

`onboarder` does not own:

- CDS database writes
- CDS entity destination mapping
- CDS registry mapping
- CDS observation / episode / clinical-entity materialization
- CDS deduplication policy for canonical records

## where CDS responsibility begins

CDS responsibility begins only after these files are consumed by a CDS-owned ingest path.

copying files into:

- `/srv/integrations/cds/raw/<client>/from emails/<run-name>/final/`

does **not** by itself create CDS rows.

that folder is an evidence handoff, not a normalized CDS write.

once CDS ingests those files as document assets, CDS becomes authoritative for:

- destination mapping
- validators
- provenance enrichment
- document-staged normalization
- registry-backed observation materialization

current CDS importer assumptions that onboarder must satisfy:

- every importable run lives under `/srv/integrations/cds/raw/<client>/from emails/<run-name>/`
- every importable run has `final/`
- every importable run has `cds_asset_manifest.tsv` or `asset_manifest.tsv`
- every importable manifest row has a `final_file` whose basename exists under `final/`
- manifest `status`, if present, should be `ok` or `accepted` for rows meant to be imported
- `cds_asset_manifest.tsv` should be treated as the preferred CDS-facing manifest when both manifests exist

## duplicate handling

the sync step intentionally copies the full `final/` bundle for the run into CDS.

it also writes:

- `duplicate_hash_matches.tsv`

so downstream tools can see which copied files match hashes already present elsewhere under:

- `from emails/`
- legacy `from email/`

the copy step is not allowed to silently drop files from the run folder just because they look duplicated somewhere else.

CDS owns checksum deduplication after handoff.

## relationship to the legacy gmail api path

this repository is the current operational path for attachment-heavy medical onboarding.

the older gmail-api mailbox ingestion slice in `services/knowledge-base` is a separate, legacy/experimental path and should not be described as the current `onboarder` runtime unless the repository state changes and docs are updated together.
