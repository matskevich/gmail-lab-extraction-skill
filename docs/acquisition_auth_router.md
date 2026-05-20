# Acquisition auth router

This project extracts raw lab/result evidence before it derives metadata or text.

## Router

Use this order for Gmail-native attachments:

1. Gmail API
2. Persistent browser/CDP profile
3. Cloned browser/CDP profile
4. ChatGPT Gmail connector for diagnosis only
5. Manual download only as an emergency operator workaround

Run the machine check first:

```bash
gmail-lab diagnose-gmail-acquisition
gmail-lab verify-gmail-paths --targets-tsv ./tmp/private_targets.tsv
```

Use the live smoke only when the operator expects real downloads:

```bash
gmail-lab verify-gmail-paths --targets-tsv ./tmp/private_targets.tsv --run-dir ./runs/gmail-smoke --allow-live
```

This command is the compact handoff surface: CLI path, dependency state, Gmail API auth, browser/CDP auth, live acquisition exit code, and `explain-run` summary in one JSON result.

For normal acquisition, use the router:

```bash
gmail-lab acquire-gmail ./tmp/private_targets.tsv ./runs/gmail-acquire-run
```

If Gmail API is not configured and browser fallback is acceptable, ask the router to start the persistent CDP profile:

```bash
gmail-lab acquire-gmail ./tmp/private_targets.tsv ./runs/gmail-cdp-run --start-persistent-cdp
```

On the first run, log into Gmail in the opened Chrome window. Rerun the same command after login.

The router writes `run_manifest.tsv` even when acquisition is blocked. Important blocker statuses:

- `api_auth_missing`: Gmail API token/client secret is not available; browser/CDP was also unavailable.
- `cdp_not_authenticated`: CDP is reachable but the page is not an authenticated Gmail mailbox.
- `cdp_down`: CDP is not reachable.
- `blocked_by_acquisition`: enrichment did not run because raw bytes were not acquired.

Operator/agent handoff command:

```bash
gmail-lab explain-run <run-dir>
```

It reads `run_manifest.tsv`, `asset_manifest.tsv`, OCR/PDF-text manifests, and `logs/acquisition_diagnostic.json`, then returns `state`, `blockers`, and `next_steps`. Treat `state=acquisition_blocked` as a hard stop: raw bytes are absent, so matching old filenames/order ids are not evidence of the current email.

## Why a previous browser fallback can work

A browser/CDP run works only when all of these are true:

- Chrome is reachable through a remote debugging port.
- The resolved page is an authenticated Gmail mailbox.
- Gmail has rendered attachment controls with `download_url`.
- CDP can run `fetch(..., { credentials: "include" })` in that page context.

When those invariants hold, the browser lane can save raw bytes even for encrypted PDFs. Password handling happens later in the PDF text lane.

## Why the same fallback can fail later

An ordinary logged-in Chrome window is not automatically a CDP target. Chrome must be started with `--remote-debugging-port`.

Chrome also blocks remote debugging on the default user data directory, so the old helper cloned an existing profile into `/tmp`. That can work, but it is not a stable auth contract:

- the source profile may be the wrong Chrome profile;
- the source profile may be copied while Chrome is active;
- Google session cookies/tokens may not survive the clone;
- Google can reject the cloned credentials and force a sign-in page.

When the smoke gate reports `gmail_not_authenticated`, the browser lane has not reached mailbox evidence. Treat that as an acquisition/auth failure, not a PDF password failure.

## Stable browser fallback

For browser fallback, use a persistent CDP-only profile:

```bash
skills/gmail-browser-attachments/scripts/start_chrome_cdp_profile.sh
```

Log into Gmail in that window once. Later runs reuse:

```text
~/.gmail-lab/chrome-cdp-profile
```

This is still a fallback. Gmail API remains the primary lane for native attachments.

The May-12 Prodia addendum case validated this fallback shape: `/tmp` clone opened public Gmail, while the persistent CDP profile worked after a one-time login and acquired raw bytes.

## Primary Gmail API lane

Authenticate once:

```bash
gmail-lab setup-google --client-secrets ~/.gmail-lab/oauth-client.json
gmail-lab google-auth-status
```

Export:

```bash
gmail-lab acquire-gmail ./tmp/private_targets.tsv ./runs/gmail-acquire-run
```

Target rows can use a search query or a real Gmail API id:

```tsv
from:lab@example.com newer_than:14d	order-123	api
message:<gmail-api-message-id>	order-123	api
thread:<gmail-api-thread-id>	order-123	api
```

Gmail web UI URLs like `https://mail.google.com/.../#inbox/FMfc...` are not Gmail API ids.

## Acceptance test for the Prodia three-PDF case

The live acceptance target is the Prodia message known to contain three encrypted PDFs:

```tsv
message:19df33cf090c3ffa	2604300030	api
```

Expected acquisition result:

- `run_manifest.tsv/status=ok`
- `extracted_count=3`
- all three PDFs exist under `raw/`
- encrypted PDFs report `pdf_text_status=needs_password_hint` unless a local secret source is available

Do not claim the case is solved until raw bytes exist. `needs_password_hint` is downstream enrichment state; it is meaningful only after acquisition succeeds.
