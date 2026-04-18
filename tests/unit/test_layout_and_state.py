from __future__ import annotations

from gmail_lab.core.layout import AppPaths
from gmail_lab.core.store.state import SqliteStateStore


def test_layout_and_state_init(tmp_path) -> None:
    paths = AppPaths(tmp_path / ".gmail-lab")
    paths.ensure()

    assert paths.root.exists()
    assert paths.tokens_dir.exists()
    assert paths.messages_dir.exists()
    assert paths.evidence_dir.exists()
    assert paths.runs_dir.exists()

    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()

    assert paths.state_db.exists()
    assert state_store.list_mailbox_connections() == []
    assert state_store.list_messages() == []
    assert state_store.list_evidence() == []
