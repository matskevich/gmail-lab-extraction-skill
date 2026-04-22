#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from collections import OrderedDict
from pathlib import Path

DEFAULT_INVENTORY_ENV = "HEALTH_LAB_INVENTORY"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_tsv_no_header(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writerows(rows)


def base_case_id(case_id: str) -> str:
    value = case_id.strip()
    for suffix in ("_clinchem", "_cbc"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    if value.count("_") == 1 and all(part.isdigit() for part in value.split("_")):
        return value.split("_", 1)[0]
    return value


def gmail_query(provider: str, case_id: str, lane: str) -> str:
    base = base_case_id(case_id)
    if provider == "prodia" or lane == "passworded_pdf_recovered":
        return "from:tabanan@prodia.co.id Half Medical Result"
    if provider == "cmd":
        return f"from:info@cmd-online.ru {base}"
    if provider == "dnkom":
        return f"from:results@dnkom.ru {base}"
    if provider == "gemotest":
        return f"from:info@gemotest.ru {base}"
    if provider == "kdl":
        return f"from:result@kdltest.ru {base}"
    if provider == "invitro":
        return f"from:srs@invitro.ru {base}"
    return base


def gmail_needle(provider: str, lane: str, case_id: str) -> str:
    if provider == "prodia" or lane == "passworded_pdf_recovered":
        return "Half Medical Result"
    return base_case_id(case_id)


def group_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (row["recovery_lane"], row["provider"], base_case_id(row["case_id"]))


def build_rows(inventory_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    oracle_rows: list[dict[str, str]] = []
    gmail_groups: OrderedDict[tuple[str, str, str], list[dict[str, str]]] = OrderedDict()
    portal_groups: OrderedDict[tuple[str, str, str], list[dict[str, str]]] = OrderedDict()

    for row in inventory_rows:
        status = row["status"]
        lane = row["recovery_lane"]
        provider = row["provider"]
        case_id = row["case_id"]
        base = base_case_id(case_id)
        expected_path = row.get("semantic_path", "")
        oracle_rows.append(
            {
                "date": row["date"],
                "provider": provider,
                "case_id": case_id,
                "base_case_id": base,
                "inventory_status": status,
                "category": row["category"],
                "recovery_lane": lane,
                "expected_semantic_path": expected_path,
                "note": row.get("note", ""),
            }
        )
        if status != "active":
            continue
        if lane in {"gmail_attachment_recovered", "passworded_pdf_recovered"}:
            gmail_groups.setdefault(group_key(row), []).append(row)
        elif lane == "invitro_portal_recovered":
            portal_groups.setdefault(group_key(row), []).append(row)

    gmail_targets: list[dict[str, str]] = []
    regression_targets: list[dict[str, str]] = []
    for (_lane, provider, base), rows in gmail_groups.items():
        query = gmail_query(provider, base, rows[0]["recovery_lane"])
        needle = gmail_needle(provider, rows[0]["recovery_lane"], base)
        min_attachments = str(len(rows))
        note = f"{provider} {base}; expected active artifacts: {len(rows)}"
        gmail_targets.append({"query": query, "needle": needle, "mode": "auto"})
        regression_targets.append(
            {
                "query": query,
                "needle": needle,
                "mode": "auto",
                "min_attachments": min_attachments,
                "min_inline": "0",
                "note": note,
            }
        )

    portal_targets: list[dict[str, str]] = []
    for (_lane, provider, base), _rows in portal_groups.items():
        query = f"from:srs@invitro.ru {base}"
        portal_targets.append(
            {
                "provider": provider,
                "locator": query,
                "row_needle": base,
                "patient_hint": "",
            }
        )

    return oracle_rows, gmail_targets, regression_targets, portal_targets


def write_plan(path: Path, oracle_rows: list[dict[str, str]], gmail_targets: list[dict[str, str]], portal_targets: list[dict[str, str]]) -> None:
    active = [row for row in oracle_rows if row["inventory_status"] == "active"]
    excluded = [row for row in oracle_rows if row["inventory_status"] != "active"]
    lanes: OrderedDict[str, int] = OrderedDict()
    for row in active:
        lanes[row["recovery_lane"]] = lanes.get(row["recovery_lane"], 0) + 1
    lines = [
        "# health full validation plan",
        "",
        "purpose:",
        "- validate this repo against the user's existing personal health lab oracle",
        "- prove raw acquisition, enrichment, metadata, and promotion boundaries for downstream agents",
        "",
        "oracle:",
        f"- active artifacts: {len(active)}",
        f"- excluded/context artifacts: {len(excluded)}",
        f"- gmail/passworded target groups: {len(gmail_targets)}",
        f"- portal target groups: {len(portal_targets)}",
        "",
        "active lanes:",
    ]
    lines.extend(f"- `{lane}`: {count}" for lane, count in lanes.items())
    lines.extend(
        [
            "",
            "run order:",
            "1. `./scripts/run_gmail_discovery.sh <gmail_targets.tsv> <run>/discovery`",
            "2. `./scripts/run_regression_suite.sh <regression_targets.tsv> <run>/regression`",
            "3. `./scripts/run_gmail_lab_export.sh <gmail_targets.tsv> <run>/export`",
            "4. `PORTAL_PATIENT_HINT=<last-name> ./scripts/run_portal_lab_export.sh <portal_targets.tsv> <run>/portal`",
            "5. `./scripts/audit_health_validation.py --oracle <oracle.tsv> --export-run <run>/export --portal-run <run>/portal --out <run>/coverage_report.md`",
            "",
            "pass rule:",
            "- every active gmail/password group lands at least the expected number of promoted result assets",
            "- every portal group either lands a promoted result asset or is explicitly reported as portal-token debt",
            "- support files and formal sidecars stay raw-only with explicit `non_result` or `sidecar` status",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build private health validation targets from personal health lab inventory.")
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path(os.environ[DEFAULT_INVENTORY_ENV]) if os.environ.get(DEFAULT_INVENTORY_ENV) else None,
        help=f"Path to private health lab inventory TSV. Can also be set with {DEFAULT_INVENTORY_ENV}.",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.inventory is None:
        raise SystemExit(f"missing --inventory or {DEFAULT_INVENTORY_ENV}")

    inventory = args.inventory.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    rows = read_tsv(inventory)
    oracle_rows, gmail_targets, regression_targets, portal_targets = build_rows(rows)

    write_tsv(
        out_dir / "oracle.tsv",
        ["date", "provider", "case_id", "base_case_id", "inventory_status", "category", "recovery_lane", "expected_semantic_path", "note"],
        oracle_rows,
    )
    write_tsv_no_header(out_dir / "gmail_targets.tsv", ["query", "needle", "mode"], gmail_targets)
    write_tsv_no_header(
        out_dir / "regression_targets.tsv",
        ["query", "needle", "mode", "min_attachments", "min_inline", "note"],
        regression_targets,
    )
    write_tsv_no_header(out_dir / "portal_targets.tsv", ["provider", "locator", "row_needle", "patient_hint"], portal_targets)
    write_plan(out_dir / "validation_plan.md", oracle_rows, gmail_targets, portal_targets)

    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
