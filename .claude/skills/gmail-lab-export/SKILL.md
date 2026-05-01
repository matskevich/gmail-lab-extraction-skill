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
python -m gmail_lab --help
```

For real mailbox runs, keep targets in a gitignored file such as `tmp/private_targets.tsv`.

## Decision Router

- "find likely lab emails" -> run discovery first; inspect `discovery_manifest.tsv`.
- "download/export results" -> run `./scripts/run_gmail_lab_export.sh <targets.tsv> <run-dir>`.
- "why is final empty/wrong" -> inspect `asset_manifest.tsv`; `final/` is a convenience view.
- "OCR or PDF text failed" -> inspect `ocr_status`, `pdf_text_status`, and `enrichment_status`, then rerun `./scripts/rerun_enrichment.py <run-dir>` after installing missing tools.
- "passworded PDF" -> use local secret resolution; email/provider text is a hint, password values are local secrets.
- "is this complete" -> require discovery plus regression evidence, not one happy-path export.
- "portal link" -> use `./scripts/run_portal_lab_export.sh` only for supported tokenized providers.

## Passworded PDFs

Do not put password values, dates of birth, portal passwords, cookies, or tokens into repo files, target TSVs, logs, issues, or manifests.

Use:

```bash
./scripts/extract_pdf_text.py ./runs/my-run/raw ./runs/my-run/pdf_text_check \
  --prompt-secrets \
  --remember-secret session
```

Expected manifest behavior:
- `password_used=redacted`
- `secret_scope` records scope
- `secret_persistence` records persistence
- `status=needs_password_hint` means a non-interactive run had a password hint but no local candidate

## Manifest Reading

If `run_manifest.tsv/status=ok`, raw acquisition succeeded. Enrichment can still be blocked.

In `asset_manifest.tsv`:
- `status=ok` -> promoted to `final/`
- `status=needs_review` -> raw landed, metadata too weak for promotion
- `analysis_date_status=fallback` -> do not trust the date as clinical truth
- `final_file=-` -> intentionally not promoted

Repo-local source of truth:
- `START_HERE_FOR_AGENTS.md`
- `AGENTS.md`
- `docs/architecture.md`
- `docs/test_strategy.md`
- `docs/secret_resolution.md`
- `schemas/*.schema.json`
