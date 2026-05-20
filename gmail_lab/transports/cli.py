from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import click

from gmail_lab import __version__
from gmail_lab.core.claims.derive import build_claim_record, claim_to_analysis_row
from gmail_lab.core.config import load_config, resolve_root, save_config
from gmail_lab.core.google_auth import (
    build_gmail_service,
    client_secret_candidates,
    copy_client_secrets,
    default_client_secrets_path,
    default_token_path,
    google_credentials_status,
    load_google_credentials,
    resolve_client_secrets_path,
    validate_client_secrets,
)
from gmail_lab.core.layout import AppPaths
from gmail_lab.core.manifests.analyses import write_analysis_manifest
from gmail_lab.core.manifests.claims import write_claims_manifest
from gmail_lab.core.manifests.discovery import write_discovery_manifest
from gmail_lab.core.manifests.evidence import write_evidence_manifest
from gmail_lab.core.models import MailboxConnection, MessageRecord
from gmail_lab.core.runs import explain_run
from gmail_lab.core.secrets.models import SecretMetadata
from gmail_lab.core.secrets.store import SecretStore, SecretStoreUnavailable
from gmail_lab.core.store.evidence import FsEvidenceStore
from gmail_lab.core.store.messages import FsMessageStore
from gmail_lab.core.store.state import SqliteStateStore


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@click.group()
@click.option("--root", type=click.Path(path_type=Path, file_okay=False), default=None)
@click.version_option(version=__version__)
@click.pass_context
def main(ctx: click.Context, root: Path | None) -> None:
    resolved_root = resolve_root(root)
    paths = AppPaths(resolved_root)
    ctx.ensure_object(dict)
    ctx.obj["paths"] = paths


def _paths_from_context(ctx: click.Context) -> AppPaths:
    return cast(AppPaths, ctx.obj["paths"])


def _echo_run_explanation(run_dir: Path) -> None:
    click.echo(json.dumps(explain_run(run_dir), ensure_ascii=False, indent=2))


