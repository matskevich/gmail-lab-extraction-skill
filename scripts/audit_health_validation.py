#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, OrderedDict
from pathlib import Path


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def base_case_id(case_id: str) -> str:
    value = case_id.strip()
    for suffix in ("_clinchem", "_cbc"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    if value.count("_") == 1 and all(part.isdigit() for part in value.split("_")):
        return value.split("_", 1)[0]
    return value


def text_for_asset(row: dict[str, str]) -> str:
    return "\n".join(
        [
            row.get("raw_file", ""),
            row.get("final_file", ""),
            row.get("provider", ""),
            row.get("owner_name", ""),
        ]
    ).lower()


def matching_assets(asset_rows: list[dict[str, str]], base: str, provider: str, statuses: set[str] | None = None) -> list[dict[str, str]]:
    token = base.lower()
    out = []
    for row in asset_rows:
        if statuses is not None and row.get("status") not in statuses:
            continue
        if token not in text_for_asset(row):
            continue
        if provider and provider != "invitro" and row.get("provider") not in {provider, "hemotest"}:
            continue
        out.append(row)
    return out


def group_oracle(oracle_rows: list[dict[str, str]]) -> OrderedDict[tuple[str, str, str], list[dict[str, str]]]:
    groups: OrderedDict[tuple[str, str, str], list[dict[str, str]]] = OrderedDict()
    for row in oracle_rows:
        if row["inventory_status"] != "active":
            continue
        key = (row["recovery_lane"], row["provider"], base_case_id(row["case_id"]))
        groups.setdefault(key, []).append(row)
    return groups


def portal_status_for(base: str, portal_manifest: list[dict[str, str]]) -> str:
    for row in portal_manifest:
        haystack = "\n".join([row.get("locator", ""), row.get("row_needle", ""), row.get("portal_url", "")]).lower()
        if base.lower() in haystack:
            return row.get("status", "unknown")
    return "missing_run_row"


def summarize_metadata(asset_rows: list[dict[str, str]]) -> list[str]:
    promoted = [row for row in asset_rows if row.get("status") == "ok"]
    status_counts = Counter(row.get("status", "") for row in asset_rows)
    confidence_counts = Counter(row.get("confidence", "") for row in promoted)
    owner_counts = Counter(row.get("owner_status", "") for row in promoted)
    date_counts = Counter(row.get("analysis_date_status", "") for row in promoted)
    lines = [
        "metadata quality:",
        f"- asset rows: {len(asset_rows)}",
        f"- promoted result rows: {len(promoted)}",
        f"- asset statuses: {dict(status_counts)}",
        f"- confidence: {dict(confidence_counts)}",
        f"- owner status: {dict(owner_counts)}",
        f"- analysis date status: {dict(date_counts)}",
    ]
    low_rows = [row for row in promoted if row.get("confidence") == "low" or row.get("owner_status") == "unknown_owner"]
    if low_rows:
        lines.append("- weak rows:")
        for row in low_rows[:20]:
            lines.append(
                f"  - `{Path(row.get('raw_file', '')).name}` owner={row.get('owner_status')} date={row.get('analysis_date_status')} confidence={row.get('confidence')}"
            )
    return lines


def audit(oracle_rows: list[dict[str, str]], export_assets: list[dict[str, str]], portal_assets: list[dict[str, str]], portal_manifest: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    groups = group_oracle(oracle_rows)
    result_rows: list[dict[str, str]] = []
    blockers: list[str] = []
    for (lane, provider, base), expected in groups.items():
        if lane in {"gmail_attachment_recovered", "passworded_pdf_recovered"}:
            assets = matching_assets(export_assets, base, provider, {"ok"})
            status = "pass" if len(assets) >= len(expected) else "fail"
            detail = f"promoted_result_assets={len(assets)} expected={len(expected)}"
        elif lane == "invitro_portal_recovered":
            assets = matching_assets(portal_assets, base, provider, {"ok"})
            portal_status = portal_status_for(base, portal_manifest)
            status = "pass" if len(assets) >= len(expected) else "portal_debt"
            detail = f"promoted_result_assets={len(assets)} expected={len(expected)} portal_status={portal_status}"
        else:
            continue
        if status != "pass":
            blockers.append(f"{lane}/{provider}/{base}: {detail}")
        result_rows.append(
            {
                "lane": lane,
                "provider": provider,
                "base_case_id": base,
                "expected_artifacts": str(len(expected)),
                "status": status,
                "detail": detail,
                "expected_cases": ",".join(row["case_id"] for row in expected),
            }
        )
    return result_rows, blockers


def write_report(path: Path, result_rows: list[dict[str, str]], blockers: list[str], export_assets: list[dict[str, str]], portal_assets: list[dict[str, str]]) -> None:
    counts = Counter(row["status"] for row in result_rows)
    verdict = "pass" if not blockers else "blocked"
    lines = [
        "# health gmail validation report",
        "",
        f"verdict: `{verdict}`",
        "",
        "coverage:",
        f"- groups checked: {len(result_rows)}",
        f"- status counts: {dict(counts)}",
        "",
    ]
    if blockers:
        lines.append("blockers:")
        lines.extend(f"- {item}" for item in blockers)
        lines.append("")
    lines.extend(summarize_metadata([*export_assets, *portal_assets]))
    lines.extend(
        [
            "",
            "group detail:",
            "",
            "| lane | provider | base case | expected | status | detail |",
            "| --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for row in result_rows:
        lines.append(
            f"| `{row['lane']}` | `{row['provider']}` | `{row['base_case_id']}` | {row['expected_artifacts']} | `{row['status']}` | {row['detail']} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_result_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["lane", "provider", "base_case_id", "expected_artifacts", "status", "detail", "expected_cases"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a full Gmail lab export against a personal health oracle.")
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--export-run", type=Path, required=True)
    parser.add_argument("--portal-run", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    oracle_rows = read_tsv(args.oracle.expanduser().resolve())
    export_run = args.export_run.expanduser().resolve()
    portal_run = args.portal_run.expanduser().resolve() if args.portal_run else None
    export_assets = read_tsv(export_run / "asset_manifest.tsv")
    portal_assets = read_tsv(portal_run / "asset_manifest.tsv") if portal_run else []
    portal_manifest = read_tsv(portal_run / "run_manifest.tsv") if portal_run else []

    result_rows, blockers = audit(oracle_rows, export_assets, portal_assets, portal_manifest)
    out = args.out.expanduser().resolve()
    write_report(out, result_rows, blockers, export_assets, portal_assets)
    write_result_tsv(out.with_suffix(".tsv"), result_rows)
    print(out)
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
