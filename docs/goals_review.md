# goals review

## original goals

1. find analyses in gmail reliably
2. extract gmail-native attachments
3. extract inline image-based results
4. support portal-linked results where possible
5. OCR image results
6. handle password-protected PDFs when the password can be inferred or supplied
7. guarantee an `analysis_date` for every artifact
8. capture whose result it is
9. package the work as a reusable skill/repo for other agents

## current status

### green
- `gmail search -> thread -> native attachments`
- `gmail search -> thread -> inline image assets`
- OCR for image assets
- password-hinted PDF text extraction with OCR fallback
- reproducible runs with `run_manifest.tsv`
- metadata derivation for `analysis_date`
- metadata derivation for `owner`
- canonical filenames in `final/`
- reusable repo + skill structure

### yellow
- `analysis_date` is sometimes inferred from gmail thread date, not direct from artifact
- `owner` can still be `weak_owner` or `unknown_owner` on forwarded / context-only mails
- provider detection is heuristic outside explicit provider hints
- passworded PDFs still need either a discoverable rule in context or an explicit operator hint

### red
- generic login-required provider automation does not exist yet

## what was fixed during review

- removed provider hallucinations caused by matching JSON key names instead of evidence
- stopped OCR birth dates from overriding artifact dates without context
- made ambiguous rows explicit instead of pretending confidence

## what remains to make v1 solid

1. add one more provider adapter beyond invitro anonymous links
2. add provider-specific direct date parsers where the portal page exposes collection/result dates
3. improve stronger owner verification beyond thread/title heuristics

## what should wait until v2

- username/password/2fa providers
- automatic dedupe across runs
- deeper ownership verification against patient dob or order id

## release judgment

for agent use now:
- yes, as a gmail extraction repo with OCR + metadata derivation

for claiming universal lab export:
- no

truthful label right now:
- `gmail and tokenized-portal lab extraction repo with explicit provenance and metadata status`
