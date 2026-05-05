# Agent Install

This repo has three interfaces:

1. `gmail-lab` engine: Python package, scripts, schemas, and repo docs.
2. Agent skills: installable workflow routers for Codex and Claude Code.
3. Future MCP: optional tool API once the workflow needs cross-client tool calls.

## Codex

Install repo skills locally:

```bash
./install.sh
```

This installs:

- `gmail-lab-export`: workflow router for discovery, export, manifests, enrichment, and passworded PDFs
- `gmail-browser-attachments`: lower-level CDP attachment/inline-image extraction helper

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
7. `docs/test_strategy.md`
8. `docs/secret_resolution.md`
9. `schemas/*.schema.json`

Then run:

```bash
./scripts/doctor.sh
python -m gmail_lab --help
gmail-lab diagnose-gmail-acquisition
```

## Packaging Rule

Keep responsibilities separate:

- engine code lives under `gmail_lab/` and `scripts/`
- repo truth lives under docs and schemas
- skills route agent behavior and should stay concise
- MCP should expose stable tool calls only after the CLI/workflow is stable
