#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path("/Users/zhoumeng/Documents/Codex/2026-04-24/new-chat")
sys.path.insert(0, str(SCRIPT_ROOT))

from export_dashboard_funnels import dashboard_detail, events_payload, events_report, funnel_payload, funnel_report
from sensors_api_tool import ROOT, Settings, load_dotenv


DEFAULT_DASHBOARD_ID = 1522
DEFAULT_SECOND_UPSELL_BOOKMARK_ID = 23213
DEFAULT_REVENUE_BOOKMARK_ID = 23217


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare WebOB second-upsell funnels by conversion, ARPU, and SKU mix.")
    parser.add_argument("--project", help="Project/all_product_name, such as bend, yoga, dance, muscle, walkup.")
    parser.add_argument("--funnels", help="Comma-separated funnel IDs for --project, such as 73,288.")
    parser.add_argument("--targets", nargs="+", help="Targets such as bend:73,288 yoga:101,102.")
    parser.add_argument(
        "--target-periods",
        nargs="+",
        help="Targets with their own windows: project:funnel_ids:start:end[:label], such as bend:73:2026-05-01:2026-05-07:after.",
    )
    parser.add_argument("--start", help="Start date YYYY-MM-DD.")
    parser.add_argument("--end", help="End date YYYY-MM-DD.")
    parser.add_argument("--period-label", help="Display label for this date window.")
    parser.add_argument("--countries", help="Comma-separated country values to filter, such as US or United States. Defaults to all countries.")
    parser.add_argument("--country-field", default="event.$Anything.$country", help="Sensors field used for country filtering.")
    parser.add_argument("--output-dir", default=".", help="Directory for TSV/Markdown outputs.")
    parser.add_argument("--dashboard-id", type=int, default=DEFAULT_DASHBOARD_ID)
    parser.add_argument("--second-upsell-bookmark-id", type=int, default=DEFAULT_SECOND_UPSELL_BOOKMARK_ID)
    parser.add_argument("--revenue-bookmark-id", type=int, default=DEFAULT_REVENUE_BOOKMARK_ID)
    parser.add_argument("--top-skus", type=int, default=8)
    parser.add_argument("--auth", choices=("openapi",), default="openapi", help="Sensors auth mode. Only OpenAPI/API Key is supported.")
    return parser.parse_args()


def split_funnel_ids(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def split_csv(raw: str | None) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()] if raw else []


def add_country_filter(payload: dict[str, Any], countries: list[str], country_field: str) -> None:
    if not countries:
        return
    function = "equal" if len(countries) == 1 else "in"
    payload.setdefault("filter", {}).setdefault("conditions", []).append(
        {"field": country_field, "function": function, "params": countries}
    )


def parse_targets(args: argparse.Namespace) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    if args.target_periods:
        if args.targets or args.project or args.funnels:
            raise SystemExit("Use either --target-periods, --targets, or --project/--funnels; do not combine target modes.")
        for item in args.target_periods:
            parts = item.split(":", 4)
            if len(parts) < 4:
                raise SystemExit(f"Invalid --target-periods item {item!r}; expected project:funnel_ids:start:end[:label].")
            project, raw_funnels, start, end = [part.strip() for part in parts[:4]]
            label = parts[4].strip() if len(parts) == 5 and parts[4].strip() else f"{start}~{end}"
            if not project:
                raise SystemExit(f"Invalid --target-periods item {item!r}; project is empty.")
            validate_date_window(start, end)
            for funnel_id in split_funnel_ids(raw_funnels):
                targets.append({"project": project, "funnel_id": funnel_id, "start": start, "end": end, "period": label})
    elif args.targets:
        if not args.start or not args.end:
            raise SystemExit("--start and --end are required unless using --target-periods.")
        validate_date_window(args.start, args.end)
        for target in args.targets:
            if ":" not in target:
                raise SystemExit(f"Invalid --targets item {target!r}; expected project:funnel_id[,funnel_id].")
            project, raw_funnels = target.split(":", 1)
            project = project.strip()
            if not project:
                raise SystemExit(f"Invalid --targets item {target!r}; project is empty.")
            for funnel_id in split_funnel_ids(raw_funnels):
                targets.append({"project": project, "funnel_id": funnel_id, "start": args.start, "end": args.end, "period": args.period_label or f"{args.start}~{args.end}"})
    else:
        if not args.start or not args.end:
            raise SystemExit("--start and --end are required unless using --target-periods.")
        validate_date_window(args.start, args.end)
        if not args.project or not args.funnels:
            raise SystemExit("Pass either --targets project:funnel_ids... or both --project and --funnels.")
        for funnel_id in split_funnel_ids(args.funnels):
            targets.append({"project": args.project, "funnel_id": funnel_id, "start": args.start, "end": args.end, "period": args.period_label or f"{args.start}~{args.end}"})

    if not targets:
        raise SystemExit("No funnel targets provided.")

    seen: dict[tuple[str, str, str], str] = {}
    for target in targets:
        funnel_id = target["funnel_id"]
        project = target["project"]
        key = (funnel_id, target["start"], target["end"])
        if key in seen and seen[key] != project:
            raise SystemExit(f"Funnel ID {funnel_id} appears under multiple projects in the same date window and cannot be safely split.")
        seen[key] = project
    for index, target in enumerate(targets, start=1):
        target["target_key"] = f"{target['project']}|{target['funnel_id']}|{target['start']}|{target['end']}|{index}"
    return targets


