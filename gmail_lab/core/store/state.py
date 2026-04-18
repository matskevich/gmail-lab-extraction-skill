from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path

from gmail_lab.core.models import EvidenceRecord, MailboxConnection, MessageRecord


class SqliteStateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mailbox_connections (
                    mailbox TEXT PRIMARY KEY,
                    gmail_address TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    connected_at TEXT NOT NULL,
                    last_sync_at TEXT NOT NULL,
                    last_history_id TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    mailbox TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    internal_date TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    labels_json TEXT NOT NULL,
                    raw_path TEXT NOT NULL,
                    full_path TEXT NOT NULL,
                    headers_path TEXT NOT NULL,
                    mime_summary_path TEXT NOT NULL,
                    discovery_status TEXT NOT NULL,
                    discovery_class TEXT NOT NULL,
                    attachment_candidate_count INTEGER NOT NULL,
                    download_url_count INTEGER NOT NULL,
                    inline_candidate_count INTEGER NOT NULL,
                    scanning_for_viruses INTEGER NOT NULL,
                    query TEXT NOT NULL,
                    needle TEXT NOT NULL,
                    json_log TEXT NOT NULL,
                    stderr_log TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (mailbox, message_id)
                );

                CREATE TABLE IF NOT EXISTS evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mailbox TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', '1')"
            )

    def upsert_mailbox_connection(self, connection: MailboxConnection) -> None:
        payload = asdict(connection)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO mailbox_connections (
                    mailbox, gmail_address, scopes_json, connected_at, last_sync_at, last_history_id
                ) VALUES (
                    :mailbox, :gmail_address, :scopes_json, :connected_at, :last_sync_at, :last_history_id
                )
                ON CONFLICT(mailbox) DO UPDATE SET
                    gmail_address = excluded.gmail_address,
                    scopes_json = excluded.scopes_json,
                    connected_at = excluded.connected_at,
                    last_sync_at = excluded.last_sync_at,
                    last_history_id = excluded.last_history_id
                """,
                payload,
            )

    def list_mailbox_connections(self) -> list[MailboxConnection]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM mailbox_connections ORDER BY mailbox").fetchall()
        return [MailboxConnection(**dict(row)) for row in rows]

    def upsert_message(self, message: MessageRecord) -> None:
        payload = asdict(message)
        payload["scanning_for_viruses"] = int(message.scanning_for_viruses)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    mailbox, message_id, thread_id, internal_date, subject, sender, snippet, labels_json,
                    raw_path, full_path, headers_path, mime_summary_path, discovery_status, discovery_class,
                    attachment_candidate_count, download_url_count, inline_candidate_count, scanning_for_viruses,
                    query, needle, json_log, stderr_log, created_at
                ) VALUES (
                    :mailbox, :message_id, :thread_id, :internal_date, :subject, :sender, :snippet, :labels_json,
                    :raw_path, :full_path, :headers_path, :mime_summary_path, :discovery_status, :discovery_class,
                    :attachment_candidate_count, :download_url_count, :inline_candidate_count, :scanning_for_viruses,
                    :query, :needle, :json_log, :stderr_log, :created_at
                )
                ON CONFLICT(mailbox, message_id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    internal_date = excluded.internal_date,
                    subject = excluded.subject,
                    sender = excluded.sender,
                    snippet = excluded.snippet,
                    labels_json = excluded.labels_json,
                    raw_path = excluded.raw_path,
                    full_path = excluded.full_path,
                    headers_path = excluded.headers_path,
                    mime_summary_path = excluded.mime_summary_path,
                    discovery_status = excluded.discovery_status,
                    discovery_class = excluded.discovery_class,
                    attachment_candidate_count = excluded.attachment_candidate_count,
                    download_url_count = excluded.download_url_count,
                    inline_candidate_count = excluded.inline_candidate_count,
                    scanning_for_viruses = excluded.scanning_for_viruses,
                    query = excluded.query,
                    needle = excluded.needle,
                    json_log = excluded.json_log,
                    stderr_log = excluded.stderr_log,
                    created_at = excluded.created_at
                """,
                payload,
            )

    def list_messages(self, mailbox: str | None = None) -> list[MessageRecord]:
        query = "SELECT * FROM messages"
        params: tuple[str, ...] = ()
        if mailbox:
            query += " WHERE mailbox = ?"
            params = (mailbox,)
        query += " ORDER BY internal_date, mailbox, message_id"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        result: list[MessageRecord] = []
        for row in rows:
            payload = dict(row)
            payload["scanning_for_viruses"] = bool(payload["scanning_for_viruses"])
            result.append(MessageRecord(**payload))
        return result

    def add_evidence(self, evidence: EvidenceRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO evidence (
                    mailbox, message_id, source_kind, original_filename, stored_path, mime_type,
                    size_bytes, sha256, created_at
                ) VALUES (
                    :mailbox, :message_id, :source_kind, :original_filename, :stored_path, :mime_type,
                    :size_bytes, :sha256, :created_at
                )
                """,
                asdict(evidence),
            )

    def list_evidence(self, mailbox: str | None = None) -> list[EvidenceRecord]:
        query = "SELECT mailbox, message_id, source_kind, original_filename, stored_path, mime_type, size_bytes, sha256, created_at FROM evidence"
        params: tuple[str, ...] = ()
        if mailbox:
            query += " WHERE mailbox = ?"
            params = (mailbox,)
        query += " ORDER BY created_at, mailbox, message_id, original_filename"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [EvidenceRecord(**dict(row)) for row in rows]
