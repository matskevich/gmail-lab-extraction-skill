#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmail_lab.core.manifests.regression_summary import (  # noqa: E402
    build_regression_summary_rows,
    write_regression_summary,
)


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print(
            "usage: scripts/summarize_regression_run.py <run-dir> [output-path]",
            file=sys.stderr,
        )
        return 2

    run_dir = Path(sys.argv[1]).expanduser().resolve()
    manifest_path = run_dir / "regression_manifest.tsv"
    if not manifest_path.exists():
        print(f"missing regression manifest: {manifest_path}", file=sys.stderr)
        return 1

    output_path = (
        Path(sys.argv[2]).expanduser().resolve()
        if len(sys.argv) == 3
        else (run_dir / "regression_summary.tsv")
    )
    rows = build_regression_summary_rows(manifest_path)
    write_regression_summary(output_path, rows)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
