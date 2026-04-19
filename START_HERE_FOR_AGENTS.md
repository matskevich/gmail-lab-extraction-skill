# Start Here For Agents

read this file first.

## current status

- green:
  - python substrate under `gmail_lab/`
  - `state.db`, message archive, evidence archive
  - `discovery_manifest.tsv`, `evidence_manifest.tsv`, `claims_manifest.tsv`, `analysis_manifest.tsv`
  - claims derivation for `owner`, `analysis_date`, `sample_draw_*`
  - invitro anonymous portal export
  - password-hinted pdf text lane
- yellow:
  - browser historical completeness for some old gmail threads
  - live collector regression stability across delayed attachment hydration
- red:
  - gmail api native discovery/acquisition is not implemented yet
  - generic provider login automation is not implemented

## read order

1. `README.md`
2. `AGENTS.md`
3. `docs/api_first_architecture.md`
4. `docs/completeness_framework.md`
5. `docs/test_strategy.md`
6. `schemas/*.schema.json`

## canonical truths

- evidence first:
  - `raw/`
  - message archive
  - evidence archive
- claims second:
  - `claims_manifest.tsv`
  - `analysis_manifest.tsv`
- do not infer product state from prose only

## primary commands

```bash
./scripts/doctor.sh
python -m gmail_lab --help
python -m pytest
python -m ruff check .
python -m mypy gmail_lab
```

for live browser runs:

```bash
./scripts/run_gmail_discovery.sh ./examples/targets.tsv
./scripts/run_regression_suite.sh ./examples/regression_targets.tsv
```

for substrate / claims:

```bash
gmail-lab init
gmail-lab identity-status
gmail-lab derive-claims
gmail-lab emit-claims-manifest --output ./claims_manifest.tsv
gmail-lab emit-analysis-manifest --output ./analysis_manifest.tsv
```

## known sharp edge

historical cmd threads can still regress into inline-only extraction when gmail attachment controls hydrate late. do not claim completeness from one happy-path smoke run.

## immediate next work

1. stabilize `DCKY6078` / old cmd live extraction
2. implement gmail api native discovery/acquisition
3. keep browser lane as fallback and portal lane
