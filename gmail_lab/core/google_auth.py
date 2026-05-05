from __future__ import annotations

from pathlib import Path
from typing import Any

GMAIL_READONLY_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_FILENAME = "gmail-api-token.json"


def default_token_path(root: Path) -> Path:
    return root / "tokens" / TOKEN_FILENAME


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


def google_credentials_status(token_path: Path, scopes: list[str] | None = None) -> dict[str, object]:
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
