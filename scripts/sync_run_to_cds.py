#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
from pathlib import Path


DEFAULT_CDS_RAW_ROOT = Path("/srv/integrations/cds/raw")
IMPORTABLE_STATUSES = {"ok", "accepted"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_existing_hashes(client_root: Path, excluded_run_root: Path) -> dict[str, list[str]]:
    existing: dict[str, list[str]] = {}
    for folder_name in ("from emails", "from email"):
        root = client_root / folder_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.is_relative_to(excluded_run_root):
                continue
            try:
                existing.setdefault(sha256(path), []).append(str(path))
            except OSError:
                continue
    return existing


def build_cds_asset_manifest(
    source_manifest_path: Path,
    destination_run_root: Path,
    destination_final: Path,
) -> tuple[int, int]:
    destination_manifest_path = destination_run_root / "cds_asset_manifest.tsv"
    with source_manifest_path.open(encoding="utf-8", newline="") as src_fh:
        reader = csv.DictReader(src_fh, delimiter="\t")
        fieldnames = reader.fieldnames or []
        rows_to_write: list[dict[str, str]] = []
        seen_basenames: set[str] = set()
        skipped_count = 0
        for row in reader:
            final_file = (row.get("final_file") or "").strip()
            status = (row.get("status") or "").strip().lower()
            if not final_file:
                skipped_count += 1
                continue
            if status and status not in IMPORTABLE_STATUSES:
                skipped_count += 1
                continue
            basename = Path(final_file).name
            if not basename:
                skipped_count += 1
                continue
            if basename in seen_basenames:
                skipped_count += 1
                continue
            destination_file = destination_final / basename
            if not destination_file.exists():
                skipped_count += 1
                continue
            updated_row = dict(row)
            updated_row["final_file"] = str(destination_file)
            rows_to_write.append(updated_row)
            seen_basenames.add(basename)

    with destination_manifest_path.open("w", encoding="utf-8", newline="") as dst_fh:
        writer = csv.DictWriter(dst_fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows_to_write)

    return (len(rows_to_write), skipped_count)


def copy_run_to_cds(
    run_dir: Path,
    cds_client_dir_name: str,
    cds_raw_root: Path,
    folder_name: str | None,
) -> tuple[Path, int, int, int, int]:
    final_dir = run_dir / "final"
    if not final_dir.exists():
        raise SystemExit(f"missing final directory: {final_dir}")

    asset_manifest_path = run_dir / "asset_manifest.tsv"
    if not asset_manifest_path.exists():
        raise SystemExit(f"missing asset manifest: {asset_manifest_path}")

    client_root = cds_raw_root / cds_client_dir_name
    run_folder_name = folder_name or run_dir.name
    destination_run_root = client_root / "from emails" / run_folder_name
    destination_final = destination_run_root / "final"

    if destination_run_root.exists():
        shutil.rmtree(destination_run_root)
    destination_final.mkdir(parents=True, exist_ok=True)

    existing_hashes = collect_existing_hashes(client_root=client_root, excluded_run_root=destination_run_root)

    copied_rows: list[tuple[str, str, str]] = []
    duplicate_rows: list[tuple[str, str, str]] = []
    for source_file in sorted(final_dir.rglob("*")):
        if not source_file.is_file():
            continue
        rel = source_file.relative_to(final_dir)
        destination_file = destination_final / rel
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination_file)
        digest = sha256(source_file)
        copied_rows.append((str(source_file), str(destination_file), digest))
        for existing_match in existing_hashes.get(digest, []):
            duplicate_rows.append((str(destination_file), digest, existing_match))

    for artifact_name in ("asset_manifest.tsv", "run_manifest.tsv", "run_meta.txt"):
        artifact_path = run_dir / artifact_name
        if artifact_path.exists():
            shutil.copy2(artifact_path, destination_run_root / artifact_name)

    accepted_manifest_rows, skipped_manifest_rows = build_cds_asset_manifest(
        source_manifest_path=asset_manifest_path,
        destination_run_root=destination_run_root,
        destination_final=destination_final,
    )

    sync_manifest_path = destination_run_root / "cds_sync_manifest.tsv"
    with sync_manifest_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(("src_final_file", "dst_final_file", "sha256"))
        writer.writerows(copied_rows)

    duplicate_manifest_path = destination_run_root / "duplicate_hash_matches.tsv"
    with duplicate_manifest_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(("dst_final_file", "sha256", "existing_match"))
        writer.writerows(duplicate_rows)

    return (
        destination_run_root,
        len(copied_rows),
        len(duplicate_rows),
        accepted_manifest_rows,
        skipped_manifest_rows,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy one materialized gmail extraction run into the CDS raw filesystem handoff.")
    parser.add_argument("run_dir", help="Run directory produced by run_gmail_lab_export.sh")
    parser.add_argument("cds_client_dir_name", help="CDS client raw directory name, for example openclaw_ilya-mutovin")
    parser.add_argument("--cds-raw-root", default=str(DEFAULT_CDS_RAW_ROOT), help="Root directory that contains CDS raw client folders")
    parser.add_argument("--folder-name", default=None, help="Override the destination folder name under 'from emails/'")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    cds_raw_root = Path(args.cds_raw_root).expanduser().resolve()
    (
        destination_run_root,
        copied_count,
        duplicate_count,
        accepted_manifest_rows,
        skipped_manifest_rows,
    ) = copy_run_to_cds(
        run_dir=run_dir,
        cds_client_dir_name=args.cds_client_dir_name,
        cds_raw_root=cds_raw_root,
        folder_name=args.folder_name,
    )
    print(f"run_dir={run_dir}")
    print(f"cds_run_dir={destination_run_root}")
    print(f"copied_final_files={copied_count}")
    print(f"cds_asset_manifest_rows={accepted_manifest_rows}")
    print(f"skipped_manifest_rows={skipped_manifest_rows}")
    print(f"duplicate_hash_matches={duplicate_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
