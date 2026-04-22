# goals review

## original goals

1. find analyses in gmail reliably
2. keep historical discovery completeness explicit, including partial-ready mails
3. extract gmail-native attachments
4. extract inline image-based results
5. support portal-linked results where possible
6. OCR image results
7. handle password-protected PDFs when the password can be inferred or supplied
8. guarantee an `analysis_date` for every artifact
9. capture whose result it is
10. package the work as a reusable skill/repo for other agents
11. make the repo usable as an agent-first self-hosted open-source toolkit for operators exporting their own gmail lab history

## current status

### green
- `gmail search -> thread -> native attachments`
- `gmail search -> thread -> inline image assets`
- live regression runner for known historical cases
- OCR for image assets
- password-hinted PDF text extraction with OCR fallback
- reproducible runs with `run_manifest.tsv`
- regression review condensed into `regression_summary.tsv`
- explicit separation between acquisition status and enrichment status
- metadata derivation for `analysis_date`
- metadata derivation for `owner`
- non-result support attachments can stay in `raw/` without promotion to `final/`
- canonical filenames in `final/`
- reusable repo + skill structure
- self-hosted local-first product boundary is now explicit in docs
- primary user is now explicitly another ai agent

### yellow
- discovery still depends on maintaining a regression corpus of real historical mails
- `analysis_date` is sometimes inferred from gmail thread date, not direct from artifact
- `owner` can still be `weak_owner` or `unknown_owner` on forwarded / context-only mails
- provider detection is heuristic outside explicit provider hints
- passworded PDFs still need either a discoverable rule in context or an explicit operator hint
- OCR/PDF-text quality still depends on local binaries, but missing tools are now reported as `missing_dependency` instead of fake extraction failure

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
4. expand the live regression corpus beyond the current smoke set so mixed, portal-only, and inline-only cases stay covered
5. reduce first-run setup friction for a new self-hosted agent/operator pair

## what should wait until v2

- username/password/2fa providers
- automatic dedupe across runs
- deeper ownership verification against patient dob or order id

## release judgment

for agent use now:
- yes, as a gmail extraction repo with OCR + metadata derivation

for self-hosted operator use now:
- yes, with browser/cdp setup and honest expectations about provider/login limits

for other ai agents now:
- yes, if they follow the manifest-first contract and stay within the current browser-first live boundary

for claiming universal lab export:
- no

truthful label right now:
- `agent-first self-hosted gmail lab export repo with explicit provenance and metadata status`
