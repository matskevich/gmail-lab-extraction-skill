from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MailboxConnection:
    mailbox: str
    gmail_address: str
    scopes_json: str
    connected_at: str
    last_sync_at: str = ""
    last_history_id: str = ""


@dataclass(frozen=True)
class MessageRecord:
    mailbox: str
    message_id: str
    thread_id: str
    internal_date: str
    subject: str
    sender: str
    snippet: str
    labels_json: str
    raw_path: str
    full_path: str
    headers_path: str
    mime_summary_path: str
    discovery_status: str
    discovery_class: str
    attachment_candidate_count: int
    download_url_count: int
    inline_candidate_count: int
    scanning_for_viruses: bool
    query: str
    needle: str
    json_log: str
    stderr_log: str
    created_at: str


@dataclass(frozen=True)
class EvidenceRecord:
    mailbox: str
    message_id: str
    source_kind: str
    original_filename: str
    stored_path: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: str


@dataclass(frozen=True)
class ClaimRecord:
    analysis_id: str
    mailbox: str
    message_id: str
    evidence_sha256: str
    evidence_path: str
    provider: str
    provider_source: str
    category: str
    owner_name: str
    owner_status: str
    owner_source: str
    owner_evidence: str
    analysis_date: str
    analysis_date_source: str
    sample_draw_date: str
    sample_draw_time: str
    sample_draw_datetime: str
    sample_draw_status: str
    sample_draw_source: str
    sample_draw_evidence: str
    confidence: str
    created_at: str
