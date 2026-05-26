#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
LIB_ROOT = SKILL_ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB_ROOT))

from sensors_api_tool import load_dotenv


def load_sensors_env() -> None:
    code_env = os.environ.get("CODEX_SENSORS_ENV")
    if code_env:
        load_dotenv(Path(code_env).expanduser())
    load_dotenv(Path.home() / ".codex-secrets" / "sensors" / "webob.env")
    load_dotenv(SKILL_ROOT / ".env")


def main() -> int:
    load_sensors_env()
    os.environ.setdefault("SENSORS_AUTH_MODE", "openapi")
    required = ["SENSORS_BASE_URL", "SENSORS_PROJECT", "SENSORS_OPENAPI_KEY"]
    missing = [name for name in required if not os.environ.get(name)]
    config = SKILL_ROOT / "config" / "webob_openapi_queries.json"
    if missing:
        print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
        print("Copy config/sensors.env.example to a local-only env file and set CODEX_SENSORS_ENV to that path.", file=sys.stderr)
        return 1
    if os.environ.get("SENSORS_AUTH_MODE") != "openapi":
        print("SENSORS_AUTH_MODE should be openapi for this team-ready skill.", file=sys.stderr)
        return 1
    if not os.environ["SENSORS_OPENAPI_KEY"].startswith("#K-"):
        print("SENSORS_OPENAPI_KEY should start with #K-.", file=sys.stderr)
        return 1
    if not config.exists():
        print(f"Missing OpenAPI query config: {config}", file=sys.stderr)
        return 1
    print("Environment shape looks OK. Network/API connectivity is not checked by this command.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
