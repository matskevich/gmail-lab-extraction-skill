# secret resolution for passworded results

goal: passworded PDFs should be recoverable without putting passwords, dates of birth, or portal secrets into target files, manifests, logs, git history, or support issues.

the password problem has three different axes:

- hint discovery: what does the email/provider say about the password rule?
- secret resolution: which local secret can satisfy that rule for this user?
- secret purpose: where this secret is allowed to be used

PDF unlock secrets, portal login passwords, patient-gate hints, Gmail OAuth
tokens, and browser cookies are different credential classes. They can share a
provider and identity, but they must not share a secret id or resolver path.

these must stay separate. a hint is evidence. a secret is private runtime state.

## supported secret sources

resolution order:

1. run-level environment variables for automation and CI fixtures
   - `PDF_PASSWORD_CANDIDATES`
   - `PDF_BIRTH_DATE`
2. one-run interactive prompt
   - useful for local one-off extraction
   - no persistence unless the user explicitly chooses it
3. local secret store
   - default long-term path
   - backed by OS keychain where available
   - encrypted local fallback only when keychain is unavailable
4. provider or identity metadata
   - only for non-public local config
   - should migrate away from plain `config.yaml` for sensitive facts
5. explicit password text in the message body
   - accepted only when the email includes a concrete password, not only a rule
6. hint-derived candidates
   - examples: birth date formats, phone suffix, order id
   - only if the underlying secret is known locally

## local storage model

`~/.gmail-lab/config.yaml` is for non-secret configuration:

- canonical display name
- aliases
- known non-owner names
- mailbox addresses
- provider domains
- references to secret ids

secret values belong in a separate local store:

- primary: OS keychain via a small `SecretStore` interface
- fallback: encrypted file under `~/.gmail-lab/secrets/`
- never: plaintext yaml, target TSVs, run manifests, issue templates, or logs

the local index can store metadata, but not the value:

- `secret_id`
- `label`
- `provider`
- `identity_alias`
- `purpose`
- `hint_type`
- `scope`
- `created_at`
- `last_used_at`
- `use_count`
- optional `evidence_sha256`

example scopes:

- `attachment_sha256`: one specific file
- `gmail_thread`: one mail thread
- `provider_identity`: one provider for one user identity
- `identity`: reusable personal fact such as birth date

example purposes:

- `pdf_unlock`: opens encrypted result PDFs only
- `portal_login`: logs into a provider account only
- `portal_patient_gate`: satisfies a tokenized portal patient gate only
- `gmail_oauth`: Gmail API tokens, handled by the Gmail auth lane

secret ids are namespaced by purpose:

- `pdf_unlock:identity:default`
- `pdf_unlock:provider_identity:prodia:default`
- `portal_login:provider_identity:prodia:default`
- `portal_patient_gate:provider_identity:prodia:default`

legacy `identity:default` and `provider_identity:<provider>:<identity>` are read
only as a backward-compatible fallback for `pdf_unlock`. Portal code must never
search those legacy ids.

default persistence should be `session`. permanent persistence requires an explicit user choice.

## cli ux

when an encrypted PDF cannot be opened and the email contains a hint, the CLI should stop with a typed state:

```text
encrypted pdf needs a secret
provider: prodia
hint: birth date DDMMYYYY
scope suggestion: provider_identity

1. enter one-time password
2. enter birth date and remember in local keychain
3. skip this document
```

canonical persistent setup:

```bash
gmail-lab remember-pdf-secret \
  --scope identity \
  --hint-type birth_date_ddmmyyyy \
  --persistence keychain
```

This uses a hidden local prompt and stores the value under
`pdf_unlock:identity:default`. The secret value is not printed, and only
`birth_date_secret_id` is written to `~/.gmail-lab/config.yaml`.

If an older local install has `birth_date_secret_id=identity:default`, migrate it
without re-entering the value:

```bash
gmail-lab migrate-pdf-secrets
```

The command copies the legacy value to the purpose-namespaced id and updates
config. It does not delete the old keychain entry.

Portal credentials use a separate command and namespace:

