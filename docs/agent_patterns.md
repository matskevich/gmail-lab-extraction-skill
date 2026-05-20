# agent-friendly patterns

this repo follows 5 patterns that are worth preserving:

1. small entrypoints
- one runner per lane
- one script per responsibility

2. machine-readable handoff
- `run_manifest.tsv`
- `asset_manifest.tsv`
- explicit enums for source/status/confidence

3. provenance before inference
- raw bytes stay in `raw/`
- inference lives in a separate manifest

4. honest ambiguity
- `unknown-provider`
- `unknown-owner`
- `low` confidence

5. narrow adapters
- provider-specific logic belongs in `providers/*.mjs`

anti-patterns:
- giant orchestration scripts with hidden side effects
- mixing browser automation, OCR, and metadata claims in one step
- treating a Gmail sign-in page as a usable CDP fallback
- relying on filenames as the only contract
- letting agents infer schema from examples instead of a declared contract

pragmatic note:
- if you add a new capability, add the manifest field or schema first
- if you add a new provider, keep it behind a dedicated adapter file
- if live Gmail acquisition is blocked, fail with the exact auth/acquisition state before asking for manual screenshots or interpreting clinical content
