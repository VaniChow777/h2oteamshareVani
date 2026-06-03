# Git Publish Workflow

## Personal Git

Use personal git for the first consolidation pass:

```bash
python3 $CODEX_HOME/skills/github-skill-backup/scripts/prepare_skill_backup.py \
  --target personal \
  --repo codexgalaxy777 \
  --workspace <local-backup-workspace>/codexgalaxy777 \
  --skill <new-skill> \
  --message "Add teamized <new-skill>"
```

If replacing old skills, delete the superseded folders in the backup workspace, rerun the backup script for the new skill, inspect status, then commit and push.

## Overseas/Team Git

Use overseas git only after the skill passes team-install checks:

```bash
python3 $CODEX_HOME/skills/github-skill-backup/scripts/prepare_skill_backup.py \
  --target overseas \
  --owner VaniChow777 \
  --repo h2oteamshareVani \
  --workspace <local-backup-workspace>/h2oteamshareVani \
  --skill <new-skill> \
  --message "Add teamized <new-skill>"
```

Then remove superseded folders from that repository workspace only when the user requested replacement.

## Required Checks Before Push

```bash
git status --short
git diff --stat
python3 skills/skill-teamizer/scripts/render_skill_readme.py . --strict
find . -name .DS_Store -o -name .env -o -name '*.pyc' -o -name __pycache__
rg -n "(/Users/[^/]+|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_|github_pat_|-----BEGIN)" .
```

If the current branch is not `main`, compare `origin/main...HEAD` before pushing. Use `git push origin HEAD:main` only when `origin/main` is an ancestor and the intended target is `main`.

## README and Index

Each backup repository should keep a root-level `skill-index.json`. Treat it as the source of truth for README categories, topics, summaries, tags, and short update notes.

Use these primary categories:

- `业务能力`
- `汇报总结能力`
- `AI 使用能力`

After adding, removing, replacing, or reclassifying a skill, update `skill-index.json`, render `README.md`, and inspect the diff before pushing.
