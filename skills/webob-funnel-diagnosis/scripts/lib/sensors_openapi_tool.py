#!/usr/bin/env python3
"""
Sensors Analytics OpenAPI helper.

This module is for the newer OpenAPI endpoints that authenticate with a
`#K-...` API Key. It intentionally lives next to the legacy helper because the
dashboard/funnel UI endpoints still require API Secret via `token=`.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sensors_api_tool import ROOT, load_dotenv


DEFAULT_OUTPUT_DIR = ROOT / "output" / "openapi"
DEFAULT_CONFIG = ROOT.parents[1] / "config" / "webob_openapi_queries.json"


@dataclass
class OpenAPISettings:
    base_url: str
    project: str
    api_key: str

    @classmethod
    def from_env(cls) -> "OpenAPISettings":
        missing = [
            name
            for name in ("SENSORS_BASE_URL", "SENSORS_PROJECT", "SENSORS_OPENAPI_KEY")
            if not os.environ.get(name)
        ]
        if missing:
            raise SystemExit(
                "Missing environment variables: "
                + ", ".join(missing)
                + ". Set SENSORS_OPENAPI_KEY to a Sensors OpenAPI API Key (#K-...)."
            )
        api_key = os.environ["SENSORS_OPENAPI_KEY"]
        if not api_key.startswith("#K-"):
            raise SystemExit("SENSORS_OPENAPI_KEY should be the #K-... OpenAPI API Key, not API Secret.")
        base_url = os.environ.get("SENSORS_OPENAPI_BASE_URL") or default_openapi_base_url(os.environ["SENSORS_BASE_URL"])
        return cls(
            base_url=base_url.rstrip("/"),
            project=os.environ["SENSORS_PROJECT"],
            api_key=api_key,
        )


def default_openapi_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.port:
        return base_url.rstrip("/")
    host = parsed.hostname or parsed.netloc
    if parsed.username or parsed.password:
        netloc = parsed.netloc
    else:
        netloc = f"{host}:8107"
    return urllib.parse.urlunsplit(("http", netloc, "", "", ""))


def openapi_headers(settings: OpenAPISettings) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "api-key": settings.api_key,
        "Sensors-Language": "ZH-CN",
        "sensorsdata-project": settings.project,
    }


def openapi_url(settings: OpenAPISettings, path: str) -> str:
    path = "/" + path.lstrip("/")
    return f"{settings.base_url}{path}"


def request_json(settings: OpenAPISettings, path: str, payload: dict[str, Any], timeout: int = 180) -> Any:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = openapi_url(settings, path)
    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            url,
            data=body,
            headers=openapi_headers(settings),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return {}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
                    return {"code": "SUCCESS", "stream": records}
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {502, 503, 504} or attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
        except (socket.timeout, TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"OpenAPI request failed after retries: {url}") from last_error


def openapi_funnel_to_legacy_table(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict) or "metadata_columns" not in data:
        return response

    columns = list(data.get("metadata_columns", {}).keys())
    cells: list[dict[str, Any]] = []
    for raw_row in data.get("detail_rows", []):
        row = {column: raw_row[index] if index < len(raw_row) else None for index, column in enumerate(columns)}
        if "total_user" in row:
            row["step_1.user_count"] = row.get("total_user")

        conversion_indices = sorted(
            int(column.rsplit("_", 1)[1])
            for column in row
            if column.startswith("convert_user_step_") and column.rsplit("_", 1)[1].isdigit()
        )
        for index in conversion_indices:
            row[f"step_{index + 1}.user_count"] = row.get(f"convert_user_step_{index}")
            rate = row.get(f"convert_rate_step_{index}")
            if rate not in (None, ""):
                row[f"step_{index + 1}.conversion_rate"] = float(rate) * 100

        if "completion_converted_user" in row:
            row["step_fold.user_count"] = row.get("completion_converted_user")
        if "completion_rate" in row and row.get("completion_rate") not in (None, ""):
            row["step_fold.conversion_rate"] = float(row["completion_rate"]) * 100
        cells.append(row)

    return {
        **response,
        "table_data": {
            "column_meta_list": [{"data_name": column} for column in columns],
            "cells": cells,
        },
    }


def _strip_ui_only(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {
            key: _strip_ui_only(item)
            for key, item in value.items()
            if not key.startswith("$$") and key not in {"state", "isSaved", "config"}
        }
        if isinstance(cleaned.get("relation"), str):
            relation = cleaned["relation"].upper()
            if relation in {"AND", "OR"}:
                cleaned["relation"] = relation
        return cleaned
    if isinstance(value, list):
        return [_strip_ui_only(item) for item in value]
    return value


def funnel_payload_from_legacy(legacy_payload: dict[str, Any], start: str | None = None, end: str | None = None) -> dict[str, Any]:
    """Translate a saved dashboard funnel payload into OpenAPI v3 shape.

    The dashboard payload already stores the same funnel definition users see in
    the UI. This translator keeps the analysis semantics and drops UI/runtime
    fields that are not part of the OpenAPI contract.
    """
    legacy_funnel = _strip_ui_only(legacy_payload.get("funnel_define", {}))
    funnel_define = {
        "max_convert_time": legacy_funnel.get("max_convert_time"),
        "steps": [
            {
                key: value
                for key, value in {
                    "event_name": step.get("event_name"),
                    "filter": step.get("filter"),
                    "relevance_field": step.get("relevance_field"),
                }.items()
                if value not in (None, "")
            }
            for step in legacy_funnel.get("steps", [])
        ],
    }
    by_fields = _strip_ui_only(legacy_payload.get("by_fields", []))
    by_field_steps = _strip_ui_only(legacy_payload.get("by_field_steps", []))
    grouped = [
        (field, by_field_steps[index] if index < len(by_field_steps) else 0)
        for index, field in enumerate(by_fields)
        if isinstance(field, str) and not field.endswith("$time")
    ]
    payload: dict[str, Any] = {
        "funnel": funnel_define,
        "from_date": start or legacy_payload.get("from_date"),
        "to_date": end or legacy_payload.get("to_date"),
        "by_fields": [field for field, _ in grouped],
        "by_field_steps": [step for _, step in grouped],
        "filter": _strip_ui_only(legacy_payload.get("filter", {})),
        "filter_field_steps": _strip_ui_only(legacy_payload.get("filter_field_steps", [])),
        "unit": str(legacy_payload.get("unit", "day")).upper(),
        "rollup": True,
        "sampling_factor": legacy_payload.get("sampling_factor", 64),
        "use_cache": False,
        "extend_over_end_date": "true" if legacy_payload.get("extend_over_end_date", True) else "false",
    }
    for key in ("calculation_caliber", "subject_id", "time_zone_mode", "server_time_zone", "trade_day_mode"):
        if key in legacy_payload:
            payload[key] = _strip_ui_only(legacy_payload[key])
    return payload


def _normalize_custom_measure(measure: dict[str, Any]) -> dict[str, Any]:
    normalized = _strip_ui_only(measure)
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
    return normalized


def openapi_segmentation_to_legacy_table(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict) or "metadata_columns" not in data:
        return response

    metadata = data.get("metadata_columns", {})
    columns = list(metadata.keys())
    dimension_columns = [column for column in columns if column != "date" and metadata.get(column) == "STRING"]
    metric_columns = [column for column in columns if column not in dimension_columns and column != "date"]
    cells: list[dict[str, Any]] = []
    rollup_rows: list[dict[str, Any]] = []
    for raw_row in data.get("detail_rows", []):
        row = {column: raw_row[index] if index < len(raw_row) else None for index, column in enumerate(columns)}
        cells.append(row)
        rollup_rows.append(
            {
                "by_values": [row.get(column) for column in dimension_columns],
                "values": [[row.get(column) for column in metric_columns]],
            }
        )
    return {
        **response,
        "table_data": {
            "column_meta_list": [{"data_name": column} for column in columns],
            "cells": cells,
        },
        "rollup_result": {
            "columns": metric_columns,
            "rows": rollup_rows,
        },
    }


def stream_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    if "stream" in response:
        rows = []
        for item in response["stream"]:
            data = item.get("data", {})
            columns = data.get("columns", [])
            values = data.get("data", [])
            rows.append({column: values[index] if index < len(values) else None for index, column in enumerate(columns)})
        return rows
    data = response.get("data", {}) if isinstance(response, dict) else {}
    columns = data.get("columns", [])
    values = data.get("data", [])
    if columns and values:
        return [{column: values[index] if index < len(values) else None for index, column in enumerate(columns)}]
    return []


def segmentation_payload_from_legacy(
    legacy_payload: dict[str, Any], start: str | None = None, end: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "measures": [_normalize_custom_measure(measure) for measure in legacy_payload.get("measures", [])],
        "from_date": start or legacy_payload.get("from_date"),
        "to_date": end or legacy_payload.get("to_date"),
        "unit": str(legacy_payload.get("unit", "day")).upper(),
        "by_fields": _strip_ui_only(legacy_payload.get("by_fields", [])),
        "filter": _strip_ui_only(legacy_payload.get("filter", {})),
        "sampling_factor": legacy_payload.get("sampling_factor", 64),
        "rollup": True,
        "detail_and_rollup": legacy_payload.get("detail_and_rollup", True),
    }
    for key in ("approx", "bucket_params", "time_zone_mode", "server_time_zone", "arith_rollup"):
        if key in legacy_payload:
            payload[key] = _strip_ui_only(legacy_payload[key])
    return payload


def load_legacy_bookmark_payload(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    bookmark = raw.get("bookmark", raw)
    data = bookmark.get("data", bookmark)
    if isinstance(data, str):
        return json.loads(data)
    return data


def load_query_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def payload_with_dates(template: dict[str, Any], start: str | None, end: str | None) -> dict[str, Any]:
    payload = json.loads(json.dumps(template, ensure_ascii=False))
    if start:
        payload["from_date"] = start
    if end:
        payload["to_date"] = end
    return payload


def command_funnel_from_bookmark(settings: OpenAPISettings, args: argparse.Namespace) -> int:
    output_dir = DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    legacy_payload = load_legacy_bookmark_payload(Path(args.bookmark_json))
    payload = funnel_payload_from_legacy(legacy_payload, args.start, args.end)
    try:
        report = request_json(settings, "/api/v3/analytics/v1/model/funnel/report", payload)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1

    target = output_dir / args.output
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)
    return 0


def command_query_from_config(settings: OpenAPISettings, args: argparse.Namespace) -> int:
    output_dir = DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_query_config(Path(args.config))
    query = config["queries"].get(args.role)
    if not query:
        raise SystemExit(f"Unknown query role: {args.role}")
    if "payload_template" not in query:
        raise SystemExit(f"Query role {args.role} is not migrated yet: {query.get('migration_status', query.get('type'))}")

    payload = payload_with_dates(query["payload_template"], args.start, args.end)
    try:
        report = request_json(settings, query["openapi_path"], payload)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1

    target = output_dir / args.output
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sensors OpenAPI helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    funnel_parser = subparsers.add_parser("funnel-from-bookmark", help="Run OpenAPI funnel report from a saved bookmark JSON")
    funnel_parser.add_argument("--bookmark-json", required=True, help="Path to saved bookmark JSON")
    funnel_parser.add_argument("--start", help="Start date, YYYY-MM-DD")
    funnel_parser.add_argument("--end", help="End date, YYYY-MM-DD")
    funnel_parser.add_argument("--output", default="funnel_report.json")
    funnel_parser.set_defaults(func=command_funnel_from_bookmark)

    config_parser = subparsers.add_parser("query-from-config", help="Run a migrated OpenAPI query by role")
    config_parser.add_argument("--role", required=True, help="Query role, for example main_funnel")
    config_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    config_parser.add_argument("--start", help="Start date, YYYY-MM-DD")
    config_parser.add_argument("--end", help="End date, YYYY-MM-DD")
    config_parser.add_argument("--output", default="query_report.json")
    config_parser.set_defaults(func=command_query_from_config)
    return parser


def main() -> int:
    load_dotenv(ROOT / ".env")
    settings = OpenAPISettings.from_env()
    args = build_parser().parse_args()
    return args.func(settings, args)


if __name__ == "__main__":
    raise SystemExit(main())
