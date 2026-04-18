# completeness framework

the extractor needs 4 separate layers of truth. if they are mixed, you get false confidence.

## 1. discovery

question:
- what medically relevant email artifacts exist in the mailbox at all?

output:
- discovery inventory of candidate threads, not yet a medical truth layer

required statuses:
- `candidate_attachment`
- `candidate_inline_only`
- `candidate_portal_only`
- `candidate_context_only`
- `candidate_non_owner`

important rule:
- a partial-ready mail is still a discovery hit, even if it is later superseded by a full-ready mail

## 2. acquisition

question:
- did raw bytes land locally?

output:
- `raw/`
- `run_manifest.tsv`

required statuses:
- `ok`
- `extract_fail`

important rule:
- acquisition is not the same as enrichment

## 3. enrichment

question:
- can we derive text, dates, owner hints, and provider hints?

output:
- `ocr/`
- `pdf_text/`
- `asset_manifest.tsv`

required statuses:
- `ok`
- `partial`
- `missing_dependency`
- `fail`

important rule:
- missing OCR/PDF tools is environment debt, not mailbox debt

## 4. promotion

question:
- should this artifact enter the downstream truth layer?

promotion rules:
- prefer the best terminal artifact for a given order
- keep partial-ready artifacts in discovery/regression history even if they are superseded
- never hide uncertainty around owner or date

## completeness threats

the main failure classes are:

1. search coverage failure
- query never surfaces the thread

2. row selection failure
- search page is stale or wrong row is clicked

3. asset hydration failure
- thread opens, but attachment controls appear only after scroll, delay, or virus-scan completion

4. mixed-thread misclassification
- banners or inline previews are saved, while real PDF attachments are missed

5. promotion drift
- raw evidence exists, but downstream truth layer never gets updated

## why `DCKY28207` matters

`DCKY28207` is a good regression case because:
- it is old
- it has multiple partial-ready mails
- attachment preview can appear before raw attachment controls are hydrated
- it proves the difference between `mail found` and `artifact landed`

if a repo misses this class, the extractor is not yet complete enough for historical recovery.
