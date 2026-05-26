#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]+"),
    re.compile(r"ghp_[A-Za-z0-9_]{36}"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
]
LOCAL_PATH_RE = re.compile(r"/Users/[^/]+/(Documents|Desktop|Downloads|Library|\.codex)(/[^\s'\"`)]*)?")
BAD_NAMES = {".DS_Store", ".env"}
BAD_SUFFIXES = {".pyc", ".pyo", ".log"}
SKIP_PARTS = {".git", "__pycache__", "node_modules", "output", "tmp", ".pytest_cache"}


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        yield path


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a Codex skill or skill backup repo for team-install readiness.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    root = args.path.expanduser().resolve()
    if not root.exists():
        print(f"Missing path: {root}", file=sys.stderr)
        return 2

    issues: list[str] = []
    if (root / "SKILL.md").exists():
        skill_roots = [root]
    else:
        skill_roots = [path for path in (root / "skills").glob("*") if (path / "SKILL.md").exists()] if (root / "skills").exists() else []
    if not skill_roots:
        issues.append("No SKILL.md found at root and no skills/*/SKILL.md found.")

    for skill_root in skill_roots:
        rel = skill_root.relative_to(root) if skill_root != root else Path(".")
        if not (skill_root / "agents" / "openai.yaml").exists():
            issues.append(f"{rel}: missing agents/openai.yaml")
        if not (skill_root / ".gitignore").exists():
            issues.append(f"{rel}: missing .gitignore")
        if not ((skill_root / "requirements.txt").exists() or (skill_root / "package.json").exists()):
            issues.append(f"{rel}: missing requirements.txt/package.json or standard-library-only note")

    for path in iter_files(root):
        rel = path.relative_to(root)
        if path.name in BAD_NAMES or path.suffix in BAD_SUFFIXES:
            issues.append(f"{rel}: local-only file should not be shared")
            continue
        text = read_text(path)
        if text is None:
            continue
        if LOCAL_PATH_RE.search(text):
            issues.append(f"{rel}: contains local absolute path")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                issues.append(f"{rel}: potential secret pattern")
                break

    if issues:
        print("Audit failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Audit passed: no obvious teamization blockers found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
