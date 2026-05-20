from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def explain_run(run_dir: Path) -> dict[str, Any]:
    resolved_run_dir = run_dir.expanduser().resolve()
    run_manifest_path = resolved_run_dir / "run_manifest.tsv"
    asset_manifest_path = resolved_run_dir / "asset_manifest.tsv"
    pdf_text_manifest_paths = _manifest_candidates(
        resolved_run_dir / "pdf_text_manifest.tsv",
        resolved_run_dir / "pdf_text" / "pdf_text_manifest.tsv",
        sorted((resolved_run_dir / "pdf_text").glob("*/pdf_text_manifest.tsv")),
    )
    ocr_manifest_paths = _manifest_candidates(
        resolved_run_dir / "ocr" / "ocr_manifest.tsv",
        *sorted((resolved_run_dir / "ocr").glob("*/ocr_manifest.tsv")),
    )
    diagnostic_path = resolved_run_dir / "logs" / "acquisition_diagnostic.json"

    run_rows = _read_tsv(run_manifest_path)
    asset_rows = _read_tsv(asset_manifest_path)
    pdf_text_rows = _read_tsvs(pdf_text_manifest_paths)
    ocr_rows = _read_tsvs(ocr_manifest_paths)
    diagnostic = _read_json(diagnostic_path)

    blockers: list[dict[str, str]] = []
    next_steps: list[str] = []
    raw_count = sum(_safe_int(row.get("extracted_count", "")) for row in run_rows)
    promoted_count = sum(
        1
        for row in asset_rows
        if row.get("status") == "ok" and row.get("final_file", "-") not in {"", "-"}
    )
    review_count = sum(1 for row in asset_rows if row.get("status") == "needs_review")

    if not run_manifest_path.exists():
        blockers.append(
            _blocker(
                layer="run",
                status="missing_run_manifest",
                message="run_manifest.tsv is absent; acquisition state is unknown",
                next_step="rerun acquisition with `gmail-lab acquire-gmail <targets.tsv> <run-dir>`",
            )
        )
    else:
        _add_run_blockers(run_rows, blockers)
        _add_enrichment_blockers(run_rows, pdf_text_rows, ocr_rows, blockers)
        _add_asset_blockers(asset_rows, blockers)

    for blocker in blockers:
        next_step = blocker.get("next_step", "")
        if next_step and next_step not in next_steps:
            next_steps.append(next_step)

    state = _derive_state(
        run_manifest_exists=run_manifest_path.exists(),
        run_rows=run_rows,
        blockers=blockers,
        raw_count=raw_count,
        asset_rows=asset_rows,
        promoted_count=promoted_count,
        review_count=review_count,
    )

    if not next_steps and state in {"ready", "partial_ready"}:
        next_steps.append(
            "ingest/read `final/` only after checking `asset_manifest.tsv` provenance columns"
        )
    elif not next_steps and state == "raw_acquired_needs_metadata":
        next_steps.append("run metadata derivation/enrichment before trusting `final/`")
    elif not next_steps:
        next_steps.append(
            "inspect manifests and logs; this state is not yet mapped to a specific recovery command"
        )

    return {
        "run_dir": str(resolved_run_dir),
        "state": state,
        "summary": _summary_for_state(state),
        "counts": {
            "targets": len(run_rows),
            "raw_acquired": raw_count,
            "asset_rows": len(asset_rows),
            "promoted": promoted_count,
            "needs_review": review_count,
            "pdf_text_rows": len(pdf_text_rows),
            "ocr_rows": len(ocr_rows),
        },
        "manifests": {
            "run_manifest": _manifest_info(run_manifest_path),
            "asset_manifest": _manifest_info(asset_manifest_path),
            "pdf_text_manifest": _manifest_info(
                _first_existing_or_default(pdf_text_manifest_paths)
            ),
            "pdf_text_manifests": [
                _manifest_info(path) for path in pdf_text_manifest_paths if path.exists()
            ],
            "ocr_manifest": _manifest_info(_first_existing_or_default(ocr_manifest_paths)),
            "ocr_manifests": [_manifest_info(path) for path in ocr_manifest_paths if path.exists()],
            "acquisition_diagnostic": _manifest_info(diagnostic_path),
        },
        "diagnostic": _summarize_diagnostic(diagnostic),
        "rows": [_summarize_run_row(row) for row in run_rows],
        "blockers": blockers,
        "next_steps": next_steps,
    }


