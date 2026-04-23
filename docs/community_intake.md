# community intake

the project needs one intake system that humans can use quickly and agents can process reliably.

## source of truth

- issues: actionable bugs, provider requests, help requests, feature requests, and success cases
- discussions: open-ended ideas, questions, design tradeoffs, and user stories
- pull requests: concrete changes with tests/docs
- docs: current public contract and release status

chat is useful for awareness. github is the durable queue.

## labels

- `bug`: command or behavior is wrong
- `provider-request`: new lab/provider support
- `portal`: provider page, anonymous result link, login, or last-name gate
- `passworded-pdf`: encrypted pdf or password hint issue
- `gmail-ui`: browser/CDP/Gmail rendering issue
- `metadata`: owner/date/provider/confidence issue
- `docs`: docs, onboarding, examples
- `privacy`: redaction, secrets, personal data boundary
- `good-first-adapter`: small provider/parser contribution
- `needs-repro`: issue lacks enough redacted evidence
- `blocked-external`: blocked by provider login, captcha, expired link, or mailbox access
- `success-case`: a provider/language/file type worked

## triage rules for agents

1. read the issue template fields first
2. check whether personal data is present; if yes, ask for redaction and do not quote it back
3. map the issue to a lane:
   - discovery
   - acquisition
   - enrichment
   - metadata
   - promotion
   - portal adapter
   - docs/onboarding
4. ask for the smallest missing artifact:
   - command
   - manifest row
   - status value
   - redacted stderr
   - provider/language/file type
5. do not request raw medical files
6. convert repeated cases into tests, docs, or adapter work

## issue lifecycle

- `needs-repro`: not enough safe evidence
- `triaged`: lane and likely cause are known
- `accepted`: maintainer agrees this should be fixed
- `blocked-external`: cannot be solved without provider/login/user-side access
- `fixed`: merged and verified

## provider request acceptance

a provider request is actionable when it includes:

- country and provider/lab name
- delivery shape: attachment, inline image, tokenized portal link, passworded PDF, or login portal
- redacted command and manifest status
- whether a last-name or birth-date hint is expected
- whether the provider exposes a downloadable PDF

no public provider request should include a real portal key or raw result file.