```bash
gmail-lab remember-portal-secret \
  --provider prodia \
  --secret-type account_password \
  --persistence keychain
```

This stores `portal_login:provider_identity:prodia:default`. It is not visible
to PDF unlock. A patient gate hint uses `--secret-type patient_gate_hint` and
stores `portal_patient_gate:provider_identity:<provider>:<identity>`.

To unlock an already acquired run without handling raw paths directly:

```bash
gmail-lab unlock-pdf-run ./runs/my-run
```

This reruns PDF text extraction against existing `raw/`, prompts locally if needed, and updates `run_manifest.tsv` / `asset_manifest.tsv`.

Before assuming a remembered secret exists, check that the reference resolves:

```bash
gmail-lab identity-status
```

`identity.birth_date_secret_id` only proves that config points at a secret id.
`identity.birth_date_secret.resolvable=true` proves the local keychain or
encrypted-file backend can actually read the secret in the current runtime.

For automation without shell history leakage, pass an environment variable name,
not the value:

```bash
gmail-lab remember-pdf-secret \
  --scope identity \
  --hint-type birth_date_ddmmyyyy \
  --persistence keychain \
  --value-env PDF_BIRTH_DATE
```

non-interactive mode must not hang. it should emit:

```text
status=needs_password_hint
hint_type=birth_date_ddmmyyyy
prompt_skipped=stdin_not_tty
next=run gmail-lab remember-pdf-secret, rerun with --prompt-secrets, or set PDF_PASSWORD_CANDIDATES/PDF_BIRTH_DATE
```

manifest fields should say what happened without exposing the secret:

- `password_source`
- `password_used=redacted`
- `secret_scope`
- `secret_purpose=pdf_unlock`
- `secret_persistence`
- `candidate_count`
- `status`

## code shape

target package:

```text
gmail_lab/core/secrets/
  models.py
  store.py
  resolver.py
```

minimum interfaces:

```python
class SecretStore:
    def get(self, secret_id: str) -> str | None: ...
    def put(self, secret_id: str, value: str, metadata: SecretMetadata) -> None: ...

class SecretResolver:
    def candidates(self, context: SecretContext) -> list[SecretCandidate]: ...
```

`scripts/extract_pdf_text.py` should become a thin CLI wrapper around the resolver. the current env and prompt behavior are valid resolver inputs, but they should not remain the whole architecture.

## migration path

### v0

- keep current env support
- keep `PDF_PASSWORD_PROMPT=1`
- add explicit `needs_password_hint` status when a PDF is encrypted and no candidate works
- avoid writing sensitive identity facts into support artifacts

### v1

- add `SecretResolver`
- add `SecretStore` with OS keychain backend
- add `--prompt-secrets`
- add `--remember-secret never|session|keychain|encrypted-file`
- add secret scope selection

current implementation status:
- `gmail_lab/core/secrets/` exists with models, resolver, OS keychain primary store, and encrypted-file fallback
- `scripts/extract_pdf_text.py` routes password candidates through `SecretResolver`
- `pdf_text_manifest.tsv` includes `secret_scope`, `secret_purpose`, and `secret_persistence`
- non-interactive encrypted PDFs with a hint and no candidate emit `status=needs_password_hint`
- `PDF_PASSWORD_CANDIDATES` and `PDF_BIRTH_DATE` remain as the v0 automation path
- `remember-pdf-secret` writes purpose-namespaced `pdf_unlock:*` ids
- `remember-portal-secret` writes separate `portal_login:*` / `portal_patient_gate:*` ids

### v2

- move sensitive `identity.birth_date` out of plaintext `config.yaml`
- keep only a secret reference in config
- route Gmail API and browser fallback lanes through the same resolver
- add provider adapters that explicitly request `portal_login` or
  `portal_patient_gate` secrets instead of touching PDF unlock secrets

## support boundary

safe to ask users for:

- provider name
- hint text with personal values redacted
- manifest rows with `password_used=redacted`
- `status=needs_password_hint`

not safe to ask users for:

- date of birth
- concrete PDF password
- portal password
- copied email body containing personal secrets
- raw unredacted result PDFs
