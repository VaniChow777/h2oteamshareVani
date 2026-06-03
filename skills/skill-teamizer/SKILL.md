---
name: skill-teamizer
description: Convert one or more personal Codex skills into a team-installable skill. Use when the user asks to merge, harden, publish, backup, sync, or teamize personal skills; remove local path dependencies; handle key/token/env safety; add install checks; run secret/path scans; smoke test a skill; sync to personal GitHub or overseas/team GitHub; or delete superseded skills from skill backup repositories.
---

# Skill Teamizer

## Purpose

Use this skill to turn personal Codex skills into team-installable, publishable skill assets. The standard outcome is a clean skill folder that can be installed by another teammate without the original author's local directories, hidden files, or private credentials, then published to the personal or team backup repository with a categorized README.

## Core Rules

- Never copy real secrets, `.env` files, cookies, private keys, generated raw exports, or signed temporary URLs into a shared skill.
- Do not edit or delete the user's original local skills unless explicitly asked. Prefer creating a new consolidated skill first, validating it, then removing old skills only from git backup repositories when requested.
- Preserve business logic and metric口径 before refactoring. Validate merged outputs against the old skill outputs when possible.
- Keep `SKILL.md` concise. Move long checklists to `references/` and deterministic checks to `scripts/`.
- Treat git push and deletion from backup repositories as separate, explicit phases with status checks before pushing.

## Standard Workflow

1. Inventory the source skills:
   - List files and scripts.
   - Read `SKILL.md`, `agents/openai.yaml`, and the main scripts.
   - Search for local paths, secrets, env usage, output paths, and duplicated helpers.
2. Choose the target shape:
   - Keep one skill if the source skill is already cohesive.
   - Merge multiple skills when they are separate views of the same workflow or report.
   - Create a shared `scripts/lib/` layer when scripts use the same clients, parsers, target parsing, or output helpers.
3. Build the team-ready skill:
   - Add `SKILL.md`.
   - Add `agents/openai.yaml`.
   - Add `config/*.env.example`.
   - Add `scripts/check_env.py` or an equivalent self-check.
   - Add `requirements.txt` or explicitly state standard-library-only.
   - Add `.gitignore`.
   - Add `references/` only for detailed口径, install checklist, or migration notes needed by Codex.
4. Remove local-only assumptions:
   - Replace `/Users/<name>/...` with `Path(__file__).resolve()` based paths, `$CODEX_HOME`, env vars, or arguments.
   - Bundle required templates/configs under the skill.
   - Make output directories explicit and safe.
5. Run validation:
   - `--help` for all CLI scripts.
   - Python compile or equivalent language syntax checks.
   - Secret/path scan.
   - Dependency/env self-check.
   - Smoke test with the smallest safe real query or fixture.
6. Sync to git only after local validation:
   - Use the GitHub skill backup workflow when publishing selected local skills.
   - After adding the new skill, delete superseded old skills from the backup workspace only when the user asked for repository减法.
   - Check `git status --short`, `git diff --stat`, and secret/path scans before push.
7. Maintain repository presentation:
   - Keep `skill-index.json` at the repository root as the source of truth for category, topic, summary, tags, and update notes.
   - Generate `README.md` with `scripts/render_skill_readme.py`.
   - Use the user's primary categories: `业务能力`, `汇报总结能力`, and `AI 使用能力`.

## Audit Commands

Prefer the bundled audit script for a first pass:

```bash
python3 scripts/audit_skill.py /path/to/skill-or-repo
```

Use the manual checklist in `references/teamization_checklist.md` when the audit finds issues or the skill has custom deployment needs.

## README Publishing

When a skill is added, removed, renamed, or reclassified in a backup repository:

```bash
python3 skills/skill-teamizer/scripts/render_skill_readme.py . --strict
```

Before pushing, confirm the generated README matches the intended publishing target:

- Personal repo `codexgalaxy777`: may include personal-only skills, but still must not include secrets.
- Team repo `h2oteamshareVani`: include only team-shareable skills and team-safe context.
- If a skill appears in both repos, keep its category/topic consistent unless the audience needs a different presentation.

## Git Publishing

When the user asks to sync, back up, or publish a teamized skill:

- Use the installed `github-skill-backup` skill if available.
- For personal git, target `codexgalaxy777` unless the user says otherwise.
- For overseas/team git, target `h2oteamshareVani` unless the user says otherwise.
- Never rely on the backup script to delete old skills automatically; inspect the repository workspace and remove superseded skill folders deliberately.
- Push only after the local backup workspace is clean and the user-requested replacement set is visible in `README.md`.

## Output Style

Report the result as:

- What was created or changed.
- What validations passed.
- What was not done yet.
- Exact next step for local smoke test, personal git sync, overseas git sync, or old skill cleanup.

Keep conclusions short and operational. Link the created skill files and generated reports when available.
