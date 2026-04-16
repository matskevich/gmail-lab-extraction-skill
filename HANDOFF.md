# handoff

this is the friend-safe public repo.

repo url:
- `https://github.com/matskevich/gmail-lab-extraction-skill`

what is inside:
- a Codex skill bundle
- runnable scripts for gmail export, portal export, and metadata derivation
- docs, schemas, and examples for agent handoff

what is intentionally excluded:
- local `runs/` with private PDFs, thread JSON, provider JSON, portal URLs, or stderr logs
- `__pycache__`

how to share it:
1. send the github repo link
2. or send a zip/tar archive of this repository

canonical synced local clone for ongoing work:
- `<your-workspace>/gmail-lab-extraction-skill`

how to install the skill:

```bash
cd gmail-lab-extraction-skill
./install.sh
```

after install, the skill will live at:

```bash
~/.codex/skills/gmail-browser-attachments
```

how to use the repo directly:

```bash
./scripts/doctor.sh
./scripts/run_gmail_lab_export.sh ./examples/targets.tsv
./scripts/run_portal_lab_export.sh ./examples/portal_targets.tsv
```

boundary:
- the repo does not solve arbitrary username/password/2fa portal login
- the current green provider adapter is `invitro` anonymous result links