def validate_date_window(start: str, end: str) -> None:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if end_date < start_date:
        raise SystemExit(f"End date {end} must be >= start date {start}.")


def money_from_sku(sku: str) -> float | None:
    matches = re.findall(r"-([0-9]+(?:\.[0-9]+)?)d\d+", sku)
    return float(matches[-1]) if matches else None


def short_sku(sku: str) -> str:
    parts = sku.split("_")
    return parts[-1] if parts else sku


def pct(numerator: float, denominator: float) -> float:
    return numerator / denominator * 100 if denominator else 0.0


def get_bookmark(settings: Settings, dashboard_id: int, bookmark_id: int) -> dict[str, Any]:
    detail = dashboard_detail(settings, dashboard_id)
    for item in detail.get("items", []):
        bookmark = item.get("bookmark")
        if bookmark and bookmark.get("id") == bookmark_id:
            return bookmark
    raise SystemExit(f"Bookmark {bookmark_id} not found in dashboard {dashboard_id}.")


def funnel_rollups(settings: Settings, bookmark: dict[str, Any], dashboard_id: int, start: str, end: str, funnel_ids: set[str], countries: list[str], country_field: str) -> dict[str, dict[str, int]]:
    payload = funnel_payload(bookmark, dashboard_id, start, end)
    add_country_filter(payload, countries, country_field)
    payload["by_fields"] = ["event.view_deal_detail_wf_h2o.funnel_id"]
    payload["by_field_steps"] = [0]
    payload["unit"] = "day"
    payload["state"] = "trends"
    report = funnel_report(settings, bookmark["id"], payload)

    result: dict[str, dict[str, int]] = {}
    for row in report.get("table_data", {}).get("cells", []):
        if row.get("event.view_deal_detail_wf_h2o.$time"):
            continue
        funnel_id = str(row.get("event.view_deal_detail_wf_h2o.funnel_id") or "")
        if funnel_id in funnel_ids:
            result[funnel_id] = {
                "page_users": int(float(row.get("step_1.user_count") or 0)),
                "submit_users": int(float(row.get("step_2.user_count") or 0)),
                "pay_users": int(float(row.get("step_fold.user_count") or row.get("step_3.user_count") or 0)),
            }
    return result


def sku_payment_counts(settings: Settings, bookmark: dict[str, Any], dashboard_id: int, start: str, end: str, funnel_ids: set[str], countries: list[str], country_field: str) -> dict[tuple[str, str], int]:
    payload = funnel_payload(bookmark, dashboard_id, start, end)
    add_country_filter(payload, countries, country_field)
    payload["by_fields"] = ["event.view_deal_detail_wf_h2o.funnel_id", "event.purchase_yoga_dance.product_id_all_product"]
    payload["by_field_steps"] = [0, 2]
    payload["unit"] = "day"
    payload["state"] = "trends"
    report = funnel_report(settings, bookmark["id"], payload)

    result: dict[tuple[str, str], int] = {}
    for row in report.get("table_data", {}).get("cells", []):
        funnel_id = str(row.get("event.view_deal_detail_wf_h2o.funnel_id") or "")
        sku = row.get("event.purchase_yoga_dance.product_id_all_product")
        if funnel_id not in funnel_ids or not sku or row.get("rollup_columns"):
            continue
        pay_users = int(float(row.get("step_fold.user_count") or row.get("step_3.user_count") or 0))
        if pay_users:
            result[(funnel_id, str(sku))] = pay_users
    return result


