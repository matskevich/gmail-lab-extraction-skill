from __future__ import annotations

import json
import os
import subprocess
import sys
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
    default_token_path,
    google_credentials_status,
    load_google_credentials,
)
from gmail_lab.core.layout import AppPaths
from gmail_lab.core.manifests.analyses import write_analysis_manifest
from gmail_lab.core.manifests.claims import write_claims_manifest
from gmail_lab.core.manifests.discovery import write_discovery_manifest
from gmail_lab.core.manifests.evidence import write_evidence_manifest
from gmail_lab.core.models import MailboxConnection, MessageRecord
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


@main.command("auth-google")
@click.option("--client-secrets", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--token", type=click.Path(path_type=Path), default=None)
@click.option("--no-browser", is_flag=True, help="Print OAuth URL and ask for an authorization code.")
@click.pass_context
def auth_google_command(
    ctx: click.Context,
    client_secrets: Path | None,
    token: Path | None,
    no_browser: bool,
) -> None:
    paths = _paths_from_context(ctx)
    paths.ensure()
    client_secrets_path = client_secrets
    if client_secrets_path is None:
        env_value = os.environ.get("GMAIL_LAB_GOOGLE_CLIENT_SECRET", "").strip()
        client_secrets_path = Path(env_value).expanduser().resolve() if env_value else None
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

    repo_root = Path(__file__).resolve().parents[2]
    smoke_script = repo_root / "skills/gmail-browser-attachments/scripts/gmail_smoke_check.sh"
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
    status["smoke_excerpt"] = _tail_text(combined)
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
        recommendations.append("run `gmail-lab export-gmail-api` for Gmail-native attachments")
    else:
        recommendations.append("run `gmail-lab auth-google --client-secrets <oauth-desktop-client.json>`")
    if cdp_ready:
        recommendations.append("browser/CDP fallback is available for UI-specific rescue")
    elif cdp_status.get("state") == "cdp_gmail_not_authenticated":
        recommendations.append("repair CDP auth by using a persistent CDP profile and logging into Gmail once")
    else:
        recommendations.append("start a persistent CDP profile only if browser fallback is needed")

    click.echo(
        json.dumps(
            {
                "ready": api_ready or cdp_ready,
                "preferred_lane": "gmail_api" if api_ready else "auth_google",
                "gmail_api": api_status,
                "browser_cdp": cdp_status,
                "recommendations": recommendations,
            },
            ensure_ascii=False,
            indent=2,
        )
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
@click.option("--mime-summary-json-file", type=click.Path(exists=True, path_type=Path), default=None)
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
