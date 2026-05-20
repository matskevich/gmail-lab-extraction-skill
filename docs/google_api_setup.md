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
3. If Google Cloud shows `Google Cloud access blocked`, enable 2-step verification on that Google account and refresh the console.
4. Enable `Gmail API`.
5. Configure OAuth consent screen.
6. Create OAuth client credentials with application type `Desktop app`.
7. Download the JSON file locally.

Keep that file out of git. The canonical local path is:

```text
~/.gmail-lab/oauth-client.json
```

`gmail-lab setup-google` can also take the downloaded JSON from another path and copy it there with local-only file permissions.

## First run

Prepare a gitignored target file:

```tsv
from:tabanan@prodia.co.id newer_than:7d	2605040024	api
```

Run:

```bash
gmail-lab setup-google --client-secrets ~/Downloads/oauth-client.json
gmail-lab diagnose-gmail-acquisition
gmail-lab google-auth-status
gmail-lab acquire-gmail ./tmp/private_targets.tsv ./runs/gmail-acquire-run
gmail-lab explain-run ./runs/gmail-acquire-run
```

`gmail-lab setup-google` validates that the JSON is a Desktop OAuth client, copies it to `~/.gmail-lab/oauth-client.json`, opens the local OAuth browser flow, and stores the token at:

```text
~/.gmail-lab/tokens/gmail-api-token.json
```

Later runs reuse that token unless `--token` or `GMAIL_LAB_GOOGLE_TOKEN` points elsewhere.

To inspect the plan without opening a browser:

```bash
gmail-lab setup-google --check-only
```

This command prints the exact missing piece: absent OAuth client JSON, invalid web-client JSON, OAuth/browser error, or missing token.

Use `gmail-lab setup --skip-auth` only for package/runtime initialization. Use `setup-google` for Gmail API auth. `auth-google` remains as a narrow compatibility command, but `setup-google` is the operator-facing entrypoint.

Do not use an API key, Google account password, app password, service-account key, portal password, or PDF password for this step. Gmail API acquisition needs only a local Desktop OAuth client plus the user's browser consent for the mailbox that receives the lab emails.

The one account-level prerequisite is Google Cloud Console access. As of 2026, Google may block Cloud Console until 2-step verification is enabled. That gate must be resolved in the Google account security UI; the extractor should not turn on account MFA automatically.

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

The acquisition runner writes:

- `run_manifest.tsv`
- `evidence_manifest.tsv`
- `raw/`
- `pdf_text/`
- `asset_manifest.tsv`
- `logs/*.extract.json`

Use `gmail-lab explain-run <run-dir>` after acquisition to get the machine-readable state, blockers, and next commands.

If a PDF is password protected, raw acquisition can still be `ok` while PDF text extraction returns:

```text
pdf_text_status=needs_password_hint
```

That is the correct boundary: acquisition succeeded, enrichment needs a local secret.

## Failure meanings

- `gmail api auth missing`: no token and no OAuth client secret was provided.
- `api_auth_missing`: the acquisition router could not use Gmail API, and no authenticated browser/CDP fallback was available.
- `cdp_not_authenticated`: browser/CDP is reachable, but it is not an authenticated Gmail mailbox.
- `gmail_ui_url_not_api_locator`: a Gmail web URL was passed where a query or API ID is required.
- `extract_fail`: raw bytes were not acquired for that target; inspect the row stderr log.
- `needs_password_hint`: raw bytes exist, but encrypted PDF text needs a local secret source.

For browser fallback and `gmail_not_authenticated`, read `docs/acquisition_auth_router.md`.
