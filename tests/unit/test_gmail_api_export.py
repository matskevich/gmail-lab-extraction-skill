from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path


def load_script_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts/run_gmail_api_export.py"
    spec = importlib.util.spec_from_file_location("run_gmail_api_export", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def gmail_b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def test_attachment_assets_include_attachment_id_and_inline_body() -> None:
    module = load_script_module()
    message = {
        "id": "msg-1",
        "threadId": "thread-1",
        "payload": {
            "parts": [
                {
                    "partId": "1",
                    "filename": "report.pdf",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "att-1"},
                },
                {
                    "partId": "2",
                    "filename": "inline.txt",
                    "mimeType": "text/plain",
                    "body": {"data": gmail_b64(b"hello")},
                },
            ]
        },
    }

    assets = module.attachment_assets(message)

    assert [asset.filename for asset in assets] == ["report.pdf", "inline.txt"]
    assert assets[0].attachment_id == "att-1"
    assert assets[1].inline_data


def test_choose_message_matches_attachment_filename_before_first_message() -> None:
    module = load_script_module()
    older = {
        "id": "older",
        "threadId": "thread-older",
        "snippet": "Prodia result",
        "payload": {"headers": [{"name": "Subject", "value": "Prodia"}], "parts": []},
    }
    target = {
        "id": "target",
        "threadId": "thread-target",
        "snippet": "Prodia result",
        "payload": {
            "headers": [{"name": "Subject", "value": "Prodia"}],
            "parts": [
                {
                    "partId": "1",
                    "filename": "2605040024 Mr Dzmitry Matskevich.pdf",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "att-1"},
                }
            ],
        },
    }

    assert module.choose_message([older, target], "2605040024")["id"] == "target"


def test_decode_gmail_base64_accepts_unpadded_urlsafe_data() -> None:
    module = load_script_module()

    assert module.decode_gmail_base64(gmail_b64(b"pdf bytes")) == b"pdf bytes"


def test_gmail_ui_url_is_not_treated_as_api_locator() -> None:
    module = load_script_module()

    assert module.is_gmail_ui_url("https://mail.google.com/mail/u/0/#inbox/FMfcgzQgLjQhgLr")
    assert not module.is_probable_api_id("FMfcgzQgLjQhgLr")


def test_api_id_locator_prefixes() -> None:
    module = load_script_module()

    assert module.api_id_from_locator("message:19df31832eed6691", "message:") == "19df31832eed6691"
    assert module.api_id_from_locator("thread:abc123", "message:") == ""
