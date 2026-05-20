# Agent Install

This repo has three interfaces:

1. `gmail-lab` engine: Python package, scripts, schemas, and repo docs.
2. Agent skills: installable workflow routers for Codex and Claude Code.
3. Future MCP: optional tool API once the workflow needs cross-client tool calls.

## Codex

Install repo skills locally:

```bash
./install.sh
gmail-lab --help
```

This installs the `gmail-lab` CLI with `pipx` when available, then installs:

- `gmail-lab-export`: workflow router for discovery, export, manifests, enrichment, and passworded PDFs
- `gmail-browser-attachments`: lower-level CDP attachment/inline-image extraction helper

If `pipx` is unavailable, `install.sh` creates `~/.local/bin/gmail-lab` as a wrapper around the repo venv. If the command is still not found, add `~/.local/bin` to `PATH` or rerun from the repo with `./.venv/bin/gmail-lab`.

Restart Codex after installation so skills are discovered.

## Claude Code

Use project-local skill directly from:

```text
.claude/skills/gmail-lab-export/SKILL.md
```

For user-level installation:

```bash
mkdir -p ~/.claude/skills
cp -R .claude/skills/gmail-lab-export ~/.claude/skills/gmail-lab-export
```

Claude Code watches existing skill directories for changes. If `~/.claude/skills` did not exist when the session started, restart Claude Code.

## Generic Agent

Read in this order:

1. `START_HERE_FOR_AGENTS.md`
2. `AGENTS.md`
3. `README.md`
4. `docs/architecture.md`
5. `docs/google_api_setup.md`
6. `docs/acquisition_auth_router.md`
7. `docs/learning_loop.md`
8. `docs/test_strategy.md`
9. `docs/secret_resolution.md`
10. `schemas/*.schema.json`

Then run:

```bash
./scripts/doctor.sh
gmail-lab setup --skip-auth
python -m gmail_lab --help
gmail-lab setup-google --check-only
gmail-lab diagnose-gmail-acquisition
gmail-lab verify-gmail-paths --targets-tsv ./tmp/private_targets.tsv
```

For a clean Gmail API install, use:

```bash
gmail-lab setup-google --client-secrets ~/.gmail-lab/oauth-client.json
gmail-lab verify-gmail-paths --targets-tsv ./tmp/private_targets.tsv --run-dir ./runs/gmail-smoke --allow-live
gmail-lab acquire-gmail ./tmp/private_targets.tsv ./runs/gmail-acquire-run
gmail-lab explain-run ./runs/gmail-acquire-run
```

## Packaging Rule

Keep responsibilities separate:

- engine code lives under `gmail_lab/` and `scripts/`
- repo truth lives under docs and schemas
- skills route agent behavior and should stay concise
- MCP should expose stable tool calls only after the CLI/workflow is stable
