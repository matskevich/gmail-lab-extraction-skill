from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def tokens_dir(self) -> Path:
        return self.root / "tokens"

    @property
    def messages_dir(self) -> Path:
        return self.root / "messages"

    @property
    def evidence_dir(self) -> Path:
        return self.root / "evidence"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def state_db(self) -> Path:
        return self.root / "state.db"

    def ensure(self) -> None:
        for path in [
            self.root,
            self.tokens_dir,
            self.messages_dir,
            self.evidence_dir,
            self.runs_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def message_dir(self, mailbox: str, message_id: str) -> Path:
        return self.messages_dir / mailbox / message_id

    def evidence_message_dir(self, mailbox: str, message_id: str) -> Path:
        return self.evidence_dir / mailbox / message_id
