from __future__ import annotations

import json

from gmail_lab.core.google_auth import (
    copy_client_secrets,
    default_client_secrets_path,
    resolve_client_secrets_path,
    validate_client_secrets,
)


def test_validate_client_secrets_accepts_desktop_oauth_json(tmp_path) -> None:
    path = tmp_path / "oauth-client.json"
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client.apps.googleusercontent.com",
                    "client_secret": "secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )

    status = validate_client_secrets(path)

    assert status.valid is True
    assert status.client_type == "installed"
    assert status.errors == ()


def test_validate_client_secrets_rejects_web_oauth_json(tmp_path) -> None:
    path = tmp_path / "web-client.json"
    path.write_text(
        json.dumps(
            {
                "web": {
                    "client_id": "client.apps.googleusercontent.com",
                    "client_secret": "secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )

    status = validate_client_secrets(path)

    assert status.valid is False
    assert status.client_type == "web"
    assert "expected_desktop_app_client_with_top_level_installed" in status.errors


def test_resolve_client_secrets_path_prefers_canonical_root_file(tmp_path, monkeypatch) -> None:
    root = tmp_path / ".gmail-lab"
    root.mkdir()
    canonical = default_client_secrets_path(root)
    canonical.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("GMAIL_LAB_GOOGLE_CLIENT_SECRET", raising=False)

    assert resolve_client_secrets_path(root=root) == canonical.resolve()


def test_copy_client_secrets_writes_gitignored_canonical_file(tmp_path) -> None:
    source = tmp_path / "downloaded-client.json"
    source.write_text("{}", encoding="utf-8")
    destination = tmp_path / ".gmail-lab" / "oauth-client.json"

    copied = copy_client_secrets(source, destination)

    assert copied == destination.resolve()
    assert copied.read_text(encoding="utf-8") == "{}"
    assert copied.stat().st_mode & 0o777 == 0o600