def _emit_acquisition_result(lane: str, run_dir: Path) -> None:
    explanation = explain_run(run_dir)
    state = str(explanation.get("state", "unknown"))
    payload = {
        "lane": lane,
        "run_dir": str(run_dir),
        "status": "ok",
        "state": state,
        "counts": explanation.get("counts", {}),
        "blockers": explanation.get("blockers", []),
        "next_steps": explanation.get("next_steps", []),
    }
    if state in {"acquisition_blocked", "missing_run_manifest", "no_raw_assets"}:
        payload["status"] = "blocked"
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        raise click.ClickException(f"gmail acquisition blocked after collector run: {state}")
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@main.command("init")
@click.pass_context
def init_command(ctx: click.Context) -> None:
    paths = _paths_from_context(ctx)
    paths.ensure()
    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()
    config = load_config(paths.root)
    config_path = save_config(paths.root, config)
    click.echo(
        json.dumps(
            {
                "root": str(paths.root),
                "config": str(config_path),
                "state_db": str(paths.state_db),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@main.command("setup")
@click.option("--client-secrets", type=click.Path(path_type=Path), default=None)
@click.option("--token", type=click.Path(path_type=Path), default=None)
@click.option(
    "--no-browser", is_flag=True, help="Print OAuth URL and ask for an authorization code."
)
@click.option(
    "--skip-auth", is_flag=True, help="Initialize and report auth state without starting OAuth."
)
@click.pass_context
def setup_command(
    ctx: click.Context,
    client_secrets: Path | None,
    token: Path | None,
    no_browser: bool,
    skip_auth: bool,
) -> None:
    """First-run local setup for a self-hosted Gmail lab extractor install."""

    paths = _paths_from_context(ctx)
    paths.ensure()
    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()
    config_path = save_config(paths.root, load_config(paths.root))
    token_path = token.expanduser().resolve() if token else default_token_path(paths.root)
    client_secrets_path = _resolve_google_client_secrets_path(paths, client_secrets)
    auth_attempted = False
    auth_error = ""
    profile: dict[str, object] = {}

    if (
        not skip_auth
        and client_secrets_path is not None
        and not google_credentials_status(token_path).get("valid")
    ):
        auth_attempted = True
        try:
            creds = load_google_credentials(
                token_path=token_path,
                client_secrets_path=client_secrets_path,
                no_browser=no_browser,
            )
            gmail_profile = build_gmail_service(creds).users().getProfile(userId="me").execute()
            profile = {
                "gmail_address": gmail_profile.get("emailAddress", ""),
                "messages_total": gmail_profile.get("messagesTotal", ""),
                "threads_total": gmail_profile.get("threadsTotal", ""),
            }
        except RuntimeError as exc:
            auth_error = str(exc)

    auth_status = google_credentials_status(token_path)
    dependencies = _dependency_status()
    next_steps = _setup_next_steps(
        auth_valid=bool(auth_status.get("valid")),
        client_secrets_path=client_secrets_path,
        missing_dependencies=[
            name for name, details in dependencies.items() if not bool(details.get("found"))
        ],
        auth_error=auth_error,
    )
    click.echo(
        json.dumps(
            {
                "root": str(paths.root),
                "initialized": True,
                "config": str(config_path),
                "state_db": str(paths.state_db),
                "dependencies": dependencies,
                "gmail_api": {
                    "token_path": str(token_path),
                    "auth_attempted": auth_attempted,
                    "auth_error": auth_error,
                    "status": auth_status,
                    "profile": profile,
                },
                "ready": bool(auth_status.get("valid")) and not next_steps,
                "next_steps": next_steps,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _dependency_status() -> dict[str, dict[str, str | bool]]:
    return {
        name: {
            "found": shutil.which(name) is not None,
            "path": shutil.which(name) or "",
        }
        for name in ["pdftotext", "pdftoppm", "tesseract"]
    }


def _setup_next_steps(
    *,
    auth_valid: bool,
    client_secrets_path: Path | None,
    missing_dependencies: list[str],
    auth_error: str,
) -> list[str]:
    next_steps: list[str] = []
    if missing_dependencies:
        next_steps.append(
            "install missing OCR/PDF tools, for example `brew install tesseract poppler`"
        )
    if auth_error:
        next_steps.append(
            "fix OAuth error, then rerun `gmail-lab setup-google --client-secrets <oauth-desktop-client.json>`"
        )
    elif not auth_valid and client_secrets_path is None:
        next_steps.append(
            "run `gmail-lab setup-google --client-secrets <oauth-desktop-client.json>`"
        )
    elif not auth_valid:
        next_steps.append("rerun `gmail-lab setup-google`")
    return next_steps


def _resolve_google_client_secrets_path(paths: AppPaths, explicit: Path | None) -> Path | None:
    return resolve_client_secrets_path(root=paths.root, explicit=explicit)


def _google_setup_guide() -> dict[str, object]:
    return {
        "google_cloud_console": "https://console.cloud.google.com/",
        "gmail_api_enable": "https://console.cloud.google.com/apis/library/gmail.googleapis.com",
        "oauth_clients": "https://console.cloud.google.com/auth/clients",
        "official_quickstart": "https://developers.google.com/gmail/api/quickstart/python",
        "required_google_steps": [
            "create or select a Google Cloud project",
            "make sure the Google account can access Google Cloud Console; Google may require 2-step verification",
            "enable Gmail API",
            "configure Google Auth platform / OAuth consent screen",
            "create OAuth client with application type Desktop app",
            "download the client JSON",
        ],
        "cloud_console_auth_gate": "If Google Cloud Console shows `Google Cloud access blocked`, enable 2-step verification for that Google account before creating the OAuth client.",
        "local_client_secret_path": "~/.gmail-lab/oauth-client.json",
        "local_token_path": "~/.gmail-lab/tokens/gmail-api-token.json",
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
    }


def _client_secret_candidate_payloads(paths: AppPaths) -> list[dict[str, object]]:
    return [
        validation.as_dict()
        for validation in [
            validate_client_secrets(candidate)
            for candidate in client_secret_candidates(root=paths.root)
            if candidate.exists()
        ]
    ]


def _pick_setup_google_client_secret(
    *,
    paths: AppPaths,
    explicit: Path | None,
    candidates: list[dict[str, object]],
) -> Path | None:
    if explicit is not None:
        return explicit.expanduser().resolve()
    canonical = default_client_secrets_path(paths.root).expanduser().resolve()
    for candidate in candidates:
        if candidate.get("valid") and Path(str(candidate.get("path", ""))) == canonical:
            return canonical
    valid_paths = [
        Path(str(candidate["path"])) for candidate in candidates if candidate.get("valid")
    ]
    if len(valid_paths) == 1:
        return valid_paths[0]
    return None


def _setup_google_next_steps(
    *,
    token_valid: bool,
    selected_client_secrets: Path | None,
    selected_client_secret_exists: bool | None,
    selected_client_secret_valid: bool,
    client_secret_candidates_found: list[dict[str, object]],
    auth_error: str,
    check_only: bool,
) -> list[str]:
    if token_valid:
        return ["run `gmail-lab verify-gmail-paths --targets-tsv <targets.tsv> --allow-live`"]
    if auth_error:
        return [
            "fix the OAuth error, then rerun `gmail-lab setup-google --client-secrets ~/.gmail-lab/oauth-client.json`"
        ]
    if selected_client_secrets is not None and selected_client_secret_exists is False:
        return [
            f"download a Google Desktop OAuth client JSON to `{selected_client_secrets}` or rerun with the correct `--client-secrets` path"
        ]
    if selected_client_secrets is not None and not selected_client_secret_valid:
        return [
            f"replace `{selected_client_secrets}` with a Google Desktop OAuth client JSON, then rerun `gmail-lab setup-google --client-secrets {selected_client_secrets}`"
        ]
    if selected_client_secrets is not None and check_only:
        return [f"run `gmail-lab setup-google --client-secrets {selected_client_secrets}`"]
    valid_candidates = [
        candidate for candidate in client_secret_candidates_found if candidate.get("valid")
    ]
    if len(valid_candidates) > 1 and selected_client_secrets is None:
        return [
            "choose one Desktop OAuth client JSON and rerun `gmail-lab setup-google --client-secrets <path-to-json>`"
        ]
    if selected_client_secrets is not None:
        return ["complete the browser OAuth consent window opened by `gmail-lab setup-google`"]
    return [
        "create a Google Cloud Desktop OAuth client JSON, save it as `~/.gmail-lab/oauth-client.json`, then run `gmail-lab setup-google`"
    ]


@main.command("identity-status")
@click.pass_context
def identity_status_command(ctx: click.Context) -> None:
    paths = _paths_from_context(ctx)
    paths.ensure()
    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()
    config = load_config(paths.root)
    identity = config.identity.model_dump(mode="python")
    if identity.get("birth_date"):
        identity["birth_date"] = "redacted"
    birth_date_secret_id = str(identity.get("birth_date_secret_id", "") or "")
    identity["birth_date_secret"] = _secret_reference_status(paths, birth_date_secret_id)
    mailboxes = [asdict(row) for row in state_store.list_mailbox_connections()]
    click.echo(
        json.dumps(
            {
                "root": str(paths.root),
                "identity": identity,
                "mailboxes": mailboxes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _secret_reference_status(paths: AppPaths, secret_id: str) -> dict[str, str | bool]:
    if not secret_id:
        return {
            "secret_id": "",
            "configured": False,
            "resolvable": False,
            "persistence": "none",
            "legacy": False,
        }
    try:
        value, persistence = SecretStore(paths.root).get(secret_id)
    except SecretStoreUnavailable:
        value, persistence = None, "none"
    legacy_target = _legacy_pdf_unlock_target(secret_id)
    status: dict[str, str | bool] = {
        "secret_id": secret_id,
        "configured": True,
        "resolvable": bool(value),
        "persistence": persistence if value else "none",
        "value": "redacted" if value else "",
        "legacy": bool(legacy_target),
    }
    if legacy_target:
        status["suggested_secret_id"] = legacy_target
        status["migration_command"] = "gmail-lab migrate-pdf-secrets"
    return status


def _legacy_pdf_unlock_target(secret_id: str) -> str:
    if secret_id.startswith("pdf_unlock:"):
        return ""
    if secret_id.startswith("identity:") or secret_id.startswith("provider_identity:"):
        return f"pdf_unlock:{secret_id}"
    return ""


@main.command("remember-pdf-secret")
@click.option("--identity-alias", default="default", show_default=True)
@click.option(
    "--provider",
    default="",
    help="Provider name such as prodia. Optional for identity-scoped secrets.",
)
@click.option(
    "--scope",
    type=click.Choice(["identity", "provider_identity"]),
    default="identity",
    show_default=True,
    help="Use identity for reusable personal facts; provider_identity for provider-specific passwords.",
)
@click.option(
    "--hint-type",
    type=click.Choice(["birth_date_ddmmyyyy", "password_hint"]),
    default="birth_date_ddmmyyyy",
    show_default=True,
)
@click.option(
    "--persistence",
    type=click.Choice(["keychain", "encrypted-file"]),
    default="keychain",
    show_default=True,
)
@click.option(
    "--value-env",
    default="",
    help="Read secret value from this environment variable instead of prompting. The value is never printed.",
)
@click.pass_context
def remember_pdf_secret_command(
    ctx: click.Context,
    identity_alias: str,
    provider: str,
    scope: str,
    hint_type: str,
    persistence: str,
    value_env: str,
) -> None:
    """Store a local PDF secret without writing the value to repo files or manifests."""

    paths = _paths_from_context(ctx)
    paths.ensure()
    identity = identity_alias.strip().lower() or "default"
    provider_key = provider.strip().lower()
    if scope == "provider_identity" and not provider_key:
        raise click.ClickException("--provider is required when --scope=provider_identity")

    if value_env:
        secret_value = os.environ.get(value_env, "")
        if not secret_value:
            raise click.ClickException(f"environment variable {value_env} is empty or unset")
        input_source = f"env:{value_env}"
    else:
        secret_value = click.prompt(
            "PDF password/date secret",
            hide_input=True,
            confirmation_prompt=False,
            type=str,
        )
        input_source = "hidden_prompt"

    if not secret_value.strip():
        raise click.ClickException("empty secret value")

    secret_id = _purpose_secret_id("pdf_unlock", scope, provider_key, identity)
    metadata = SecretMetadata(
        secret_id=secret_id,
        label=hint_type,
        provider=provider_key,
        identity_alias=identity,
        purpose="pdf_unlock",
        hint_type=hint_type,
        scope=scope,  # type: ignore[arg-type]
        persistence=persistence,  # type: ignore[arg-type]
    )
    try:
        actual_persistence = SecretStore(paths.root).put(secret_id, secret_value.strip(), metadata)
    except SecretStoreUnavailable as exc:
        raise click.ClickException(str(exc)) from exc

    config = load_config(paths.root)
    if hint_type == "birth_date_ddmmyyyy" and scope == "identity":
        config.identity.birth_date = ""
        config.identity.birth_date_secret_id = secret_id
        if identity != "default":
            config.identity.aliases = sorted(set([*config.identity.aliases, identity]))
        save_config(paths.root, config)

    click.echo(
        json.dumps(
            {
                "root": str(paths.root),
                "secret_id": secret_id,
                "scope": scope,
                "provider": provider_key,
                "identity_alias": identity,
                "hint_type": hint_type,
                "persistence": actual_persistence,
                "input_source": input_source,
                "value": "redacted",
                "config_birth_date_secret_id_updated": hint_type == "birth_date_ddmmyyyy"
                and scope == "identity",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _purpose_secret_id(purpose: str, scope: str, provider: str, identity: str) -> str:
    if scope == "identity":
        return f"{purpose}:identity:{identity}"
    return f"{purpose}:provider_identity:{provider}:{identity}"


@main.command("migrate-pdf-secrets")
@click.pass_context
def migrate_pdf_secrets_command(ctx: click.Context) -> None:
    """Copy legacy PDF unlock secret refs into purpose-namespaced ids."""

    paths = _paths_from_context(ctx)
    paths.ensure()
    config = load_config(paths.root)
    source_secret_id = config.identity.birth_date_secret_id.strip()
    target_secret_id = _legacy_pdf_unlock_target(source_secret_id)
    if not source_secret_id:
        click.echo(
            json.dumps(
                {
                    "root": str(paths.root),
                    "migrated": False,
                    "reason": "no_birth_date_secret_id",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if not target_secret_id:
        click.echo(
            json.dumps(
                {
                    "root": str(paths.root),
                    "migrated": False,
                    "reason": "already_purpose_namespaced",
                    "secret_id": source_secret_id,
                    "value": "redacted",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    store = SecretStore(paths.root)
    try:
        value, source_persistence = store.get(source_secret_id)
    except SecretStoreUnavailable as exc:
        raise click.ClickException(str(exc)) from exc
    if not value:
        click.echo(
            json.dumps(
                {
                    "root": str(paths.root),
                    "migrated": False,
                    "reason": "legacy_secret_not_resolvable",
                    "source_secret_id": source_secret_id,
                    "target_secret_id": target_secret_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    identity_alias = source_secret_id.split(":")[-1] if ":" in source_secret_id else "default"
    provider = ""
    scope = "identity"
    if source_secret_id.startswith("provider_identity:"):
        parts = source_secret_id.split(":")
        provider = parts[1] if len(parts) > 1 else ""
        identity_alias = parts[2] if len(parts) > 2 else identity_alias
        scope = "provider_identity"
    metadata = SecretMetadata(
        secret_id=target_secret_id,
        label="birth_date_ddmmyyyy",
        provider=provider,
        identity_alias=identity_alias,
        purpose="pdf_unlock",
        hint_type="birth_date_ddmmyyyy",
        scope=scope,  # type: ignore[arg-type]
        persistence=source_persistence
        if source_persistence in {"keychain", "encrypted-file"}
        else "keychain",  # type: ignore[arg-type]
    )
    try:
        target_persistence = store.put(target_secret_id, value, metadata)
    except SecretStoreUnavailable as exc:
        raise click.ClickException(str(exc)) from exc

    config.identity.birth_date = ""
    config.identity.birth_date_secret_id = target_secret_id
    save_config(paths.root, config)
    click.echo(
        json.dumps(
            {
                "root": str(paths.root),
                "migrated": True,
                "source_secret_id": source_secret_id,
                "source_persistence": source_persistence,
                "target_secret_id": target_secret_id,
                "target_persistence": target_persistence,
                "config_birth_date_secret_id_updated": True,
                "value": "redacted",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@main.command("remember-portal-secret")
@click.option("--provider", required=True, help="Provider name such as prodia.")
@click.option("--identity-alias", default="default", show_default=True)
@click.option(
    "--secret-type",
    type=click.Choice(["account_password", "patient_gate_hint"]),
    default="account_password",
    show_default=True,
    help="Portal account login and patient gate hints are separate secret purposes.",
)
@click.option(
    "--persistence",
    type=click.Choice(["keychain", "encrypted-file"]),
    default="keychain",
    show_default=True,
)
@click.option(
    "--value-env",
    default="",
    help="Read secret value from this environment variable instead of prompting. The value is never printed.",
)
@click.pass_context
def remember_portal_secret_command(
    ctx: click.Context,
    provider: str,
    identity_alias: str,
    secret_type: str,
    persistence: str,
    value_env: str,
) -> None:
    """Store a portal-scoped secret without making it available to PDF unlock."""

    paths = _paths_from_context(ctx)
    paths.ensure()
    provider_key = provider.strip().lower()
    if not provider_key:
        raise click.ClickException("--provider is required")
    identity = identity_alias.strip().lower() or "default"

    if value_env:
        secret_value = os.environ.get(value_env, "")
        if not secret_value:
            raise click.ClickException(f"environment variable {value_env} is empty or unset")
        input_source = f"env:{value_env}"
    else:
        secret_value = click.prompt(
            "Portal secret",
            hide_input=True,
            confirmation_prompt=False,
            type=str,
        )
        input_source = "hidden_prompt"

    if not secret_value.strip():
        raise click.ClickException("empty secret value")

    purpose = "portal_login" if secret_type == "account_password" else "portal_patient_gate"
    secret_id = _purpose_secret_id(purpose, "provider_identity", provider_key, identity)
    metadata = SecretMetadata(
        secret_id=secret_id,
        label=secret_type,
        provider=provider_key,
        identity_alias=identity,
        purpose=purpose,  # type: ignore[arg-type]
        hint_type=secret_type,
        scope="provider_identity",
        persistence=persistence,  # type: ignore[arg-type]
    )
    try:
        actual_persistence = SecretStore(paths.root).put(secret_id, secret_value.strip(), metadata)
    except SecretStoreUnavailable as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        json.dumps(
            {
                "root": str(paths.root),
                "secret_id": secret_id,
                "purpose": purpose,
                "provider": provider_key,
                "identity_alias": identity,
                "secret_type": secret_type,
                "persistence": actual_persistence,
                "input_source": input_source,
                "value": "redacted",
                "pdf_unlock_available": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@main.command("unlock-pdf-run")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--all",
    "rerun_all",
    is_flag=True,
    help="Re-run all successful rows, not only blocked/non-ok enrichment rows.",
)
@click.option(
    "--prompt-secrets/--no-prompt-secrets",
    default=True,
    show_default=True,
    help="Prompt locally for PDF password/date secrets when needed.",
)
@click.option(
    "--remember-secret",
    type=click.Choice(["never", "session", "keychain", "encrypted-file"]),
    default="session",
    show_default=True,
    help="Persistence for secrets entered through --prompt-secrets.",
)
@click.pass_context
def unlock_pdf_run_command(
    ctx: click.Context,
    run_dir: Path,
    rerun_all: bool,
    prompt_secrets: bool,
    remember_secret: str,
) -> None:
    """Re-run PDF text extraction for an existing raw run using local secret resolution."""

    paths = _paths_from_context(ctx)
    paths.ensure()
    script = _repo_root() / "scripts/rerun_enrichment.py"
    args = [sys.executable, str(script), str(run_dir.expanduser().resolve())]
    if rerun_all:
        args.append("--all")
    if prompt_secrets:
        args.append("--prompt-secrets")
    args.extend(["--remember-secret", remember_secret])
    env = os.environ.copy()
    env["GMAIL_LAB_ROOT"] = str(paths.root)
    proc = subprocess.run(args, check=False, text=True, env=env)
    if proc.returncode != 0:
        raise click.ClickException(f"pdf run unlock failed with exit code {proc.returncode}")
    click.echo(
        json.dumps(
            {
                "run_dir": str(run_dir.expanduser().resolve()),
                "prompt_secrets": prompt_secrets,
                "remember_secret": remember_secret,
                "value": "redacted",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@main.command("setup-google")
@click.option("--client-secrets", type=click.Path(path_type=Path), default=None)
@click.option("--token", type=click.Path(path_type=Path), default=None)
@click.option(
    "--no-browser", is_flag=True, help="Print OAuth URL and ask for an authorization code."
)
@click.option(
    "--check-only",
    is_flag=True,
    help="Only inspect local OAuth files and print the setup plan.",
)
@click.option(
    "--no-copy-client-secrets",
    is_flag=True,
    help="Use the selected client JSON in place instead of copying it to ~/.gmail-lab/oauth-client.json.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite ~/.gmail-lab/oauth-client.json when copying a selected client JSON.",
)
@click.pass_context
def setup_google_command(
    ctx: click.Context,
    client_secrets: Path | None,
    token: Path | None,
    no_browser: bool,
    check_only: bool,
    no_copy_client_secrets: bool,
    force: bool,
) -> None:
    """Predictable Gmail API OAuth setup for local agents and open-source users."""

    paths = _paths_from_context(ctx)
    paths.ensure()
    SqliteStateStore(paths.state_db).initialize()
    save_config(paths.root, load_config(paths.root))
    token_path = token.expanduser().resolve() if token else default_token_path(paths.root)
    candidates = _client_secret_candidate_payloads(paths)
    selected_client_secrets = _pick_setup_google_client_secret(
        paths=paths,
        explicit=client_secrets,
        candidates=candidates,
    )
    selected_validation = (
        validate_client_secrets(selected_client_secrets) if selected_client_secrets else None
    )
    canonical_client_secrets = default_client_secrets_path(paths.root)
    copied_to_canonical = False
    auth_attempted = False
    auth_error = ""
    profile: dict[str, object] = {}
    initial_token_status = google_credentials_status(token_path)
    client_secret_for_auth = selected_client_secrets

    if (
        selected_validation is not None
        and selected_validation.valid
        and not no_copy_client_secrets
        and not check_only
    ):
        try:
            was_canonical = (
                selected_validation.path == canonical_client_secrets.expanduser().resolve()
            )
            client_secret_for_auth = copy_client_secrets(
                selected_validation.path,
                canonical_client_secrets,
                overwrite=force,
            )
            copied_to_canonical = not was_canonical
        except FileExistsError as exc:
            auth_error = f"{exc}; pass --force to replace it or --no-copy-client-secrets to use the selected file in place"

    if (
        not check_only
        and not auth_error
        and selected_validation is not None
        and selected_validation.valid
        and not bool(initial_token_status.get("valid"))
    ):
        auth_attempted = True
        try:
            creds = load_google_credentials(
                token_path=token_path,
                client_secrets_path=client_secret_for_auth,
                no_browser=no_browser,
            )
            gmail_profile = build_gmail_service(creds).users().getProfile(userId="me").execute()
            profile = {
                "gmail_address": gmail_profile.get("emailAddress", ""),
                "messages_total": gmail_profile.get("messagesTotal", ""),
                "threads_total": gmail_profile.get("threadsTotal", ""),
            }
        except RuntimeError as exc:
            auth_error = str(exc)

    final_token_status = google_credentials_status(token_path)
    next_steps = _setup_google_next_steps(
        token_valid=bool(final_token_status.get("valid")),
        selected_client_secrets=selected_validation.path
        if selected_validation is not None
        else None,
        selected_client_secret_exists=selected_validation.exists
        if selected_validation is not None
        else None,
        selected_client_secret_valid=bool(
            selected_validation.valid if selected_validation is not None else False
        ),
        client_secret_candidates_found=candidates,
        auth_error=auth_error,
        check_only=check_only,
    )
    click.echo(
        json.dumps(
            {
                "root": str(paths.root),
                "ready": bool(final_token_status.get("valid")),
                "client_secrets": {
                    "canonical_path": str(canonical_client_secrets),
                    "selected_path": str(selected_validation.path)
                    if selected_validation is not None
                    else "",
                    "selected": selected_validation.as_dict()
                    if selected_validation is not None
                    else {},
                    "candidates": candidates,
                    "copied_to_canonical": copied_to_canonical,
                    "value": "redacted",
                },
                "gmail_api": {
                    "token_path": str(token_path),
                    "status": final_token_status,
                    "auth_attempted": auth_attempted,
                    "auth_error": auth_error,
                    "profile": profile,
                },
                "guide": _google_setup_guide(),
                "next_steps": next_steps,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@main.command("auth-google")
@click.option("--client-secrets", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--token", type=click.Path(path_type=Path), default=None)
@click.option(
    "--no-browser", is_flag=True, help="Print OAuth URL and ask for an authorization code."
)
@click.pass_context
def auth_google_command(
    ctx: click.Context,
    client_secrets: Path | None,
    token: Path | None,
    no_browser: bool,
) -> None:
    paths = _paths_from_context(ctx)
    paths.ensure()
    client_secrets_path = _resolve_google_client_secrets_path(paths, client_secrets)
    token_path = token.expanduser().resolve() if token else default_token_path(paths.root)
    try:
        creds = load_google_credentials(
            token_path=token_path,
            client_secrets_path=client_secrets_path,
            no_browser=no_browser,
        )
        profile = build_gmail_service(creds).users().getProfile(userId="me").execute()
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                "token_path": str(token_path),
                "gmail_address": profile.get("emailAddress", ""),
                "messages_total": profile.get("messagesTotal", ""),
                "threads_total": profile.get("threadsTotal", ""),
                "scopes": ["gmail.readonly"],
                "valid": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@main.command("google-auth-status")
@click.option("--token", type=click.Path(path_type=Path), default=None)
@click.pass_context
def google_auth_status_command(ctx: click.Context, token: Path | None) -> None:
    paths = _paths_from_context(ctx)
    token_path = token.expanduser().resolve() if token else default_token_path(paths.root)
    click.echo(json.dumps(google_credentials_status(token_path), ensure_ascii=False, indent=2))


@main.command("explain-run")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def explain_run_command(run_dir: Path) -> None:
    """Explain run state, blockers, and next commands from manifests."""

    _echo_run_explanation(run_dir)


@main.command("status")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def status_command(run_dir: Path) -> None:
    """Alias for explain-run for agent handoffs and quick operator checks."""

    _echo_run_explanation(run_dir)


def _cdp_json(url: str, timeout: float = 1.0) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if isinstance(data, dict):
        return data
    return {}


def _tail_text(value: str, limit: int = 1600) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _summarize_cdp_smoke_output(value: str) -> str:
    """Keep auth/debug markers without leaking mailbox subjects or snippets."""

    markers: list[str] = []
    row_count_match = re.search(r'"rowCount"\s*:\s*(\d+)', value)
    if row_count_match:
        markers.append(f"rowCount={row_count_match.group(1)}")
    authenticated_match = re.search(r'"authenticated"\s*:\s*(true|false)', value)
    if authenticated_match:
        markers.append(f"authenticated={authenticated_match.group(1)}")
    auth_gate_match = re.search(r'"authGate"\s*:\s*(true|false)', value)
    if auth_gate_match:
        markers.append(f"authGate={auth_gate_match.group(1)}")
    for token in [
        "gmail_not_authenticated",
        "cdp_down",
        "auth gate",
        "Search results",
        "Gmail",
    ]:
        if token in value:
            markers.append(f"marker={token}")
    return "; ".join(_dedupe_preserving_order(markers)) or "redacted_gmail_smoke_output"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _slugify(value: str) -> str:
    text = re.sub(r"\s+", "-", value.strip().lower())
    text = re.sub(r"[^a-z0-9_.-]+", "-", text, flags=re.IGNORECASE)
    text = re.sub(r"-{2,}", "-", text).strip("-.")
    return text[:80] or "target"


def _read_target_rows(path: Path) -> list[tuple[int, str, str]]:
    rows: list[tuple[int, str, str]] = []
    for index, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        parts = raw_line.split("\t")
        locator = parts[0].strip()
        if not locator:
            continue
        needle = parts[1].strip() if len(parts) > 1 else ""
        rows.append((index, locator, needle))
    return rows


def _write_empty_evidence_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\t".join(
            [
                "line_no",
                "mailbox",
                "message_id",
                "source_kind",
                "original_filename",
                "stored_path",
                "mime_type",
                "size_bytes",
                "sha256",
                "created_at",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_blocked_acquisition_run(
    *,
    targets_tsv: Path,
    run_dir: Path,
    status: str,
    diagnostic: dict[str, object],
) -> None:
    raw_root = run_dir / "raw"
    logs_dir = run_dir / "logs"
    raw_root.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "ocr").mkdir(exist_ok=True)
    (run_dir / "pdf_text").mkdir(exist_ok=True)

    (logs_dir / "acquisition_diagnostic.json").write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_empty_evidence_manifest(run_dir / "evidence_manifest.tsv")

    header = [
        "line_no",
        "slug",
        "mode",
        "status",
        "extracted_count",
        "ocr_status",
        "pdf_text_status",
        "enrichment_status",
        "raw_dir",
        "ocr_manifest",
        "pdf_text_manifest",
        "json_log",
        "stderr_log",
        "query",
        "needle",
    ]
    lines = ["\t".join(header)]
    for row_index, locator, needle in _read_target_rows(targets_tsv):
        slug = _slugify(f"{row_index}-{needle or locator}")
        row_raw_dir = raw_root / slug
        row_raw_dir.mkdir(parents=True, exist_ok=True)
        json_log = logs_dir / f"{slug}.acquire.json"
        stderr_log = logs_dir / f"{slug}.acquire.stderr.log"
        row_payload = {
            "transport": "gmail_acquisition_router",
            "status": status,
            "query": locator,
            "rowNeedle": needle,
            "diagnostic": diagnostic,
            "savedCounts": {"attachment": 0},
            "saved": [],
        }
        json_log.write_text(json.dumps(row_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        stderr_log.write_text(f"{status}\n", encoding="utf-8")
        lines.append(
            "\t".join(
                [
                    str(row_index),
                    slug,
                    "router",
                    status,
                    "0",
                    "not_applicable",
                    "not_applicable",
                    "blocked_by_acquisition",
                    str(row_raw_dir.resolve()),
                    "-",
                    "-",
                    str(json_log.resolve()),
                    str(stderr_log.resolve()),
                    locator,
                    needle,
                ]
            )
        )
    (run_dir / "run_manifest.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cdp_port_is_up(port: int) -> bool:
    try:
        _cdp_json(f"http://127.0.0.1:{port}/json/version", timeout=1)
    except (OSError, urllib.error.URLError, TimeoutError):
        return False
    return True


def _start_persistent_cdp_profile(
    *,
    port: int,
    run_dir: Path,
    url: str,
    wait_seconds: int,
) -> dict[str, object]:
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "persistent_cdp_profile.log"
    status: dict[str, object] = {
        "requested": True,
        "port": port,
        "url": url,
        "log": str(log_path.resolve()),
        "started": False,
        "reachable": False,
    }
    if _cdp_port_is_up(port):
        status["already_running"] = True
        status["reachable"] = True
        return status

    script = _repo_root() / "skills/gmail-browser-attachments/scripts/start_chrome_cdp_profile.sh"
    if not script.exists():
        status["error"] = f"missing persistent cdp launcher: {script}"
        return status

    env = os.environ.copy()
    env["PORT"] = str(port)
    log_fh = log_path.open("ab")
    try:
        proc = subprocess.Popen(
            [str(script), url],
            stdout=log_fh,
            stderr=log_fh,
            env=env,
            start_new_session=True,
        )
    finally:
        log_fh.close()
    status["started"] = True
    status["pid"] = proc.pid
    for _ in range(max(wait_seconds, 0)):
        if _cdp_port_is_up(port):
            status["reachable"] = True
            break
        time.sleep(1)
    return status


def _diagnose_cdp(port: int, run_smoke: bool) -> dict[str, object]:
    base_url = f"http://127.0.0.1:{port}"
    status: dict[str, object] = {
        "port": port,
        "up": False,
        "authenticated_gmail": False,
        "state": "cdp_down",
    }
    try:
        version = _cdp_json(f"{base_url}/json/version")
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        status["error"] = str(exc)
        return status
    status["up"] = True
    status["state"] = "cdp_up_unknown_auth"
    status["browser"] = version.get("Browser", "")

    if not run_smoke:
        return status

    smoke_script = _repo_root() / "skills/gmail-browser-attachments/scripts/gmail_smoke_check.sh"
    if not smoke_script.exists():
        status["state"] = "cdp_smoke_missing"
        status["error"] = f"missing smoke script: {smoke_script}"
        return status
    try:
        proc = subprocess.run(
            [str(smoke_script), str(port)],
            check=False,
            capture_output=True,
            text=True,
            timeout=25,
        )
    except subprocess.TimeoutExpired as exc:
        status["state"] = "cdp_smoke_timeout"
        status["error"] = str(exc)
        return status

    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    status["smoke_exit_code"] = proc.returncode
    status["smoke_excerpt"] = _summarize_cdp_smoke_output(combined)
    if proc.returncode == 0:
        status["authenticated_gmail"] = True
        status["state"] = "cdp_authenticated_gmail"
    elif "gmail_not_authenticated" in combined:
        status["state"] = "cdp_gmail_not_authenticated"
    else:
        status["state"] = "cdp_smoke_failed"
    return status


@main.command("diagnose-gmail-acquisition")
@click.option("--token", type=click.Path(path_type=Path), default=None)
@click.option("--port", type=int, default=9222)
@click.option("--skip-cdp-smoke", is_flag=True, help="Only check that the CDP port is reachable.")
@click.pass_context
def diagnose_gmail_acquisition_command(
    ctx: click.Context,
    token: Path | None,
    port: int,
    skip_cdp_smoke: bool,
) -> None:
    """Report whether Gmail raw-byte acquisition can run on this machine."""

    paths = _paths_from_context(ctx)
    token_path = token.expanduser().resolve() if token else default_token_path(paths.root)
    api_status = google_credentials_status(token_path)
    cdp_status = _diagnose_cdp(port, run_smoke=not skip_cdp_smoke)
    api_ready = bool(api_status.get("valid"))
    cdp_ready = bool(cdp_status.get("authenticated_gmail"))
    recommendations: list[str] = []
    if api_ready:
        recommendations.append(
            "run `gmail-lab acquire-gmail <targets.tsv> <run-dir>` for Gmail-native attachments"
        )
    else:
        recommendations.append(
            "run `gmail-lab setup-google --client-secrets <oauth-desktop-client.json>`"
        )
    if cdp_ready:
        recommendations.append("browser/CDP fallback is available for UI-specific rescue")
    elif cdp_status.get("state") == "cdp_gmail_not_authenticated":
        recommendations.append(
            "repair CDP auth by using a persistent CDP profile and logging into Gmail once"
        )
    else:
        recommendations.append("start a persistent CDP profile only if browser fallback is needed")

    click.echo(
        json.dumps(
            {
                "ready": api_ready or cdp_ready,
                "preferred_lane": "gmail_api"
                if api_ready
                else ("browser_cdp" if cdp_ready else "auth_google"),
                "gmail_api": api_status,
                "browser_cdp": cdp_status,
                "recommendations": recommendations,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@main.command("verify-gmail-paths")
@click.option("--token", type=click.Path(path_type=Path), default=None)
@click.option("--client-secrets", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--no-browser", is_flag=True)
@click.option("--port", type=int, default=9222)
@click.option("--skip-cdp-smoke", is_flag=True, help="Only check that the CDP port is reachable.")
@click.option("--targets-tsv", type=click.Path(path_type=Path), default=None)
@click.option("--run-dir", type=click.Path(path_type=Path), default=None)
@click.option("--max-results", type=int, default=10)
@click.option(
    "--start-persistent-cdp",
    is_flag=True,
    help="Start the persistent CDP Chrome profile before a live acquisition check.",
)
@click.option(
    "--allow-legacy-clone",
    is_flag=True,
    help="Allow the acquisition router to try the legacy cloned Chrome fallback.",
)
@click.option(
    "--allow-live",
    is_flag=True,
    help="Actually download target artifacts when --targets-tsv is supplied.",
)
@click.pass_context
def verify_gmail_paths_command(
    ctx: click.Context,
    token: Path | None,
    client_secrets: Path | None,
    no_browser: bool,
    port: int,
    skip_cdp_smoke: bool,
    targets_tsv: Path | None,
    run_dir: Path | None,
    max_results: int,
    start_persistent_cdp: bool,
    allow_legacy_clone: bool,
    allow_live: bool,
) -> None:
    """One-command auth + live-download smoke check for agent handoffs."""

    paths = _paths_from_context(ctx)
    paths.ensure()
    token_path = token.expanduser().resolve() if token else default_token_path(paths.root)
    client_secrets_path = _resolve_google_client_secrets_path(paths, client_secrets)
    api_status = google_credentials_status(token_path)
    cdp_status = _diagnose_cdp(port, run_smoke=not skip_cdp_smoke)
    api_ready = bool(api_status.get("valid"))
    cdp_ready = bool(cdp_status.get("authenticated_gmail"))
    preferred_lane = "gmail_api" if api_ready else ("browser_cdp" if cdp_ready else "auth_google")
    missing_dependencies = [
        name for name, details in _dependency_status().items() if not bool(details.get("found"))
    ]
    next_steps = _verify_gmail_next_steps(
        api_ready=api_ready,
        cdp_status=cdp_status,
        targets_tsv=targets_tsv,
        allow_live=allow_live,
        missing_dependencies=missing_dependencies,
    )
    live_acquisition: dict[str, object] = {
        "requested": targets_tsv is not None,
        "allowed": allow_live,
        "ran": False,
    }

    if targets_tsv is not None:
        resolved_targets = targets_tsv.expanduser().resolve()
        targets_exist = resolved_targets.exists()
        resolved_run_dir = (
            run_dir.expanduser().resolve()
            if run_dir is not None
            else (
                Path.cwd() / "runs" / f"verify-gmail-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            ).resolve()
        )
        live_acquisition.update(
            {
                "targets_tsv": str(resolved_targets),
                "targets_tsv_exists": targets_exist,
                "run_dir": str(resolved_run_dir),
            }
        )
        if not targets_exist:
            next_steps.append(
                "fix `--targets-tsv`: run from the repo root or pass an absolute targets file path"
            )
        elif allow_live:
            args = [
                sys.executable,
                "-m",
                "gmail_lab",
                "--root",
                str(paths.root),
                "acquire-gmail",
                str(resolved_targets),
                str(resolved_run_dir),
                "--token",
                str(token_path),
                "--max-results",
                str(max_results),
                "--port",
                str(port),
            ]
            if client_secrets_path is not None:
                args.extend(["--client-secrets", str(client_secrets_path)])
            if no_browser:
                args.append("--no-browser")
            if start_persistent_cdp:
                args.append("--start-persistent-cdp")
            if allow_legacy_clone:
                args.append("--allow-legacy-clone")
            proc = subprocess.run(args, check=False, capture_output=True, text=True)
            live_acquisition.update(
                {
                    "ran": True,
                    "exit_code": proc.returncode,
                    "stdout_tail": _tail_text(proc.stdout),
                    "stderr_tail": _tail_text(proc.stderr),
                }
            )
            if resolved_run_dir.exists():
                explanation = explain_run(resolved_run_dir)
                live_acquisition["explanation"] = explanation
                if any("unlock-pdf-run" in step for step in explanation.get("next_steps", [])):
                    next_steps.append(f"gmail-lab unlock-pdf-run {resolved_run_dir}")

    payload = {
        "root": str(paths.root),
        "cli": {
            "installed_path": shutil.which("gmail-lab") or "",
            "current_executable": sys.executable,
            "version": __version__,
        },
        "dependencies": _dependency_status(),
        "ready": api_ready or cdp_ready,
        "preferred_lane": preferred_lane,
        "gmail_api": api_status,
        "browser_cdp": cdp_status,
        "live_acquisition": live_acquisition,
        "next_steps": _dedupe_preserving_order(next_steps),
    }
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))

    if live_acquisition.get("targets_tsv_exists") is False:
        raise click.ClickException("targets tsv does not exist")
    if not (api_ready or cdp_ready):
        raise click.ClickException("no gmail acquisition lane is ready")
    live_exit_code = live_acquisition.get("exit_code")
    if isinstance(live_exit_code, int) and live_exit_code != 0:
        raise click.ClickException(f"live gmail acquisition failed with exit code {live_exit_code}")
    explanation_obj = live_acquisition.get("explanation")
    if isinstance(explanation_obj, dict):
        live_state = str(explanation_obj.get("state", "unknown"))
        if live_state in {"acquisition_blocked", "missing_run_manifest", "no_raw_assets"}:
            raise click.ClickException(
                f"live gmail acquisition did not land raw assets: {live_state}"
            )


def _verify_gmail_next_steps(
    *,
    api_ready: bool,
    cdp_status: dict[str, object],
    targets_tsv: Path | None,
    allow_live: bool,
    missing_dependencies: list[str],
) -> list[str]:
    next_steps: list[str] = []
    if missing_dependencies:
        next_steps.append(
            "install missing OCR/PDF tools, for example `brew install tesseract poppler`"
        )
    if not api_ready:
        next_steps.append(
            "run `gmail-lab setup-google --client-secrets <oauth-desktop-client.json>` for Gmail API"
        )
    cdp_state = str(cdp_status.get("state", "cdp_down"))
    if cdp_state == "cdp_gmail_not_authenticated":
        next_steps.append(
            "repair browser fallback with `gmail-lab acquire-gmail <targets.tsv> <run-dir> --start-persistent-cdp`, then log into Gmail once"
        )
    elif cdp_state == "cdp_down":
        next_steps.append(
            "start persistent browser/CDP only if API auth is unavailable or UI rescue is needed"
        )
    elif cdp_state not in {"cdp_authenticated_gmail", "cdp_up_unknown_auth"}:
        next_steps.append(
            f"inspect browser/CDP state `{cdp_state}` before relying on browser fallback"
        )
    if targets_tsv is not None and not allow_live:
        next_steps.append("rerun with `--allow-live` to verify real attachment download")
    return next_steps


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


@main.command("acquire-gmail")
@click.argument("targets_tsv", type=click.Path(exists=True, path_type=Path))
@click.argument("run_dir", type=click.Path(path_type=Path), required=False)
@click.option("--token", type=click.Path(path_type=Path), default=None)
@click.option("--client-secrets", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--no-browser", is_flag=True)
@click.option("--max-results", type=int, default=10)
@click.option("--port", type=int, default=9222)
@click.option(
    "--start-persistent-cdp",
    is_flag=True,
    help="Start the persistent CDP Chrome profile before trying browser fallback.",
)
@click.option("--persistent-cdp-url", default="https://mail.google.com/mail/u/0/#inbox")
@click.option("--cdp-wait-seconds", type=int, default=20)
@click.option(
    "--allow-legacy-clone",
    is_flag=True,
    help="Allow the browser fallback runner to start a cloned Chrome profile if CDP is down.",
)
@click.pass_context
def acquire_gmail_command(
    ctx: click.Context,
    targets_tsv: Path,
    run_dir: Path | None,
    token: Path | None,
    client_secrets: Path | None,
    no_browser: bool,
    max_results: int,
    port: int,
    start_persistent_cdp: bool,
    persistent_cdp_url: str,
    cdp_wait_seconds: int,
    allow_legacy_clone: bool,
) -> None:
    """Acquire Gmail raw bytes through the best available explicit auth lane."""

    paths = _paths_from_context(ctx)
    paths.ensure()
    resolved_targets = targets_tsv.expanduser().resolve()
    resolved_run_dir = (
        run_dir.expanduser().resolve()
        if run_dir is not None
        else (
            Path.cwd() / "runs" / f"gmail-acquire-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        ).resolve()
    )
    resolved_run_dir.mkdir(parents=True, exist_ok=True)
    token_path = token.expanduser().resolve() if token else default_token_path(paths.root)
    client_secrets_path = _resolve_google_client_secrets_path(paths, client_secrets)
    api_status = google_credentials_status(token_path)
    api_available = bool(
        api_status.get("valid")
        or (api_status.get("exists") and api_status.get("has_refresh_token"))
        or client_secrets_path
    )
    persistent_cdp_start: dict[str, object] = {"requested": False}
    if start_persistent_cdp and not api_available:
        persistent_cdp_start = _start_persistent_cdp_profile(
            port=port,
            run_dir=resolved_run_dir,
            url=persistent_cdp_url,
            wait_seconds=cdp_wait_seconds,
        )
    cdp_status = _diagnose_cdp(port, run_smoke=True)
    cdp_available = bool(cdp_status.get("authenticated_gmail"))
    diagnostic = {
        "targets_tsv": str(resolved_targets),
        "run_dir": str(resolved_run_dir),
        "gmail_api": api_status,
        "browser_cdp": cdp_status,
        "persistent_cdp_start": persistent_cdp_start,
        "allow_legacy_clone": allow_legacy_clone,
        "selected_lane": "",
    }

    if api_available:
        diagnostic["selected_lane"] = "gmail_api"
        (resolved_run_dir / "logs").mkdir(parents=True, exist_ok=True)
        (resolved_run_dir / "logs/acquisition_diagnostic.json").write_text(
            json.dumps(diagnostic, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        script = _repo_root() / "scripts/run_gmail_api_export.py"
        args = [
            sys.executable,
            str(script),
            str(resolved_targets),
            str(resolved_run_dir),
            "--token",
            str(token_path),
            "--max-results",
            str(max_results),
        ]
        if client_secrets_path is not None:
            args.extend(["--client-secrets", str(client_secrets_path)])
        if no_browser:
            args.append("--no-browser")
        proc = subprocess.run(args, check=False, text=True)
        if proc.returncode != 0:
            raise click.ClickException(
                f"gmail api acquisition failed with exit code {proc.returncode}"
            )
        _emit_acquisition_result("gmail_api", resolved_run_dir)
        return

    if cdp_available or allow_legacy_clone:
        diagnostic["selected_lane"] = "browser_cdp" if cdp_available else "legacy_chrome_clone"
        (resolved_run_dir / "logs").mkdir(parents=True, exist_ok=True)
        (resolved_run_dir / "logs/acquisition_diagnostic.json").write_text(
            json.dumps(diagnostic, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        script = _repo_root() / "scripts/run_gmail_lab_export.sh"
        env = os.environ.copy()
        env["PORT"] = str(port)
        env["STRICT_GMAIL_SMOKE"] = "1"
        env["START_CHROME"] = "1" if allow_legacy_clone and not cdp_available else "0"
        proc = subprocess.run(
            [str(script), str(resolved_targets), str(resolved_run_dir)],
            check=False,
            text=True,
            env=env,
        )
        if proc.returncode != 0:
            raise click.ClickException(
                f"browser cdp acquisition failed with exit code {proc.returncode}"
            )
        _emit_acquisition_result(str(diagnostic["selected_lane"]), resolved_run_dir)
        return

    cdp_state = str(cdp_status.get("state", "cdp_down"))
    if cdp_state == "cdp_gmail_not_authenticated":
        blocker = "cdp_not_authenticated"
    elif cdp_state == "cdp_down":
        blocker = "api_auth_missing"
    else:
        blocker = cdp_state
    diagnostic["selected_lane"] = "blocked"
    diagnostic["blocker"] = blocker
    _write_blocked_acquisition_run(
        targets_tsv=resolved_targets,
        run_dir=resolved_run_dir,
        status=blocker,
        diagnostic=diagnostic,
    )
    raise click.ClickException(
        f"gmail acquisition blocked: {blocker}; inspect {resolved_run_dir / 'run_manifest.tsv'}"
    )


@main.command("export-gmail-api")
@click.argument("targets_tsv", type=click.Path(exists=True, path_type=Path))
@click.argument("run_dir", type=click.Path(path_type=Path), required=False)
@click.option("--token", type=click.Path(path_type=Path), default=None)
@click.option("--client-secrets", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--no-browser", is_flag=True)
@click.option("--max-results", type=int, default=10)
def export_gmail_api_command(
    targets_tsv: Path,
    run_dir: Path | None,
    token: Path | None,
    client_secrets: Path | None,
    no_browser: bool,
    max_results: int,
) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_gmail_api_export.py"
    args = [sys.executable, str(script), str(targets_tsv)]
    if run_dir is not None:
        args.append(str(run_dir))
    if token is not None:
        args.extend(["--token", str(token)])
    if client_secrets is not None:
        args.extend(["--client-secrets", str(client_secrets)])
    if no_browser:
        args.append("--no-browser")
    args.extend(["--max-results", str(max_results)])
    proc = subprocess.run(args, check=False, text=True)
    if proc.returncode != 0:
        raise click.ClickException(f"gmail api export failed with exit code {proc.returncode}")


@main.command("record-mailbox")
@click.option("--mailbox", required=True)
@click.option("--gmail-address", required=True)
@click.option("--scopes-json", default='["gmail.readonly"]')
@click.option("--last-sync-at", default="")
@click.option("--last-history-id", default="")
@click.pass_context
def record_mailbox_command(
    ctx: click.Context,
    mailbox: str,
    gmail_address: str,
    scopes_json: str,
    last_sync_at: str,
    last_history_id: str,
) -> None:
    paths = _paths_from_context(ctx)
    paths.ensure()
    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()
    connection = MailboxConnection(
        mailbox=mailbox,
        gmail_address=gmail_address,
        scopes_json=scopes_json,
        connected_at=_utc_now(),
        last_sync_at=last_sync_at,
        last_history_id=last_history_id,
    )
    state_store.upsert_mailbox_connection(connection)
    click.echo(json.dumps(asdict(connection), ensure_ascii=False, indent=2))


@main.command("record-message")
@click.option("--mailbox", required=True)
@click.option("--message-id", required=True)
@click.option("--thread-id", required=True)
@click.option("--internal-date", required=True)
@click.option("--subject", default="")
@click.option("--sender", default="")
@click.option("--snippet", default="")
@click.option("--labels-json", default="[]")
@click.option("--raw-file", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--full-json-file", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--headers-json-file", type=click.Path(exists=True, path_type=Path), default=None)
@click.option(
    "--mime-summary-json-file", type=click.Path(exists=True, path_type=Path), default=None
)
@click.option("--discovery-status", default="ok")
@click.option("--discovery-class", default="unknown")
@click.option("--attachment-candidate-count", type=int, default=0)
@click.option("--download-url-count", type=int, default=0)
@click.option("--inline-candidate-count", type=int, default=0)
@click.option("--scanning-for-viruses/--no-scanning-for-viruses", default=False)
@click.option("--query", default="")
@click.option("--needle", default="")
@click.option("--json-log", default="-")
@click.option("--stderr-log", default="-")
@click.pass_context
def record_message_command(
    ctx: click.Context,
    mailbox: str,
    message_id: str,
    thread_id: str,
    internal_date: str,
    subject: str,
    sender: str,
    snippet: str,
    labels_json: str,
    raw_file: Path | None,
    full_json_file: Path | None,
    headers_json_file: Path | None,
    mime_summary_json_file: Path | None,
    discovery_status: str,
    discovery_class: str,
    attachment_candidate_count: int,
    download_url_count: int,
    inline_candidate_count: int,
    scanning_for_viruses: bool,
    query: str,
    needle: str,
    json_log: str,
    stderr_log: str,
) -> None:
    paths = _paths_from_context(ctx)
    paths.ensure()
    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()
    message_store = FsMessageStore(paths)
    stored_paths = message_store.store_message_files(
        mailbox=mailbox,
        message_id=message_id,
        raw_file=raw_file,
        full_json_file=full_json_file,
        headers_json_file=headers_json_file,
        mime_summary_json_file=mime_summary_json_file,
    )
    record = MessageRecord(
        mailbox=mailbox,
        message_id=message_id,
        thread_id=thread_id,
        internal_date=internal_date,
        subject=subject,
        sender=sender,
        snippet=snippet,
        labels_json=labels_json,
        raw_path=stored_paths["raw_path"],
        full_path=stored_paths["full_path"],
        headers_path=stored_paths["headers_path"],
        mime_summary_path=stored_paths["mime_summary_path"],
        discovery_status=discovery_status,
        discovery_class=discovery_class,
        attachment_candidate_count=attachment_candidate_count,
        download_url_count=download_url_count,
        inline_candidate_count=inline_candidate_count,
        scanning_for_viruses=scanning_for_viruses,
        query=query,
        needle=needle,
        json_log=json_log,
        stderr_log=stderr_log,
        created_at=_utc_now(),
    )
    state_store.upsert_message(record)
    click.echo(json.dumps(asdict(record), ensure_ascii=False, indent=2))


@main.command("record-evidence")
@click.option("--mailbox", required=True)
@click.option("--message-id", required=True)
@click.option("--source-file", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--source-kind", required=True)
@click.option("--original-filename", default=None)
@click.option("--mime-type", default=None)
@click.pass_context
def record_evidence_command(
    ctx: click.Context,
    mailbox: str,
    message_id: str,
    source_file: Path,
    source_kind: str,
    original_filename: str | None,
    mime_type: str | None,
) -> None:
    paths = _paths_from_context(ctx)
    paths.ensure()
    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()
    evidence_store = FsEvidenceStore(paths)
    record = evidence_store.store_evidence(
        mailbox=mailbox,
        message_id=message_id,
        source_file=source_file,
        source_kind=source_kind,
        original_filename=original_filename,
        mime_type=mime_type,
    )
    state_store.add_evidence(record)
    click.echo(json.dumps(asdict(record), ensure_ascii=False, indent=2))


@main.command("emit-discovery-manifest")
@click.option("--mailbox", default=None)
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.pass_context
def emit_discovery_manifest_command(ctx: click.Context, mailbox: str | None, output: Path) -> None:
    paths = _paths_from_context(ctx)
    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()
    messages = state_store.list_messages(mailbox=mailbox)
    written = write_discovery_manifest(output, messages)
    click.echo(str(written))


@main.command("emit-evidence-manifest")
@click.option("--mailbox", default=None)
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.pass_context
def emit_evidence_manifest_command(ctx: click.Context, mailbox: str | None, output: Path) -> None:
    paths = _paths_from_context(ctx)
    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()
    evidence_rows = state_store.list_evidence(mailbox=mailbox)
    written = write_evidence_manifest(output, evidence_rows)
    click.echo(str(written))


@main.command("derive-claims")
@click.option("--mailbox", default=None)
@click.pass_context
def derive_claims_command(ctx: click.Context, mailbox: str | None) -> None:
    paths = _paths_from_context(ctx)
    paths.ensure()
    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()
    config = load_config(paths.root)
    messages = {
        (message.mailbox, message.message_id): message
        for message in state_store.list_messages(mailbox=mailbox)
    }
    evidence_rows = state_store.list_evidence(mailbox=mailbox)
    derived = []
    for evidence in evidence_rows:
        claim = build_claim_record(
            config=config,
            message=messages.get((evidence.mailbox, evidence.message_id)),
            evidence=evidence,
        )
        state_store.upsert_claim(claim)
        derived.append(claim.analysis_id)
    click.echo(
        json.dumps(
            {
                "derived_claims": len(derived),
                "analysis_ids": derived,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@main.command("emit-claims-manifest")
@click.option("--mailbox", default=None)
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.pass_context
def emit_claims_manifest_command(ctx: click.Context, mailbox: str | None, output: Path) -> None:
    paths = _paths_from_context(ctx)
    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()
    claims = state_store.list_claims(mailbox=mailbox)
    written = write_claims_manifest(output, claims)
    click.echo(str(written))


@main.command("emit-analysis-manifest")
@click.option("--mailbox", default=None)
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.pass_context
def emit_analysis_manifest_command(ctx: click.Context, mailbox: str | None, output: Path) -> None:
    paths = _paths_from_context(ctx)
    state_store = SqliteStateStore(paths.state_db)
    state_store.initialize()
    claims = state_store.list_claims(mailbox=mailbox)
    written = write_analysis_manifest(output, [claim_to_analysis_row(claim) for claim in claims])
    click.echo(str(written))


if __name__ == "__main__":
    main()
