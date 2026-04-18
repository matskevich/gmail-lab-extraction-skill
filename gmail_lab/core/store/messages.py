from __future__ import annotations

import shutil
from pathlib import Path

from gmail_lab.core.layout import AppPaths


class FsMessageStore:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def store_message_files(
        self,
        *,
        mailbox: str,
        message_id: str,
        raw_file: Path | None = None,
        full_json_file: Path | None = None,
        headers_json_file: Path | None = None,
        mime_summary_json_file: Path | None = None,
    ) -> dict[str, str]:
        target_dir = self.paths.message_dir(mailbox, message_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        stored: dict[str, str] = {
            "raw_path": "",
            "full_path": "",
            "headers_path": "",
            "mime_summary_path": "",
        }

        mapping = [
            ("raw_path", raw_file, "message.raw"),
            ("full_path", full_json_file, "message.full.json"),
            ("headers_path", headers_json_file, "headers.json"),
            ("mime_summary_path", mime_summary_json_file, "mime_summary.json"),
        ]
        for key, source, target_name in mapping:
            if source is None:
                continue
            target = target_dir / target_name
            shutil.copy2(source, target)
            stored[key] = str(target.resolve())
        return stored
