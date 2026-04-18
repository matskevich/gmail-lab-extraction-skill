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
