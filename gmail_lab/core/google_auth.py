from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GMAIL_READONLY_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_FILENAME = "gmail-api-token.json"
CLIENT_SECRET_FILENAME = "oauth-client.json"


@dataclass(frozen=True)
class ClientSecretValidation:
    path: Path
    exists: bool
    valid: bool
    client_type: str
    client_id_present: bool
    client_secret_present: bool
    auth_uri_present: bool
    token_uri_present: bool
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "valid": self.valid,
            "client_type": self.client_type,
            "client_id_present": self.client_id_present,
            "client_secret_present": self.client_secret_present,
            "auth_uri_present": self.auth_uri_present,
            "token_uri_present": self.token_uri_present,
            "errors": list(self.errors),
        }


def default_token_path(root: Path) -> Path:
    return root / "tokens" / TOKEN_FILENAME


def default_client_secrets_path(root: Path) -> Path:
    return root / CLIENT_SECRET_FILENAME


def resolve_client_secrets_path(
    *, root: Path, explicit: Path | None = None, env_var: str = "GMAIL_LAB_GOOGLE_CLIENT_SECRET"
) -> Path | None:
    if explicit is not None:
        return explicit.expanduser().resolve()
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    for candidate in [
        default_client_secrets_path(root),
        root / "client_secret.json",
        root / "credentials.json",
    ]:
        if candidate.exists():
            return candidate.expanduser().resolve()
    return None


def client_secret_candidates(
    *, root: Path, home: Path | None = None, cwd: Path | None = None
) -> list[Path]:
    selected_home = home or Path.home()
    selected_cwd = cwd or Path.cwd()
    candidates: list[Path] = [
        default_client_secrets_path(root),
        root / "client_secret.json",
        root / "credentials.json",
        selected_cwd / "oauth-client.json",
        selected_cwd / "client_secret.json",
        selected_cwd / "credentials.json",
    ]
    downloads = selected_home / "Downloads"
    if downloads.exists():
        for pattern in ("client_secret*.json", "credentials*.json", "oauth-client*.json"):
            candidates.extend(sorted(downloads.glob(pattern)))
    return _dedupe_paths(candidates)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def validate_client_secrets(path: Path) -> ClientSecretValidation:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return ClientSecretValidation(
            path=resolved,
            exists=False,
            valid=False,
            client_type="missing",
            client_id_present=False,
            client_secret_present=False,
            auth_uri_present=False,
            token_uri_present=False,
            errors=("file_not_found",),
        )
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ClientSecretValidation(
            path=resolved,
            exists=True,
            valid=False,
            client_type="invalid_json",
            client_id_present=False,
            client_secret_present=False,
            auth_uri_present=False,
            token_uri_present=False,
            errors=(f"invalid_json: {exc}",),
        )
    if not isinstance(data, dict):
        return ClientSecretValidation(
            path=resolved,
            exists=True,
            valid=False,
            client_type="invalid_shape",
            client_id_present=False,
            client_secret_present=False,
            auth_uri_present=False,
            token_uri_present=False,
            errors=("top_level_json_must_be_object",),
        )
    client_type = "installed" if isinstance(data.get("installed"), dict) else ""
    if not client_type and isinstance(data.get("web"), dict):
        client_type = "web"
    payload = data.get(client_type, {}) if client_type else {}
    if not isinstance(payload, dict):
        payload = {}
    client_id_present = bool(payload.get("client_id"))
    client_secret_present = bool(payload.get("client_secret"))
    auth_uri_present = bool(payload.get("auth_uri"))
    token_uri_present = bool(payload.get("token_uri"))
    errors: list[str] = []
    if client_type != "installed":
        errors.append("expected_desktop_app_client_with_top_level_installed")
    if not client_id_present:
        errors.append("missing_client_id")
    if not client_secret_present:
        errors.append("missing_client_secret")
    if not auth_uri_present:
        errors.append("missing_auth_uri")
    if not token_uri_present:
        errors.append("missing_token_uri")
    return ClientSecretValidation(
        path=resolved,
        exists=True,
        valid=not errors,
        client_type=client_type or "unknown",
        client_id_present=client_id_present,
        client_secret_present=client_secret_present,
        auth_uri_present=auth_uri_present,
        token_uri_present=token_uri_present,
        errors=tuple(errors),
    )


def copy_client_secrets(source: Path, destination: Path, *, overwrite: bool = False) -> Path:
    resolved_source = source.expanduser().resolve()
    resolved_destination = destination.expanduser().resolve()
    if resolved_destination.exists() and not overwrite and resolved_destination != resolved_source:
        raise FileExistsError(f"client secrets already exist at {resolved_destination}")
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    if resolved_destination != resolved_source:
        shutil.copyfile(resolved_source, resolved_destination)
    resolved_destination.chmod(0o600)
    return resolved_destination


def load_google_credentials(
    *,
    token_path: Path,
    client_secrets_path: Path | None,
    no_browser: bool = False,
    scopes: list[str] | None = None,
) -> Any:
    selected_scopes = scopes or GMAIL_READONLY_SCOPES
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except Exception as exc:
        raise RuntimeError(f"missing google auth dependencies: {exc}") from exc

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), selected_scopes)  # type: ignore[no-untyped-call]
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not client_secrets_path:
            raise RuntimeError(
                "gmail api auth missing: provide --client-secrets or set "
                f"GMAIL_LAB_GOOGLE_CLIENT_SECRET; token path checked: {token_path}"
            )
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
        except Exception as exc:
            raise RuntimeError(f"missing google oauth dependency: {exc}") from exc

        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), selected_scopes)
        if no_browser:
            auth_url, _ = flow.authorization_url(prompt="consent")
            print(f"open this url and paste the authorization code:\n{auth_url}")
            code = input("authorization code: ").strip()
            flow.fetch_token(code=code)
            creds = flow.credentials
        else:
            creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def google_credentials_status(
    token_path: Path, scopes: list[str] | None = None
) -> dict[str, object]:
    selected_scopes = scopes or GMAIL_READONLY_SCOPES
    status: dict[str, object] = {
        "token_path": str(token_path),
        "exists": token_path.exists(),
        "valid": False,
        "expired": False,
        "has_refresh_token": False,
        "scopes": selected_scopes,
    }
    if not token_path.exists():
        return status
    try:
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(str(token_path), selected_scopes)  # type: ignore[no-untyped-call]
    except Exception as exc:
        status["error"] = str(exc)
        return status
    status["valid"] = bool(creds.valid)
    status["expired"] = bool(creds.expired)
    status["has_refresh_token"] = bool(creds.refresh_token)
    return status


def build_gmail_service(creds: Any) -> Any:
    try:
        from googleapiclient.discovery import build  # type: ignore[import-untyped]
    except Exception as exc:
        raise RuntimeError(f"missing google api client dependency: {exc}") from exc
    return build("gmail", "v1", credentials=creds, cache_discovery=False)
