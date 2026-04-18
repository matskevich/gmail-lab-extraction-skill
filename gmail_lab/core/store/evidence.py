from __future__ import annotations

import hashlib
import mimetypes
import shutil
from datetime import UTC, datetime
from pathlib import Path

from gmail_lab.core.layout import AppPaths
from gmail_lab.core.models import EvidenceRecord


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class FsEvidenceStore:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def store_evidence(
        self,
        *,
        mailbox: str,
        message_id: str,
        source_file: Path,
        source_kind: str,
        original_filename: str | None = None,
        mime_type: str | None = None,
    ) -> EvidenceRecord:
        target_dir = self.paths.evidence_message_dir(mailbox, message_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = original_filename or source_file.name
        target = target_dir / filename
        shutil.copy2(source_file, target)
        resolved = target.resolve()
        resolved_mime = mime_type or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return EvidenceRecord(
            mailbox=mailbox,
            message_id=message_id,
            source_kind=source_kind,
            original_filename=filename,
            stored_path=str(resolved),
            mime_type=resolved_mime,
            size_bytes=resolved.stat().st_size,
            sha256=_sha256_file(resolved),
            created_at=datetime.now(UTC).isoformat(),
        )
