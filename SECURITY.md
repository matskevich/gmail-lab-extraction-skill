# security policy

## supported versions

security reports are accepted for the current `main` branch.

## report privately

do not open a public issue for:

- credential, cookie, token, or browser-profile leaks
- ways to expose private medical artifacts
- unsafe mailbox mutation
- portal-link or provider-auth bypasses

report privately through GitHub security advisories for this repository when available. if advisories are unavailable, contact the maintainer through the GitHub profile and include only a minimal, redacted reproduction.

## public-safe reports

normal bugs belong in GitHub Issues when they do not expose private data. remove personal names, dates of birth, order ids, portal keys, local paths, and raw medical content before posting.

## project security goals

- local-first by default
- read-only mailbox behavior by default
- no concrete passwords in manifests
- no committed real medical artifacts, tokens, cookies, or private target corpora
- explicit `needs_*` or `blocked_*` statuses instead of pretending a private gate was solved
