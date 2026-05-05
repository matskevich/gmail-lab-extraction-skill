# Google API setup

This repo should work from a user's own machine without ChatGPT Gmail connector access and without a logged-in Chrome session.

## Goal

Use Gmail API as the primary acquisition lane for Gmail-native attachments:

- scope: `gmail.readonly`
- auth: local OAuth installed-app flow
- evidence: raw files written to `raw/`
- downstream: the existing PDF text, OCR, secret-resolution, and manifest lanes

The ChatGPT Gmail connector is useful for diagnosis during development, but it is not part of the open-source runtime.

## Create OAuth credentials

1. Open Google Cloud Console.
2. Create or select a project.
3. Enable `Gmail API`.
4. Configure OAuth consent screen.
5. Create OAuth client credentials with application type `Desktop app`.
6. Download the JSON file locally.

Keep that file out of git. Good local locations:

```text
~/.gmail-lab/client_secret.json
~/.gmail-lab/oauth-client.json
```

## First run

Prepare a gitignored target file:

```tsv
from:tabanan@prodia.co.id newer_than:7d	2605040024	api
```

Run:

```bash
gmail-lab auth-google --client-secrets ~/.gmail-lab/client_secret.json
gmail-lab diagnose-gmail-acquisition
gmail-lab google-auth-status
gmail-lab export-gmail-api ./tmp/private_targets.tsv ./runs/gmail-api-run
```

The first run opens a local OAuth browser flow. The token is stored at:

```text
~/.gmail-lab/tokens/gmail-api-token.json
```

Later runs reuse that token unless `--token` or `GMAIL_LAB_GOOGLE_TOKEN` points elsewhere.

## Target locators

Preferred target shape is a Gmail search query plus an optional row needle:

```tsv
from:lab@example.com newer_than:14d	2605040024	api
```

The API runner also accepts direct Gmail API IDs:

```tsv
message:19df31832eed6691	2605040024	api
thread:19df31832eed6691	2605040024	api
```

Gmail web UI URLs such as:

```text
https://mail.google.com/mail/u/0/#inbox/FMfc...
```

are not Gmail API message IDs. Use a search query, `message:<api_id>`, or `thread:<api_id>`.

## Expected outputs

The API runner writes:

- `run_manifest.tsv`
- `evidence_manifest.tsv`
- `raw/`
- `pdf_text/`
- `asset_manifest.tsv`
- `logs/*.extract.json`

If a PDF is password protected, raw acquisition can still be `ok` while PDF text extraction returns:

```text
pdf_text_status=needs_password_hint
```

That is the correct boundary: acquisition succeeded, enrichment needs a local secret.

## Failure meanings

- `gmail api auth missing`: no token and no OAuth client secret was provided.
- `gmail_ui_url_not_api_locator`: a Gmail web URL was passed where a query or API ID is required.
- `extract_fail`: raw bytes were not acquired for that target; inspect the row stderr log.
- `needs_password_hint`: raw bytes exist, but encrypted PDF text needs a local secret source.

For browser fallback and `gmail_not_authenticated`, read `docs/acquisition_auth_router.md`.
