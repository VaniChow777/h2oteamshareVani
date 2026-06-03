#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any


OPEN_BASE = "https://open.feishu.cn/open-apis"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def request_json(path_or_url: str, token: str | None = None, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = path_or_url if path_or_url.startswith("http") else f"{OPEN_BASE}{path_or_url}"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Feishu HTTP {exc.code}: {detail}") from exc
    result = json.loads(body)
    if result.get("code", 0) != 0:
        raise RuntimeError(f"Feishu API failed: code={result.get('code')} msg={result.get('msg')}")
    return result


def tenant_access_token() -> str:
    cached = os.environ.get("FEISHU_TENANT_ACCESS_TOKEN")
    if cached:
        return cached
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        raise SystemExit("Missing FEISHU_APP_ID/FEISHU_APP_SECRET in .env")
    result = request_json(
        "/auth/v3/tenant_access_token/internal",
        method="POST",
        payload={"app_id": app_id, "app_secret": app_secret},
    )
    token = result.get("tenant_access_token")
    if not token:
        raise RuntimeError("No tenant_access_token returned")
    return token


def wiki_token_from_url(url: str) -> str:
    match = re.search(r"/wiki/([^/?#]+)", url)
    if not match:
        raise ValueError("Cannot parse wiki token from FEISHU_BITABLE_URL")
    return match.group(1)


def bitable_app_token(token: str) -> str:
    explicit = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    if explicit:
        return explicit
    wiki_url = os.environ.get("FEISHU_BITABLE_URL", "")
    wiki_token = os.environ.get("FEISHU_WIKI_TOKEN") or wiki_token_from_url(wiki_url)
    result = request_json(f"/wiki/v2/spaces/get_node?token={urllib.parse.quote(wiki_token)}", token=token)
    node = result.get("data", {}).get("node", {})
    obj_token = node.get("obj_token")
    if not obj_token:
        raise RuntimeError("Cannot resolve bitable app token from wiki URL")
    return obj_token


def list_items(url: str, token: str, key: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token = ""
    while True:
        sep = "&" if "?" in url else "?"
        paged_url = url + (f"{sep}page_token={urllib.parse.quote(page_token)}" if page_token else "")
        result = request_json(paged_url, token=token)
        data = result.get("data", {})
        items.extend(data.get("items", []))
        if not data.get("has_more"):
            return items
        page_token = data.get("page_token") or ""


def table_id_by_name(token: str, app_token: str, table_name: str) -> str:
    tables = list_items(f"/bitable/v1/apps/{app_token}/tables?page_size=100", token, "items")
    for table in tables:
        if table.get("name") == table_name:
            return table["table_id"]
    raise RuntimeError(f"Cannot find Feishu bitable table: {table_name}")


def field_types(token: str, app_token: str, table_id: str) -> dict[str, int]:
    fields = list_items(f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields?page_size=100", token, "items")
    return {field["field_name"]: int(field.get("type", 1)) for field in fields}


def ensure_fields(token: str, app_token: str, table_id: str, field_names: list[str]) -> dict[str, int]:
    existing = field_types(token, app_token, table_id)
    for field_name in field_names:
        if field_name not in existing:
            request_json(
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
                token=token,
                method="POST",
                payload={"field_name": field_name, "type": 1},
            )
    return field_types(token, app_token, table_id)


def parse_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def date_to_ms(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return int(time.mktime(parsed.timetuple()) * 1000)


def coerce_value(value: str, field_type: int) -> Any:
    if value == "":
        return None
    if field_type == 5:
        return date_to_ms(value)
    if field_type == 2:
        if value.endswith("%"):
            return float(value[:-1]) / 100
        return float(value)
    return value


def coerce_record(row: dict[str, str], fields: dict[str, int]) -> dict[str, Any]:
    result = {}
    for key, value in row.items():
        if key in fields:
            result[key] = coerce_value(value, fields[key])
    return result


def record_pull_date(record: dict[str, Any]) -> str:
    value = record.get("fields", {}).get("拉取时间")
    if isinstance(value, int):
        return datetime.fromtimestamp(value / 1000).date().isoformat()
    return str(value or "")


def delete_existing_pull_date(token: str, app_token: str, table_id: str, pull_date: str) -> int:
    records = list_items(f"/bitable/v1/apps/{app_token}/tables/{table_id}/records?page_size=500", token, "items")
    record_ids = [record["record_id"] for record in records if record_pull_date(record) == pull_date]
    deleted = 0
    for index in range(0, len(record_ids), 500):
        chunk = record_ids[index : index + 500]
        if chunk:
            request_json(
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete",
                token=token,
                method="POST",
                payload={"records": chunk},
            )
            deleted += len(chunk)
    return deleted


def delete_empty_records(token: str, app_token: str, table_id: str) -> int:
    records = list_items(f"/bitable/v1/apps/{app_token}/tables/{table_id}/records?page_size=500", token, "items")
    record_ids = [record["record_id"] for record in records if not record.get("fields")]
    deleted = 0
    for index in range(0, len(record_ids), 500):
        chunk = record_ids[index : index + 500]
        if chunk:
            request_json(
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete",
                token=token,
                method="POST",
                payload={"records": chunk},
            )
            deleted += len(chunk)
    return deleted


def batch_create(token: str, app_token: str, table_id: str, rows: list[dict[str, Any]]) -> None:
    for index in range(0, len(rows), 500):
        chunk = rows[index : index + 500]
        request_json(
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
            token=token,
            method="POST",
            payload={"records": [{"fields": row} for row in chunk]},
        )


def sync_table(token: str, app_token: str, table_name: str, tsv_path: Path, cleanup_empty: bool = False) -> tuple[int, int, int]:
    rows = parse_tsv(tsv_path)
    if not rows:
        return 0, 0, 0
    pull_date = rows[0].get("拉取时间") or date.today().isoformat()
    table_id = table_id_by_name(token, app_token, table_name)
    fields = ensure_fields(token, app_token, table_id, list(rows[0].keys()))
    empty_deleted = delete_empty_records(token, app_token, table_id) if cleanup_empty else 0
    records = [coerce_record(row, fields) for row in rows]
    batch_create(token, app_token, table_id, records)
    return empty_deleted, 0, len(records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync WebOB TSV output to Feishu Bitable")
    parser.add_argument("--env", type=Path, help="Optional .env file with Feishu and Bitable credentials")
    parser.add_argument("--funnel", type=Path, required=True)
    parser.add_argument("--business", type=Path, required=True)
    parser.add_argument("--cleanup-empty", action="store_true", help="Delete empty records created before fields existed")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(args.env)
    load_dotenv(Path.cwd() / ".env")
    token = tenant_access_token()
    app_token = bitable_app_token(token)
    funnel_name = os.environ.get("FEISHU_FUNNEL_TABLE_NAME", "funnel数据")
    business_name = os.environ.get("FEISHU_BUSINESS_TABLE_NAME", "业务数据")

    funnel_empty_deleted, funnel_deleted, funnel_created = sync_table(
        token, app_token, funnel_name, args.funnel, cleanup_empty=args.cleanup_empty
    )
    business_empty_deleted, business_deleted, business_created = sync_table(
        token, app_token, business_name, args.business, cleanup_empty=args.cleanup_empty
    )
    print(f"feishu_funnel=empty_deleted:{funnel_empty_deleted},deleted:{funnel_deleted},created:{funnel_created}")
    print(f"feishu_business=empty_deleted:{business_empty_deleted},deleted:{business_deleted},created:{business_created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
