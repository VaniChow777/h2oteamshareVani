#!/usr/bin/env python3
"""
Export funnel widgets from a Sensors dashboard via the same API the UI uses.

This script is tailored for private deployment environments where the dashboard
API is accessible with project token / API secret.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from sensors_api_tool import ROOT, Settings, build_url, load_dotenv, request_json
from sensors_openapi_tool import (
    OpenAPISettings,
    funnel_payload_from_legacy,
    load_query_config,
    openapi_funnel_to_legacy_table,
    openapi_segmentation_to_legacy_table,
    request_json as openapi_request_json,
    segmentation_payload_from_legacy,
)


OUTPUT_DIR = ROOT / "output" / "dashboard_exports"


def slugify(text: str) -> str:
    safe = []
    for char in text:
        if char.isalnum():
            safe.append(char)
        elif char in {"-", "_"}:
            safe.append(char)
        else:
            safe.append("_")
    return "".join(safe).strip("_") or "report"


def dashboard_detail(settings: Settings, dashboard_id: int) -> dict[str, Any]:
    if os.environ.get("SENSORS_AUTH_MODE") == "openapi":
        config = load_query_config()
        if config.get("dashboard_id") != dashboard_id:
            raise KeyError(f"OpenAPI config is for dashboard {config.get('dashboard_id')}, not {dashboard_id}")
        return {
            "id": config.get("dashboard_id"),
            "name": config.get("dashboard_name"),
            "items": [
                {
                    "bookmark": {
                        "id": query["bookmark_id"],
                        "name": query["name"],
                        "type": "/funnel/" if query["type"] == "funnel" else "/segmentation/",
                        "data": json.dumps(query["legacy_payload"], ensure_ascii=False),
                    }
                }
                for query in config.get("queries", {}).values()
            ],
        }
    url = build_url(settings, f"dashboards/{dashboard_id}")
    return request_json(url)


def funnel_payload(bookmark: dict[str, Any], dashboard_id: int, start: str | None, end: str | None) -> dict[str, Any]:
    payload = json.loads(bookmark["data"])
    request_id = f"{int(time.time() * 1000)}:{bookmark['id']}"
    payload.update(
        {
            "bookmarkid": bookmark["id"],
            "bookmark_id": bookmark["id"],
            "dashboard_id": dashboard_id,
            "request_id": request_id,
            "request_type": "SA_FUNNEL",
            "funnel_id": 0,
            "ignore_cache_expire": False,
            "handle_sampling": True,
            "rewrite_by_values": True,
            "use_entire_cache_only": False,
        }
    )
    if start:
        payload["from_date"] = start
    if end:
        payload["to_date"] = end
    return payload


def funnel_report(settings: Settings, bookmark_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("SENSORS_AUTH_MODE") == "openapi":
        openapi_settings = OpenAPISettings.from_env()
        openapi_payload = funnel_payload_from_legacy(payload)
        response = openapi_request_json(openapi_settings, "/api/v3/analytics/v1/model/funnel/report", openapi_payload)
        return openapi_funnel_to_legacy_table(response)

    query = urllib.parse.urlencode(
        {
            "bookmarkId": bookmark_id,
            "async": "false",
            "timeout": "10",
            "project": settings.project,
            "token": settings.api_key,
        }
    )
    url = f"{settings.base_url}/api/v2/sa/funnel/report/?{query}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Funnel report HTTP {exc.code}: {detail}") from exc
        except (socket.timeout, TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Funnel report request timed out after retries for bookmark {bookmark_id}") from last_error


def _normalize_custom_measure(measure: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(measure)
    transform_expression = normalized.get("transformExpression") or normalized.get("expression")
    if isinstance(transform_expression, str):
        _, _, value_format = transform_expression.partition("|")
        normalized["transformExpression"] = transform_expression
        if value_format:
            normalized["format"] = value_format

    normalized.setdefault("default_measure_name", normalized.get("name", ""))
    normalized.setdefault("isExpValid", True)
    normalized.setdefault("status", "view")
    normalized.setdefault("type", "custom")
    normalized.setdefault("id", time.time())
    return normalized


def events_payload(bookmark: dict[str, Any], dashboard_id: int, start: str | None, end: str | None) -> dict[str, Any]:
    payload = json.loads(bookmark["data"])
    request_id = f"{int(time.time() * 1000)}:{bookmark['id']}"
    payload.update(
        {
            "bookmarkid": str(bookmark["id"]),
            "fromDash": json.dumps({"id": dashboard_id, "type": "normal", "size": "normal"}, separators=(",", ":")),
            "request_id": request_id,
            "use_cache": True,
            "arith_rollup": False,
        }
    )
    if start:
        payload["from_date"] = start
    if end:
        payload["to_date"] = end
    payload["measures"] = [_normalize_custom_measure(measure) for measure in payload.get("measures", [])]
    return payload


def events_report(settings: Settings, bookmark_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("SENSORS_AUTH_MODE") == "openapi":
        openapi_settings = OpenAPISettings.from_env()
        openapi_payload = segmentation_payload_from_legacy(payload)
        response = openapi_request_json(openapi_settings, "/api/v3/analytics/v1/model/segmentation/report", openapi_payload)
        return openapi_segmentation_to_legacy_table(response)

    query = urllib.parse.urlencode(
        {
            "bookmarkId": bookmark_id,
            "async": "false",
            "timeout": "10",
            "project": settings.project,
            "token": settings.api_key,
        }
    )
    url = f"{settings.base_url}/api/events/report/?{query}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Events report HTTP {exc.code}: {detail}") from exc


def write_csv(path: Path, report: dict[str, Any]) -> None:
    table = report.get("table_data", {})
    columns = table.get("column_meta_list", [])
    cells = table.get("cells", [])
    if not columns or not cells:
        return

    fieldnames = [column["data_name"] for column in columns]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in cells:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def export_dashboard(settings: Settings, dashboard_id: int, start: str | None, end: str | None) -> list[Path]:
    detail = dashboard_detail(settings, dashboard_id)
    dashboard_name = detail["name"]
    export_dir = OUTPUT_DIR / f"{dashboard_id}_{slugify(dashboard_name)}"
    export_dir.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, Any]] = []
    generated: list[Path] = []

    for index, item in enumerate(detail.get("items", []), start=1):
        bookmark = item.get("bookmark")
        if not bookmark or bookmark.get("type") != "/funnel/":
            continue

        payload = funnel_payload(bookmark, dashboard_id, start, end)
        report = funnel_report(settings, bookmark["id"], payload)

        stem = f"{index:02d}_{slugify(bookmark['name'])}"
        json_path = export_dir / f"{stem}.json"
        csv_path = export_dir / f"{stem}.csv"

        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        write_csv(csv_path, report)

        summary.append(
            {
                "bookmark_id": bookmark["id"],
                "name": bookmark["name"],
                "from_date": payload.get("from_date"),
                "to_date": payload.get("to_date"),
                "json": str(json_path),
                "csv": str(csv_path),
            }
        )
        generated.extend([json_path, csv_path])

    (export_dir / "summary.json").write_text(
        json.dumps(
            {
                "dashboard_id": dashboard_id,
                "dashboard_name": dashboard_name,
                "reports": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    generated.append(export_dir / "summary.json")
    return generated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export funnel widgets from a Sensors dashboard")
    parser.add_argument("--dashboard-id", type=int, required=True, help="Dashboard ID, for example 1522")
    parser.add_argument("--start", help="Start date, such as 2026-04-12")
    parser.add_argument("--end", help="End date, such as 2026-04-25")
    return parser.parse_args()


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    settings = Settings.from_env()

    try:
        files = export_dashboard(settings, args.dashboard_id, args.start, args.end)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {detail}")
        return 1
    except urllib.error.URLError as exc:
        print(f"Network error: {exc}")
        return 1

    print("Export completed:")
    for path in files:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
