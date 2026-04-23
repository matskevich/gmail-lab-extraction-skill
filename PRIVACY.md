# privacy

this project is built for local-first extraction of personal medical artifacts. treat every mailbox, report, filename, screenshot, and log as potentially sensitive.

## do not share

- real lab PDFs, images, OCR text, or portal screenshots
- full names, birth dates, phone numbers, addresses, emails, order ids, barcodes, and portal keys
- browser cookies, gmail message ids, tokens, client secrets, or exported chrome profiles
- unredacted `raw/`, `final/`, `ocr/`, `pdf_text/`, `run_manifest.tsv`, `asset_manifest.tsv`, or browser logs

## safe issue data

share the minimum shape needed to reproduce:

- operating system and install method
- command that failed
- provider/lab name and country, if you are comfortable naming it
- file type class: `pdf`, `jpg/png`, `inline image`, `portal link`, `passworded pdf`
- redacted manifest rows with paths, names, order ids, and owner fields replaced
- short error text after removing secrets and personal data

## redaction rule

replace private values with stable placeholders:

```text
FULL_NAME -> PERSON_A
DATE_OF_BIRTH -> DOB_REDACTED
ORDER_ID -> ORDER_123
EMAIL -> user@example.com
PORTAL_KEY -> PORTAL_KEY_REDACTED
LOCAL_PATH -> /path/to/run
```

keep structure, status values, and field names intact so agents can still reason about the bug.

## security boundary

this tool should not mutate a mailbox by default. supported live flows are read-only: search, open, fetch, OCR, and write local manifests.

do not open a public issue for a vulnerability that exposes private medical data or credentials. use the security contact path in `SECURITY.md`.