def _manifest_candidates(*paths: Path | list[Path]) -> list[Path]:
    candidates: list[Path] = []
    for value in paths:
        if isinstance(value, list):
            candidates.extend(value)
        else:
            candidates.append(value)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _first_existing_or_default(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def _read_tsvs(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        rows.extend(_read_tsv(path))
    return rows


def _read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"parse_error": "invalid_json"}
    return data if isinstance(data, dict) else {}


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _blocker(
    *, layer: str, status: str, message: str, next_step: str, row: str = ""
) -> dict[str, str]:
    payload = {
        "layer": layer,
        "status": status,
        "message": message,
        "next_step": next_step,
    }
    if row:
        payload["row"] = row
    return payload


def _add_run_blockers(rows: list[dict[str, str]], blockers: list[dict[str, str]]) -> None:
    if not rows:
        blockers.append(
            _blocker(
                layer="acquisition",
                status="empty_run_manifest",
                message="run_manifest.tsv has no target rows",
                next_step="check targets.tsv and rerun `gmail-lab acquire-gmail <targets.tsv> <run-dir>`",
            )
        )
        return

    for row in rows:
        status = row.get("status", "")
        if status == "ok":
            continue
        blockers.append(
            _blocker(
                layer="acquisition",
                status=status or "unknown_status",
                message=_acquisition_message(status),
                next_step=_acquisition_next_step(status),
                row=row.get("line_no", "") or row.get("slug", ""),
            )
        )


def _add_enrichment_blockers(
    run_rows: list[dict[str, str]],
    pdf_text_rows: list[dict[str, str]],
    ocr_rows: list[dict[str, str]],
    blockers: list[dict[str, str]],
) -> None:
    for row in run_rows:
        for column in ("ocr_status", "pdf_text_status", "enrichment_status"):
            status = row.get(column, "")
            if status in {"", "ok", "ok_text", "ok_ocr", "not_applicable"}:
                continue
            if status == "blocked_by_acquisition":
                continue
            blockers.append(
                _blocker(
                    layer="enrichment",
                    status=status,
                    message=f"{column} reports {status}",
                    next_step=_enrichment_next_step(status),
                    row=row.get("line_no", "") or row.get("slug", ""),
                )
            )

    for source, rows in (("pdf_text", pdf_text_rows), ("ocr", ocr_rows)):
        for row in rows:
            status = row.get("status", "")
            if status in {"", "ok", "ok_text", "ok_ocr", "not_applicable"}:
                continue
            blockers.append(
                _blocker(
                    layer=source,
                    status=status,
                    message=f"{source} row reports {status}",
                    next_step=_enrichment_next_step(status),
                    row=row.get("raw_file", "")
                    or row.get("source_file", "")
                    or row.get("line_no", ""),
                )
            )


def _add_asset_blockers(rows: list[dict[str, str]], blockers: list[dict[str, str]]) -> None:
    for row in rows:
        status = row.get("status", "")
        if status in {"", "ok"}:
            continue
        if status == "needs_review":
            next_step = (
                "inspect `asset_manifest.tsv`; improve date/owner evidence before trusting `final/`"
            )
        else:
            next_step = "inspect `asset_manifest.tsv` and provider/date/owner columns"
        blockers.append(
            _blocker(
                layer="metadata",
                status=status,
                message=f"asset row is {status}",
                next_step=next_step,
                row=row.get("raw_file", "") or row.get("final_file", ""),
            )
        )


def _derive_state(
    *,
    run_manifest_exists: bool,
    run_rows: list[dict[str, str]],
    blockers: list[dict[str, str]],
    raw_count: int,
    asset_rows: list[dict[str, str]],
    promoted_count: int,
    review_count: int,
) -> str:
    if not run_manifest_exists:
        return "missing_run_manifest"
    acquisition_blocked = any(blocker["layer"] == "acquisition" for blocker in blockers)
    if acquisition_blocked:
        return "acquisition_blocked"
    if run_rows and raw_count == 0:
        return "no_raw_assets"
    enrichment_blocked = any(
        blocker["layer"] in {"enrichment", "pdf_text", "ocr"} for blocker in blockers
    )
    if enrichment_blocked:
        return "enrichment_blocked"
    if not asset_rows and raw_count > 0:
        return "raw_acquired_needs_metadata"
    metadata_blocked = any(blocker["layer"] == "metadata" for blocker in blockers)
    if promoted_count > 0 and (metadata_blocked or review_count > 0):
        return "partial_ready"
    if promoted_count > 0:
        return "ready"
    if metadata_blocked or review_count > 0:
        return "metadata_blocked"
    return "unknown"


def _summary_for_state(state: str) -> str:
    return {
        "missing_run_manifest": "run surface is absent; no completeness claim is possible",
        "acquisition_blocked": "raw bytes did not land; do not interpret stale local files",
        "no_raw_assets": "acquisition ran but no raw assets were saved",
        "enrichment_blocked": "raw bytes exist, but OCR/PDF text/enrichment is blocked",
        "raw_acquired_needs_metadata": "raw bytes exist, but metadata/final promotion has not been derived",
        "metadata_blocked": "raw bytes exist, but metadata is too weak for final promotion",
        "partial_ready": "some artifacts are promoted, while other rows still need review",
        "ready": "promoted artifacts exist; verify provenance before downstream use",
    }.get(state, "run state is not mapped")


def _acquisition_message(status: str) -> str:
    return {
        "api_auth_missing": "Gmail API token/client secret is missing or invalid",
        "cdp_not_authenticated": "browser/CDP is reachable but not authenticated to Gmail",
        "cdp_down": "browser/CDP port is not reachable",
        "extract_fail": "collector failed before raw bytes landed",
    }.get(status, f"acquisition status is {status or 'unknown'}")


def _acquisition_next_step(status: str) -> str:
    return {
        "api_auth_missing": "run `gmail-lab setup-google --client-secrets <oauth-desktop-client.json>`",
        "cdp_not_authenticated": "run `gmail-lab acquire-gmail <targets.tsv> <run-dir> --start-persistent-cdp` and log into Gmail once",
        "cdp_down": "prefer Gmail API; otherwise start persistent CDP with `--start-persistent-cdp`",
        "extract_fail": "inspect row json/stderr logs, then rerun bounded target",
    }.get(status, "inspect `logs/acquisition_diagnostic.json` and rerun bounded acquisition")


def _enrichment_next_step(status: str) -> str:
    if status == "needs_password_hint":
        return "run `gmail-lab unlock-pdf-run <run-dir>` or store a local PDF secret with `gmail-lab remember-pdf-secret`"
    if status == "missing_dependency":
        return "run `./scripts/doctor.sh`, install missing OCR/PDF tools, then rerun enrichment"
    if status in {"fail", "partial"}:
        return "inspect OCR/PDF logs, then rerun `./scripts/rerun_enrichment.py <run-dir>`"
    return "inspect enrichment manifests and rerun `./scripts/rerun_enrichment.py <run-dir>`"


def _manifest_info(path: Path) -> dict[str, str | bool | int]:
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def _summarize_diagnostic(diagnostic: dict[str, Any]) -> dict[str, Any]:
    if not diagnostic:
        return {}
    gmail_api = diagnostic.get("gmail_api", {})
    browser_cdp = diagnostic.get("browser_cdp", {})
    return {
        "selected_lane": diagnostic.get("selected_lane", ""),
        "blocker": diagnostic.get("blocker", ""),
        "gmail_api": _pick_dict(
            gmail_api, ["exists", "valid", "expired", "has_refresh_token", "token_path"]
        ),
        "browser_cdp": _pick_dict(
            browser_cdp,
            ["up", "authenticated_gmail", "state", "browser", "smoke_exit_code"],
        ),
    }


def _pick_dict(value: object, keys: list[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in keys if key in value}


def _summarize_run_row(row: dict[str, str]) -> dict[str, str]:
    keys = [
        "line_no",
        "slug",
        "mode",
        "status",
        "extracted_count",
        "ocr_status",
        "pdf_text_status",
        "enrichment_status",
        "query",
        "needle",
    ]
    return {key: row.get(key, "") for key in keys if key in row}
