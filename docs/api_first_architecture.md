# api-first architecture

the long-term architecture should be `gmail api first` and `browser fallback second`.

the product boundary is still self-hosted and local-first. `gmail api first` is about a more reliable extractor, not about turning this repo into a hosted mailbox service.

the local browser/cdp lane is useful for rescue and debugging, but it is the wrong primary extractor even for a self-hosted tool once a stable gmail api lane exists.

## design principle

build around what the mailbox *contains*, not what the gmail web ui *happens to render today*.

that means:
- oauth connection per mailbox
- gmail api sync and history tracking
- MIME-native parsing
- explicit evidence storage
- browser automation only for fallback and provider portals

## production shape

### 1. auth layer

responsibility:
- connect a mailbox with explicit oauth scopes
- refresh and rotate tokens safely
- fail fast when scope is insufficient

minimum useful scope:
- `gmail.readonly`

optional:
- `gmail.modify` only if the product needs to apply labels such as `processed`

## 2. mailbox sync layer

responsibility:
- first-time full backfill
- later partial sync using `watch -> pub/sub -> history.list`

state to persist:
- mailbox id
- latest synced `historyId`
- watch expiration
- sync checkpoints

important rule:
- if `history.list` returns `404`, history continuity is lost and the client must perform a full resync

## 3. message store

responsibility:
- store stable mailbox truth so parsers can be replayed without re-downloading

recommended fields:
- `message_id`
- `thread_id`
- `internal_date`
- labels
- headers
- snippet
- normalized sender
- provider guess
- parsed payload or raw RFC822

important rule:
- `internalDate` is operationally better than trusting the `Date` header alone

## 4. discovery layer

responsibility:
- find medically relevant threads and classify their extraction class before trying to fetch bytes

classes:
- `candidate_attachment`
- `candidate_inline_only`
- `candidate_portal_only`
- `candidate_context_only`
- `candidate_non_owner`

important rule:
- discovery is not promotion
- partial-ready emails still count as discovery hits even if a later full-ready email supersedes them

## 5. acquisition layer

### gmail-native

responsibility:
- traverse MIME parts from `messages.get(format=full|raw)`
- if a part has `body.data`, decode it
- if a part has `attachmentId`, call `users.messages.attachments.get`
- preserve the raw file and part metadata

### portal-backed

responsibility:
- extract tokenized result links from message content
- hand off to a provider adapter

important rule:
- do not push provider logic into the gmail-native collector

## 6. enrichment layer

responsibility:
- OCR images
- extract PDF text
- infer password hints from provider/thread context
- resolve password candidates through a local secret-resolution layer
- derive date / owner / provider claims

important rule:
- enrichment produces claims
- acquisition produces evidence
- do not merge them
- password hints are evidence; password values are local secrets
- see `docs/secret_resolution.md`

## 7. promotion layer

responsibility:
- choose canonical artifacts for downstream truth
- keep superseded partial-ready emails in discovery history

important rule:
- `best final artifact` and `historical completeness` are not the same thing

## browser fallback lane

browser/cdp should remain for:
- local rescue when oauth scopes are broken
- provider portals that require web interaction
- debugging weird mailbox cases

browser/cdp should not be the primary production extractor for mail that is already reachable via Gmail API.

## testing implications

the test corpus must cover both:
- mailbox discovery correctness
- artifact acquisition correctness

minimum live corpus:
- old ready attachment
- old partial-ready attachment
- virus-scan delayed attachment
- inline-only result thread
- portal-only thread
- mixed thread with both real PDF and banners

## practical migration path

### v1
- keep current browser extractor as fallback
- add an api-native discovery + acquisition lane
- keep current manifests

### v1.1
- replay current enrichment and promotion layers on top of api-native raw artifacts

### v1.2
- unify browser and api acquisition behind one artifact contract

## truthful claim

if the product aims to work across client mailboxes, the durable core is:
- gmail api sync
- MIME parsing
- explicit evidence manifests

the browser lane is supporting infrastructure, not the operating system.
