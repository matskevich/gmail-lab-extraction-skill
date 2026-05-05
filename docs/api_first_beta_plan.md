# API-first beta plan

## Verdict from Prodia three-PDF test

The test case was the Prodia `Half Medical Result` email with three encrypted PDFs:

- `2604250025 Mr Dzmitry Matskevich.pdf`
- `2604300029 Mr Dzmitry Matskevich.pdf`
- `2604300030 Mr Dzmitry Matskevich.pdf`

Current result:

- Gmail metadata is reachable through connected mailbox tooling.
- Raw attachment bytes are not reachable through ChatGPT Gmail connector attachment reads.
- Browser/CDP is unavailable when Chrome is not started with a remote debugging port or the CDP profile is not authenticated.
- Repo Gmail API runner is blocked until a local OAuth token is created.

This is an onboarding/auth architecture failure, not a PDF password failure.

## Product architecture

Primary lane:

```text
gmail-lab auth-google
-> local gmail.readonly token
-> gmail-lab export-gmail-api
-> Gmail API messages/attachments
-> raw/
-> pdf_text/OCR/SecretResolver
-> manifests
```

Fallback lanes:

- Browser/CDP: debug and rescue only.
- Persistent browser/CDP profile: preferred browser fallback when API auth is unavailable or a UI-specific bug must be inspected.
- Cloned browser/CDP profile: legacy rescue path only after smoke proves the clone is authenticated.
- ChatGPT Gmail connector: diagnosis only; it is not part of the open-source runtime.
- Manual download: emergency operator workaround, not a product path.

## P0 gates

1. A fresh user can run:

```bash
gmail-lab auth-google --client-secrets ~/.gmail-lab/client_secret.json
gmail-lab diagnose-gmail-acquisition
gmail-lab google-auth-status
gmail-lab export-gmail-api ./tmp/private_targets.tsv ./runs/gmail-api-run
```

2. The Prodia three-PDF target lands all raw files in `raw/`.
3. `run_manifest.tsv/status=ok` and `extracted_count=3`.
4. Encrypted PDFs report `pdf_text_status=needs_password_hint` if no local secret is supplied.
5. No password, token, cookie, or OAuth client secret enters git, logs, issue templates, or manifests.

## P1 gates

1. API discovery can find candidate lab/result emails without hand-written provider queries.
2. API acquisition handles:
   - nested MIME parts
   - duplicate filenames
   - multiple attachments in one message
   - inline body attachments with `body.data`
   - attachment references with `attachmentId`
3. Fixture tests cover fake Gmail API responses without live credentials.
4. Live corpus includes at least:
   - one normal PDF
   - one encrypted PDF
   - one multi-attachment email
   - one inline-image result
   - one provider portal link

## P2 gates

1. Package `gmail-lab` exposes all primary workflows through CLI, not repo-only scripts.
2. Codex/Claude skills call package commands first.
3. Browser/CDP docs clearly mark fallback-only status.
4. Release verdict changes from `browser-first self-hosted alpha` to `api-first beta` only after P0 and P1 pass on live corpus.
