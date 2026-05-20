# Secret Resolution

Password handling has two layers:

- Hint: email/provider text such as `birth date DDMMYYYY`.
- Secret: local runtime value from prompt, session cache, OS keychain, encrypted local fallback, or env for CI.
- Purpose: PDF unlock, portal login, portal patient gate, and Gmail OAuth are separate credential classes.

Rules:

- Never write password values, dates of birth, cookies, tokens, or portal passwords into repo files, target TSVs, manifests, logs, issues, or support threads.
- Never reuse portal login secrets for PDF unlock, or PDF unlock secrets for portal login. Secret ids are purpose-namespaced, e.g. `pdf_unlock:identity:default` vs `portal_login:provider_identity:prodia:default`.
- Keep `PDF_PASSWORD_CANDIDATES` and `PDF_BIRTH_DATE` only as the v0 automation/CI path.
- Prefer `--prompt-secrets --remember-secret session` for local one-off use.
- Permanent persistence requires explicit `--remember-secret keychain` or `--remember-secret encrypted-file`.

Expected manifest fields:

- `password_source`
- `password_used=redacted`
- `secret_scope`
- `secret_purpose`
- `secret_persistence`
- `candidate_count`
- `status`

If status is `needs_password_hint`, rerun with a local secret source. Do not ask the user to paste secrets into issue text.
