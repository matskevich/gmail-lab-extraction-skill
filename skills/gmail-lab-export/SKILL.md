---
name: gmail-lab-export
description: Run and interpret the gmail-lab local export workflow for lab/result artifacts. Use when an agent needs to discover Gmail lab threads, export Gmail attachments or inline images, handle passworded PDFs through local secret resolution, inspect manifests, rerun enrichment, or explain why an artifact did or did not appear in final/.
---

# Gmail Lab Export

## Core Rule

Treat this repo as a local evidence pipeline, not a generic browser robot.

Truth order:
1. `discovery_manifest.tsv`
2. `run_manifest.tsv`
3. `raw/`, `ocr/`, `pdf_text/`
4. `asset_manifest.tsv`
5. `final/`

Never claim mailbox completeness from `final/` alone.

## Start Here

From repo root:

```bash
./scripts/doctor.sh
gmail-lab setup --skip-auth
python -m gmail_lab --help
gmail-lab setup-google --check-only
gmail-lab diagnose-gmail-acquisition
gmail-lab verify-gmail-paths --targets-tsv ./tmp/private_targets.tsv
gmail-lab acquire-gmail ./tmp/private_targets.tsv ./runs/gmail-acquire-run
gmail-lab explain-run ./runs/gmail-acquire-run
```

If the user asks for live Gmail extraction:

```bash
./scripts/run_gmail_discovery.sh ./examples/targets.tsv
gmail-lab setup-google --client-secrets /path/to/oauth-client.json
gmail-lab verify-gmail-paths --targets-tsv ./examples/targets.tsv --run-dir ./runs/gmail-smoke --allow-live
gmail-lab acquire-gmail ./examples/targets.tsv ./runs/gmail-acquire-run
```

For real mailbox runs, keep targets in a gitignored file such as `tmp/private_targets.tsv`.

## Decision Router

- "find likely lab emails" -> run discovery first; inspect `discovery_manifest.tsv`.
- "first run / install check" -> run `gmail-lab setup-google`; pass `--client-secrets <oauth-desktop-client.json>` to complete Gmail API auth.
- "does this machine actually download Gmail docs" -> run `gmail-lab verify-gmail-paths --targets-tsv <targets.tsv> --run-dir <run-dir> --allow-live`; read `live_acquisition.explanation` before interpreting files.
- "download/export results" -> run `gmail-lab acquire-gmail <targets.tsv> <run-dir>`; it routes through Gmail API, authenticated CDP, or a typed blocker manifest.
- "what happened in this run" -> run `gmail-lab explain-run <run-dir>` or `gmail-lab status <run-dir>` before interpreting `final/`.
- "Gmail URL" -> do not treat `mail.google.com/.../#inbox/FMfc...` as an API id; ask for/search by sender/date/filename, or use `message:<api_id>` / `thread:<api_id>` if the real Gmail API id is known.
- "`gmail_not_authenticated`" -> browser/CDP did not reach an authenticated Gmail mailbox; use Gmail API, or run `gmail-lab acquire-gmail <targets.tsv> <run-dir> --start-persistent-cdp` and log into Gmail once.
- "why is final empty/wrong" -> inspect `asset_manifest.tsv`; `final/` is a convenience view.
- "OCR or PDF text failed" -> inspect `ocr_status`, `pdf_text_status`, and `enrichment_status`, then run `gmail-lab unlock-pdf-run <run-dir>` for passworded PDFs or `./scripts/rerun_enrichment.py <run-dir>` after installing missing tools.
- "passworded PDF" -> use local secret resolution; email/provider text is a hint, password values are local secrets.
- "`birth_date_secret_id` exists but PDF still needs password" -> run `gmail-lab identity-status`; the useful signal is `birth_date_secret.resolvable`, not the id alone.
- "`birth_date_secret.legacy=true`" -> run `gmail-lab migrate-pdf-secrets`; this copies `identity:*` / `provider_identity:*` into `pdf_unlock:*` without re-entering the secret.
- "portal/login password" -> keep it separate from PDF unlock: use `gmail-lab remember-portal-secret --provider <provider>`; PDF extraction must only read `pdf_unlock:*` ids.
- "is this complete" -> require discovery plus regression evidence, not one happy-path export.
- "portal link" -> use `./scripts/run_portal_lab_export.sh` only for supported tokenized providers.
- "how do we learn from this" -> read `docs/learning_loop.md`; promote the incident into a private regression target, test, doc/skill rule, schema/status, or sanitized intake item.

## Passworded PDFs

Do not put password values, dates of birth, portal passwords, cookies, or tokens into repo files, target TSVs, logs, issues, or manifests.

Use:

```bash
gmail-lab unlock-pdf-run ./runs/my-run
```

Valid persistence choices: `never`, `session`, `keychain`, `encrypted-file`.

For reusable local storage:

```bash
gmail-lab remember-pdf-secret \
  --scope identity \
  --hint-type birth_date_ddmmyyyy \
  --persistence keychain
```

Expected manifest behavior:
- `password_used=redacted`
- `secret_scope` records scope
- `secret_purpose=pdf_unlock` records that the secret was used only for PDF unlock
- `secret_persistence` records persistence
- `status=needs_password_hint` means a non-interactive run had a password hint but no local candidate
- `prompt_skipped=stdin_not_tty` means `--prompt-secrets` was requested from a non-interactive agent shell; store the secret with `remember-pdf-secret` or run the command in a real terminal.

Preferred local setup for reusable password hints:

```bash
gmail-lab remember-pdf-secret \
  --scope identity \
  --hint-type birth_date_ddmmyyyy \
  --persistence keychain
```

This prompts locally with hidden input, stores only in the local secret store,
and writes no concrete password/date into targets, logs, manifests, or chat.

## Manifest Reading

If `run_manifest.tsv/status=ok`, raw acquisition succeeded. Enrichment can still be blocked.

Fast path:

```bash
gmail-lab explain-run <run-dir>
```

Read `state`, `blockers`, and `next_steps` before opening old local files with similar names.

Read:
- `ocr_status`
- `pdf_text_status`
- `enrichment_status`

In `asset_manifest.tsv`:
- `status=ok` -> promoted to `final/`
- `status=needs_review` -> raw landed, metadata too weak for promotion
- `analysis_date_status=fallback` -> do not trust the date as clinical truth
- `final_file=-` -> intentionally not promoted

## References

Read only when needed:
- `references/manifest_contract.md` for row/status semantics
- `references/secret_resolution.md` for password handling
- `references/live_gmail_boundaries.md` for CDP/live-run caveats

Repo-local source of truth:
- `START_HERE_FOR_AGENTS.md`
- `AGENTS.md`
- `docs/architecture.md`
- `docs/learning_loop.md`
- `docs/test_strategy.md`
- `docs/secret_resolution.md`
- `schemas/*.schema.json`
