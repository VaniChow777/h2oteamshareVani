#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_skill_descriptions(repo: Path) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    skills_dir = repo / "skills"
    if not skills_dir.exists():
        return descriptions

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        if not match:
            continue
        fields = {}
        for line in match.group(1).splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
        name = fields.get("name") or skill_md.parent.name
        description = fields.get("description", "")
        descriptions[name] = description
    return descriptions


def short_description(text: str) -> str:
    text = " ".join(text.split())
    if not text:
        return ""
    for marker in (". Use when", "。Use when", " Trigger for", " Use when"):
        if marker in text:
            text = text.split(marker, 1)[0]
            break
    return text.rstrip(".。")


def validate_index(repo: Path, index: dict, discovered: dict[str, str], strict: bool) -> list[str]:
    issues: list[str] = []
    indexed = {item["name"] for item in index.get("skills", [])}
    actual = set(discovered)

    missing = sorted(actual - indexed)
    extra = sorted(indexed - actual)
    if missing:
        issues.append("Missing from skill-index.json: " + ", ".join(missing))
    if extra:
        issues.append("Listed in skill-index.json but not present under skills/: " + ", ".join(extra))

    for item in index.get("skills", []):
        for field in ("name", "category", "topic", "summary"):
            if not item.get(field):
                issues.append(f"{item.get('name', '<unknown>')}: missing {field}")

    if strict and issues:
        return issues
    return issues


def render_readme(repo: Path, index: dict, discovered: dict[str, str]) -> str:
    repo_title = index.get("title", "Codex Skill Backup")
    repo_description = index.get("description", "Codex skills.")
    generated_by = index.get("generated_by", "skills/skill-teamizer/scripts/render_skill_readme.py")
    category_order = index.get("category_order", [])
    skills = index.get("skills", [])
    updates = index.get("updates", [])

    categories: dict[str, dict[str, list[dict]]] = {}
    for item in skills:
        skill = dict(item)
        skill.setdefault("summary", short_description(discovered.get(skill["name"], "")))
        categories.setdefault(skill["category"], {}).setdefault(skill["topic"], []).append(skill)

    ordered_categories = list(category_order)
    for category in sorted(categories):
        if category not in ordered_categories:
            ordered_categories.append(category)

    lines: list[str] = [
        f"# {repo_title}",
        "",
        repo_description,
        "",
        f"> Generated from `skill-index.json` by `{generated_by}`.",
        "",
        "## Skills",
        "",
    ]

    for category in ordered_categories:
        topics = categories.get(category)
        if not topics:
            continue
        lines.extend([f"### {category}", ""])
        for topic in sorted(topics):
            lines.extend([f"#### {topic}", ""])
            for skill in sorted(topics[topic], key=lambda item: item["name"]):
                tags = skill.get("tags", [])
                tag_text = f" ({', '.join(tags)})" if tags else ""
                lines.append(f"- `{skill['name']}`{tag_text}: {skill['summary']}")
            lines.append("")

    if updates:
        lines.extend(["## 更新记录", ""])
        for update in updates:
            date = update.get("date", "")
            note = update.get("note", "")
            skills_text = ", ".join(update.get("skills", []))
            suffix = f" [{skills_text}]" if skills_text else ""
            lines.append(f"- {date}: {note}{suffix}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a categorized README for a Codex skill backup repo.")
    parser.add_argument("repo", type=Path, help="Repository root containing skills/ and skill-index.json.")
    parser.add_argument("--index", type=Path, help="Path to skill-index.json. Defaults to <repo>/skill-index.json.")
    parser.add_argument("--output", type=Path, help="Output README path. Defaults to <repo>/README.md.")
    parser.add_argument("--strict", action="store_true", help="Fail if skill-index.json and skills/ do not match.")
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    index_path = (args.index or repo / "skill-index.json").expanduser().resolve()
    output_path = (args.output or repo / "README.md").expanduser().resolve()

    index = read_json(index_path)
    discovered = read_skill_descriptions(repo)
    issues = validate_index(repo, index, discovered, args.strict)
    if issues:
        print("Index warnings:")
        for issue in issues:
            print(f"- {issue}")
        if args.strict:
            return 1

    output_path.write_text(render_readme(repo, index, discovered), encoding="utf-8")
    print(f"Rendered {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
