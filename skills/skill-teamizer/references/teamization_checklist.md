# Teamization Checklist

## Skill Shape

- `SKILL.md` has clear `name` and trigger-focused `description`.
- `SKILL.md` explains workflow, inputs, outputs, and boundaries.
- Long domain口径 or migration details live under `references/`.
- Repeated code lives in `scripts/lib/`.
- `agents/openai.yaml` uses `interface:` and has a default prompt mentioning `$skill-name`.

## Secret Safety

- No real `.env`, token, cookie, private key, webhook URL, signed temporary URL, or API secret is committed.
- Shared config uses `*.env.example`.
- Runtime code reads secrets from env vars or local-only env files.
- Scripts fail with clear missing-env messages.
- Generated raw exports are excluded by `.gitignore` or require an explicit debug flag.

## Portability

- No `/Users/<name>/...` or temporary project directory dependencies remain.
- Scripts resolve bundled files from `Path(__file__).resolve()`.
- Required configs, templates, schemas, and fixtures are bundled under the skill.
- Output directory is explicit and not inside shared source by default.
- The skill can be copied to another user's `$CODEX_HOME/skills` and still load.

## Dependency Management

- `requirements.txt`, `package.json`, or a standard-library-only note exists.
- Optional system dependencies are documented in `SKILL.md`.
- `scripts/check_env.py` or equivalent verifies required env/config shape.
- Network/API smoke tests are separate from static checks.

## Validation

- Main scripts support `--help`.
- Syntax check passes.
- Secret scan passes.
- Local path scan passes.
- Smoke test passes or the blocker is clearly documented.
- New merged outputs are compared with old skill outputs when replacing old skills.

## Git Publishing

- New skill added to the target backup repository.
- Superseded old skills removed only when requested.
- Root `skill-index.json` reflects the final skill set, categories, topics, summaries, tags, and update notes.
- `README.md` is regenerated from `skill-index.json`.
- `git status --short` is clean before and after push.
- Push target and branch are verified.
- Commit identity warning is reported if git auto-generates author identity.
