#!/bin/zsh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
CODEX_SKILLS_DIR="$CODEX_HOME_DIR/skills"
CLAUDE_SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
CODEX_SKILLS=(gmail-lab-export gmail-browser-attachments)
CLAUDE_SKILLS=(gmail-lab-export)

for skill_name in "${CODEX_SKILLS[@]}"; do
  source_dir="$REPO_ROOT/skills/$skill_name"
  dest_dir="$CODEX_SKILLS_DIR/$skill_name"
  if [[ ! -f "$source_dir/SKILL.md" ]]; then
    echo "missing codex skill bundle at $source_dir" >&2
    exit 1
  fi
  mkdir -p "$CODEX_SKILLS_DIR"
  rm -rf "$dest_dir"
  cp -R "$source_dir" "$dest_dir"
  echo "installed codex skill: $dest_dir"
done

if [[ "${INSTALL_CLAUDE_SKILLS:-0}" == "1" ]]; then
  for skill_name in "${CLAUDE_SKILLS[@]}"; do
    source_dir="$REPO_ROOT/.claude/skills/$skill_name"
    dest_dir="$CLAUDE_SKILLS_DIR/$skill_name"
    if [[ ! -f "$source_dir/SKILL.md" ]]; then
      echo "missing claude skill bundle at $source_dir" >&2
      exit 1
    fi
    mkdir -p "$CLAUDE_SKILLS_DIR"
    rm -rf "$dest_dir"
    cp -R "$source_dir" "$dest_dir"
    echo "installed claude skill: $dest_dir"
  done
else
  echo "claude skill available at: $REPO_ROOT/.claude/skills/gmail-lab-export"
  echo "set INSTALL_CLAUDE_SKILLS=1 to copy it into $CLAUDE_SKILLS_DIR"
fi

echo "restart codex to pick up new skills"