def sku_revenue_avg(settings: Settings, bookmark: dict[str, Any], dashboard_id: int, project: str, start: str, end: str, countries: list[str], country_field: str) -> dict[str, tuple[int, float, float]]:
    payload = events_payload(bookmark, dashboard_id, start, end)
    payload.update(
        {
            "by_fields": ["event.$Anything.product_id_all_product"],
            "filter": {
                "conditions": [
                    {"field": "event.$Anything.product_id_all_product", "function": "contain", "params": ["webob"]},
                    {"field": "event.$Anything.webob_product_type", "function": "equal", "params": ["增值"]},
                    {"field": "event.$Anything.webob_product_type_is_double_extra", "function": "equal", "params": ["二级增值"]},
                    {"field": "event.$Anything.all_product_name", "function": "equal", "params": [project]},
                ]
            },
            "measures": [
                {"event_name": "purchase_yoga_dance", "aggregator": "general", "name": "orders"},
                {"event_name": "purchase_yoga_dance", "aggregator": "SUM", "name": "revenue", "field": "event.purchase_yoga_dance.origin_money"},
            ],
        }
    )
    add_country_filter(payload, countries, country_field)
    report = events_report(settings, bookmark["id"], payload)

    result: dict[str, tuple[int, float, float]] = {}
    for row in report.get("rollup_result", {}).get("rows", []):
        if not row.get("by_values"):
            continue
        sku = row["by_values"][0]
        if not sku:
            continue
        orders, revenue = row.get("values", [[0, 0]])[0]
        orders = int(float(orders or 0))
        revenue = float(revenue or 0)
        result[str(sku)] = (orders, revenue, revenue / orders if orders else 0.0)
    return result


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, label: str, summary_rows: list[dict[str, Any]], detail_rows: list[dict[str, Any]], top_skus: int) -> None:
    lines = [f"# WebOB Second-Upsell Funnel Compare - {label}", ""]
    lines.append("| period | countries | project | funnel | page users | submit users | pay users | submit rate | pay rate | overall pay rate | est. revenue | ARPU | ARPPU |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in summary_rows:
        lines.append("| {period} | {countries} | {project} | {funnel} | {page_users} | {submit_users} | {pay_users} | {submit_rate:.2f}% | {pay_rate:.2f}% | {overall_pay_rate:.2f}% | {estimated_revenue:.2f} | {arpu_by_page_user:.2f} | {arppu_by_pay_user:.2f} |".format(**row))

    lines.extend(["", "## SKU Mix", ""])
    for summary in summary_rows:
        project = summary["project"]
        funnel = summary["funnel"]
        rows = [row for row in detail_rows if row["target_key"] == summary["target_key"]]
        rows.sort(key=lambda row: -float(row["estimated_revenue"]))
        lines.extend([f"### {summary['period']} {project} {funnel}", "", "| SKU | pay users | pay mix | avg revenue/order | est. revenue | revenue mix |", "|---|---:|---:|---:|---:|---:|"])
        for row in rows[:top_skus]:
            lines.append("| {sku_label} | {pay_users} | {pay_mix:.1f}% | {avg_revenue_per_order:.2f} | {estimated_revenue:.2f} | {revenue_mix:.1f}% |".format(sku_label=short_sku(row["sku"]), **row))
        lines.append("")

    lines.append("Note: revenue and ARPU are estimated from funnel-level SKU paid users multiplied by same-period project-level SKU realized average revenue/order, because purchase events usually do not carry funnel_id.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    targets = parse_targets(args)
    countries = split_csv(args.countries)
    countries_label = ",".join(countries) if countries else "ALL"
    labels = {target["period"] for target in targets}
    label = args.period_label or (next(iter(labels)) if len(labels) == 1 else "multi-period")
    load_dotenv(ROOT / ".env")
    if args.auth:
        os.environ["SENSORS_AUTH_MODE"] = args.auth
    settings = Settings.from_env()
    second_upsell = get_bookmark(settings, args.dashboard_id, args.second_upsell_bookmark_id)
    revenue_bookmark = get_bookmark(settings, args.dashboard_id, args.revenue_bookmark_id)

    targets_by_window: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for target in targets:
        targets_by_window[(target["start"], target["end"])].append(target)

    rollups_by_key: dict[str, dict[str, int]] = {}
    payments_by_key: dict[tuple[str, str], int] = {}
    avg_prices_by_project_window: dict[tuple[str, str, str], dict[str, tuple[int, float, float]]] = {}
    for (start, end), window_targets in targets_by_window.items():
        funnel_ids = {target["funnel_id"] for target in window_targets}
        rollups = funnel_rollups(settings, second_upsell, args.dashboard_id, start, end, funnel_ids, countries, args.country_field)
        payments = sku_payment_counts(settings, second_upsell, args.dashboard_id, start, end, funnel_ids, countries, args.country_field)
        for target in window_targets:
            rollups_by_key[target["target_key"]] = rollups.get(target["funnel_id"], {"page_users": 0, "submit_users": 0, "pay_users": 0})
            for (funnel_id, sku), pay_users in payments.items():
                if funnel_id == target["funnel_id"]:
                    payments_by_key[(target["target_key"], sku)] = pay_users
        for project in sorted({target["project"] for target in window_targets}):
            avg_prices_by_project_window[(project, start, end)] = sku_revenue_avg(settings, revenue_bookmark, args.dashboard_id, project, start, end, countries, args.country_field)

    detail_rows: list[dict[str, Any]] = []
    summary_totals: dict[str, dict[str, float]] = {}
    targets_sorted = sorted(targets, key=lambda target: (target["project"], target["start"], target["end"], int(target["funnel_id"]) if target["funnel_id"].isdigit() else target["funnel_id"], target["target_key"]))
    target_by_key = {target["target_key"]: target for target in targets_sorted}
    for target in targets_sorted:
        counts = rollups_by_key.get(target["target_key"], {"page_users": 0, "submit_users": 0, "pay_users": 0})
        summary_totals[target["target_key"]] = {"page_users": float(counts["page_users"]), "submit_users": float(counts["submit_users"]), "pay_users": float(counts["pay_users"]), "estimated_revenue": 0.0}

    for (target_key, sku), pay_users in payments_by_key.items():
        target = target_by_key[target_key]
        project = target["project"]
        funnel_id = target["funnel_id"]
        global_orders, global_revenue, avg_price = avg_prices_by_project_window[(project, target["start"], target["end"])].get(sku, (0, 0.0, money_from_sku(sku) or 0.0))
        estimated_revenue = pay_users * avg_price
        summary_totals[target_key]["estimated_revenue"] += estimated_revenue
        detail_rows.append({"target_key": target_key, "period": target["period"], "countries": countries_label, "start": target["start"], "end": target["end"], "project": project, "funnel": f"funnel{funnel_id}", "funnel_id": funnel_id, "sku": sku, "pay_users": pay_users, "global_orders": global_orders, "global_revenue": round(global_revenue, 2), "avg_revenue_per_order": round(avg_price, 4), "estimated_revenue": round(estimated_revenue, 2), "sku_price_from_id": money_from_sku(sku)})

    summary_rows: list[dict[str, Any]] = []
    for target_key, totals in summary_totals.items():
        target = target_by_key[target_key]
        project = target["project"]
        funnel_id = target["funnel_id"]
        page_users = totals["page_users"]
        submit_users = totals["submit_users"]
        pay_users = totals["pay_users"]
        revenue = totals["estimated_revenue"]
        summary_rows.append({"target_key": target_key, "period": target["period"], "countries": countries_label, "start": target["start"], "end": target["end"], "project": project, "funnel": f"funnel{funnel_id}", "funnel_id": funnel_id, "page_users": int(page_users), "submit_users": int(submit_users), "pay_users": int(pay_users), "submit_rate": round(pct(submit_users, page_users), 4), "pay_rate": round(pct(pay_users, submit_users), 4), "overall_pay_rate": round(pct(pay_users, page_users), 4), "estimated_revenue": round(revenue, 2), "arpu_by_page_user": round(revenue / page_users, 4) if page_users else 0.0, "arppu_by_pay_user": round(revenue / pay_users, 4) if pay_users else 0.0})

    pay_totals = {row["target_key"]: float(row["pay_users"]) for row in summary_rows}
    revenue_totals = {row["target_key"]: float(row["estimated_revenue"]) for row in summary_rows}
    for row in detail_rows:
        row["pay_mix"] = round(pct(float(row["pay_users"]), pay_totals.get(row["target_key"], 0.0)), 4)
        row["revenue_mix"] = round(pct(float(row["estimated_revenue"]), revenue_totals.get(row["target_key"], 0.0)), 4)

    detail_rows.sort(key=lambda row: (row["project"], row["start"], int(row["funnel_id"]) if str(row["funnel_id"]).isdigit() else str(row["funnel_id"]), -float(row["estimated_revenue"]), row["sku"]))
    summary_rows.sort(key=lambda row: (row["project"], row["start"], int(row["funnel_id"]) if str(row["funnel_id"]).isdigit() else str(row["funnel_id"])))

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target_slug = "_".join(f"{target['project']}-{target['funnel_id']}-{target['start']}_{target['end']}" for target in targets)
    country_slug = "all" if not countries else "country-" + "-".join(countries)
    stem = f"second_upsell_{label}_{country_slug}_{target_slug}"
    summary_path = output_dir / f"{stem}_summary.tsv"
    detail_path = output_dir / f"{stem}_sku_detail.tsv"
    report_path = output_dir / f"{stem}_report.md"
    raw_path = output_dir / f"{stem}_raw.json"

    write_tsv(summary_path, summary_rows)
    write_tsv(detail_path, detail_rows)
    write_report(report_path, label, summary_rows, detail_rows, args.top_skus)
    raw_path.write_text(json.dumps({"summary": summary_rows, "detail": detail_rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(report_path)
    print(summary_path)
    print(detail_path)
    print(raw_path)
    print(report_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
