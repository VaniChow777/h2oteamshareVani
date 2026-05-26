#!/usr/bin/env python3
"""
Small helper for private-deployed Sensors Analytics API calls.

It keeps secrets in environment variables and gives us two useful modes:
1. `ping` verifies that base URL / project / API secret are wired correctly.
2. `call` hits any API path and stores the JSON response locally.

This is intentionally dependency-free so we can start quickly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = ROOT / "output"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class Settings:
    base_url: str
    project: str
    api_secret: str

    @property
    def api_key(self) -> str:
        """Backward-compatible alias for older scripts.

        The current dashboard/funnel helpers use Sensors' legacy `token=`
        authentication, where the token value is the project API secret, not
        the newer OpenAPI `#K-...` API Key.
        """
        return self.api_secret

    @classmethod
    def from_env(cls) -> "Settings":
        auth_mode = os.environ.get("SENSORS_AUTH_MODE", "legacy")
        secret = os.environ.get("SENSORS_API_SECRET") or os.environ.get("SENSORS_API_KEY")
        missing = [
            name
            for name in ("SENSORS_BASE_URL", "SENSORS_PROJECT")
            if not os.environ.get(name)
        ]
        if not secret and auth_mode != "openapi":
            missing.append("SENSORS_API_SECRET")
        if missing:
            raise SystemExit(
                "Missing environment variables: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill them in."
            )
        if secret and secret.startswith("#K-") and auth_mode != "openapi":
            raise SystemExit(
                "SENSORS_API_SECRET appears to contain an OpenAPI API Key (#K-...). "
                "These dashboard/funnel endpoints require the project API secret used as token=."
            )

        return cls(
            base_url=os.environ["SENSORS_BASE_URL"].rstrip("/"),
            project=os.environ["SENSORS_PROJECT"],
            api_secret=secret or "",
        )


def last_full_week(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday - timedelta(days=7)
    end = this_monday - timedelta(days=1)
    return start, end


def build_url(settings: Settings, api_path: str, extra_query: dict[str, str] | None = None) -> str:
    api_path = api_path.lstrip("/")
    parsed = urllib.parse.urlsplit(api_path)
    query = {
        "project": settings.project,
        "token": settings.api_key,
    }
    existing_query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.update(dict(existing_query))
    if extra_query:
        query.update(extra_query)
    clean_path = parsed.path
    return f"{settings.base_url}/api/{clean_path}?{urllib.parse.urlencode(query)}"


def request_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    headers = {"Content-Type": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, method=method.upper(), headers=headers, data=data)
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read().decode("utf-8")
        if not raw:
            return {}
        return json.loads(raw)


def command_ping(settings: Settings) -> int:
    url = build_url(settings, "dashboards")
    try:
        data = request_json(url)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1

    print("API connectivity looks good.")
    if isinstance(data, dict):
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
    else:
        print(str(data)[:2000])
    return 0


def command_call(settings: Settings, args: argparse.Namespace) -> int:
    output_dir = DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    query: dict[str, str] = {}
    if args.start and args.end:
        query["start"] = args.start
        query["end"] = args.end

    payload = None
    if args.body_file:
        payload = json.loads(Path(args.body_file).read_text(encoding="utf-8"))

    url = build_url(settings, args.api_path, query)
    try:
        data = request_json(url, method=args.method, payload=payload)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1

    target = output_dir / args.output
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved response to {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sensors API helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ping_parser = subparsers.add_parser("ping", help="Check API connectivity")
    ping_parser.set_defaults(func=command_ping)

    call_parser = subparsers.add_parser("call", help="Call a specific API path")
    call_parser.add_argument("api_path", help="API path after /api/, for example dashboards")
    call_parser.add_argument("--method", default="GET", choices=("GET", "POST"))
    call_parser.add_argument("--body-file", help="JSON file for POST request body")
    call_parser.add_argument("--output", default="response.json", help="Output filename")
    call_parser.add_argument("--start", help="Start date, such as 2026-04-13")
    call_parser.add_argument("--end", help="End date, such as 2026-04-19")
    call_parser.set_defaults(func=command_call)

    week_parser = subparsers.add_parser("last-week", help="Print last full week range")
    week_parser.set_defaults(func=None)

    return parser


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "last-week":
        start, end = last_full_week()
        print(json.dumps({"start": str(start), "end": str(end)}, ensure_ascii=False))
        return 0

    settings = Settings.from_env()
    if args.command == "call":
        return command_call(settings, args)
    return args.func(settings)


if __name__ == "__main__":
    raise SystemExit(main())
