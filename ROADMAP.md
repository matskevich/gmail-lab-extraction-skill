# roadmap

## current public label

`browser-first self-hosted alpha`, moving to `api-first beta`

this means:

- local operator can run the browser lane today and the Gmail API lane where OAuth is configured
- accessible gmail attachments, inline images, password-hinted PDFs, and supported tokenized portal links can be captured
- raw evidence and agent-readable manifests are produced locally
- unsupported gates are reported as explicit debt

## near term

- improve universal gmail discovery so a user can ask for likely lab/result history without writing provider-specific targets
- validate Gmail API OAuth onboarding, target locators, and raw attachment acquisition on a broader live corpus before changing the public label
- add redacted fixture patterns for more languages and providers
- harden metadata extraction for owner, analysis date, sample draw date, and provider
- keep low-confidence metadata from looking promoted: fallback-dated assets must stay in `raw/` with `needs_review`
- add a local secret-resolution layer for passworded PDFs: hint detection, interactive prompt, scoped keychain/session persistence, and `needs_password_hint` status
- add provider adapters only when they preserve clear separation from gmail-native collection
- make `coverage_debt.tsv` first-class for unsupported portals, passwords, and low-confidence metadata

## mid term

- keep browser/CDP as fallback for rescue and debugging
- add a public adapter development guide
- add a minimal agent workflow for reading manifests and proposing next actions
- add CI gates for schemas, docs examples, and issue-template consistency

## not promised

- universal login/password/2FA/captcha automation
- hosted mailbox processing
- medical interpretation of results
- silent ownership/date inference when evidence is weak
- mutation of a user's mailbox by default

## release gates

before changing the public label, update `docs/release_verdict.md` with:

- exact code gates
- exact live or fixture gates
- supported providers and lanes
- known blockers
- what is not claimed
