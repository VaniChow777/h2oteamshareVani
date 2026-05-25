#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
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
DEFAULT_PENETRATION_BOOKMARK_ID = 23211
DEFAULT_REVENUE_BOOKMARK_ID = 23217


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare WebOB penetration and member pay rates by funnel ID.")
    parser.add_argument("--project", help="Project/all_product_name label, such as bend, yoga, dance, muscle, walkup.")
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
    parser.add_argument("--penetration-bookmark-id", type=int, default=DEFAULT_PENETRATION_BOOKMARK_ID)
    parser.add_argument("--revenue-bookmark-id", type=int, default=DEFAULT_REVENUE_BOOKMARK_ID)
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
    payload["by_fields"] = ["event.onboard_pageview_wf_h2o.funnel_id"]
    payload["by_field_steps"] = [0]
    payload["unit"] = "day"
    payload["state"] = "trends"
    report = funnel_report(settings, bookmark["id"], payload)

    result: dict[str, dict[str, int]] = {}
    for row in report.get("table_data", {}).get("cells", []):
        if row.get("event.onboard_pageview_wf_h2o.$time"):
            continue
        funnel_id = str(row.get("event.onboard_pageview_wf_h2o.funnel_id") or "")
        if funnel_id in funnel_ids:
            result[funnel_id] = {
                "ob_users": int(float(row.get("step_1.user_count") or 0)),
                "member_page_users": int(float(row.get("step_2.user_count") or 0)),
                "member_submit_users": int(float(row.get("step_3.user_count") or 0)),
                "member_pay_users": int(float(row.get("step_fold.user_count") or row.get("step_4.user_count") or 0)),
            }
    return result


def member_sku_payment_counts(
    settings: Settings,
    bookmark: dict[str, Any],
    dashboard_id: int,
    start: str,
    end: str,
    funnel_ids: set[str],
    countries: list[str],
    country_field: str,
) -> dict[tuple[str, str], int]:
    payload = funnel_payload(bookmark, dashboard_id, start, end)
    add_country_filter(payload, countries, country_field)
    payload["by_fields"] = [
        "event.onboard_pageview_wf_h2o.funnel_id",
        "event.purchase_yoga_dance.product_id_all_product",
    ]
    payload["by_field_steps"] = [0, 3]
    payload["unit"] = "day"
    payload["state"] = "trends"
    report = funnel_report(settings, bookmark["id"], payload)

    result: dict[tuple[str, str], int] = {}
    for row in report.get("table_data", {}).get("cells", []):
        funnel_id = str(row.get("event.onboard_pageview_wf_h2o.funnel_id") or "")
        sku = row.get("event.purchase_yoga_dance.product_id_all_product")
        if funnel_id not in funnel_ids or not sku or row.get("rollup_columns"):
            continue
        pay_users = int(float(row.get("step_fold.user_count") or row.get("step_4.user_count") or 0))
        if pay_users:
            result[(funnel_id, str(sku))] = pay_users
    return result


def sku_revenue_avg(
    settings: Settings,
    bookmark: dict[str, Any],
    dashboard_id: int,
    project: str,
    start: str,
    end: str,
    countries: list[str],
    country_field: str,
) -> dict[str, tuple[int, float, float]]:
    payload = events_payload(bookmark, dashboard_id, start, end)
    payload.update(
        {
            "by_fields": ["event.$Anything.product_id_all_product"],
            "filter": {
                "conditions": [
                    {"field": "event.$Anything.product_id_all_product", "function": "contain", "params": ["webob"]},
                    {"field": "event.$Anything.webob_product_type", "function": "equal", "params": ["会员"]},
                    {"field": "event.$Anything.all_product_name", "function": "equal", "params": [project]},
                ]
            },
            "measures": [
                {"event_name": "purchase_yoga_dance", "aggregator": "general", "name": "orders"},
                {
                    "event_name": "purchase_yoga_dance",
                    "aggregator": "SUM",
                    "name": "revenue",
                    "field": "event.purchase_yoga_dance.origin_money",
                },
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


def short_sku(sku: str) -> str:
    parts = sku.split("_")
    return parts[-1] if parts else sku


def write_report(path: Path, label: str, rows: list[dict[str, Any]], sku_rows: list[dict[str, Any]]) -> None:
    lines = [f"# WebOB Penetration And Pay Compare - {label}", ""]
    lines.append("| period | countries | project | funnel | OB users | member page users | submit users | pay users | penetration | product-page pay rate | page-submit rate | submit-pay rate | overall pay rate | est. revenue | ARPU/OB | ARPU/page | ARPPU |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        lines.append("| {period} | {countries} | {project} | {funnel} | {ob_users} | {member_page_users} | {member_submit_users} | {member_pay_users} | {penetration_rate:.2f}% | {product_page_pay_rate:.2f}% | {submit_rate:.2f}% | {pay_rate:.2f}% | {overall_pay_rate:.2f}% | {estimated_revenue:.2f} | {member_arpu_by_ob_user:.2f} | {member_arpu_by_page_user:.2f} | {member_arppu_by_pay_user:.2f} |".format(**row))
    lines.append("")
    lines.append("## Member Pay SKU Mix")
    lines.append("")
    for summary in rows:
        project = summary["project"]
        funnel = summary["funnel"]
        related = [row for row in sku_rows if row["target_key"] == summary["target_key"]]
        related.sort(key=lambda row: -float(row["member_pay_users"]))
        lines.extend(
            [
                f"### {summary['period']} {project} {funnel}",
                "",
                "| SKU | pay users | pay mix | SKU pay / page | SKU pay / submit | SKU pay / OB | avg revenue/order | est. revenue | ARPU/page contribution | revenue mix |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in related:
            lines.append(
                "| {sku_label} | {member_pay_users} | {pay_mix:.1f}% | {sku_product_page_pay_rate:.2f}% | {sku_pay_submit_rate:.2f}% | {sku_overall_pay_rate:.2f}% | {avg_revenue_per_order:.2f} | {estimated_revenue:.2f} | {sku_arpu_by_page_user:.2f} | {revenue_mix:.1f}% |".format(
                    sku_label=short_sku(row["sku"]), **row
                )
            )
        lines.append("")
    lines.append("Note: member revenue and ARPU are estimated from funnel-level member SKU paid users multiplied by same-period project-level member SKU realized average revenue/order, because purchase events usually do not carry funnel_id.")
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
    bookmark = get_bookmark(settings, args.dashboard_id, args.penetration_bookmark_id)
    revenue_bookmark = get_bookmark(settings, args.dashboard_id, args.revenue_bookmark_id)

    targets_by_window: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for target in targets:
        targets_by_window[(target["start"], target["end"])].append(target)

    rollups_by_key: dict[str, dict[str, int]] = {}
    sku_payments_by_key: dict[tuple[str, str], int] = {}
    avg_prices_by_project_window: dict[tuple[str, str, str], dict[str, tuple[int, float, float]]] = {}
    for (start, end), window_targets in targets_by_window.items():
        funnel_ids = {target["funnel_id"] for target in window_targets}
        rollups = funnel_rollups(settings, bookmark, args.dashboard_id, start, end, funnel_ids, countries, args.country_field)
        sku_payments = member_sku_payment_counts(settings, bookmark, args.dashboard_id, start, end, funnel_ids, countries, args.country_field)
        for target in window_targets:
            rollups_by_key[target["target_key"]] = rollups.get(target["funnel_id"], {"ob_users": 0, "member_page_users": 0, "member_submit_users": 0, "member_pay_users": 0})
        for target in window_targets:
            for (funnel_id, sku), pay_users in sku_payments.items():
                if funnel_id == target["funnel_id"]:
                    sku_payments_by_key[(target["target_key"], sku)] = pay_users
        for project in sorted({target["project"] for target in window_targets}):
            avg_prices_by_project_window[(project, start, end)] = sku_revenue_avg(settings, revenue_bookmark, args.dashboard_id, project, start, end, countries, args.country_field)

    rows: list[dict[str, Any]] = []
    targets_sorted = sorted(targets, key=lambda target: (target["project"], target["start"], target["end"], int(target["funnel_id"]) if target["funnel_id"].isdigit() else target["funnel_id"], target["target_key"]))
    for target in targets_sorted:
        project = target["project"]
        funnel_id = target["funnel_id"]
        counts = rollups_by_key.get(target["target_key"], {"ob_users": 0, "member_page_users": 0, "member_submit_users": 0, "member_pay_users": 0})
        ob_users = float(counts["ob_users"])
        member_page_users = float(counts["member_page_users"])
        member_submit_users = float(counts["member_submit_users"])
        member_pay_users = float(counts["member_pay_users"])
        rows.append(
            {
                "target_key": target["target_key"],
                "period": target["period"],
                "countries": countries_label,
                "start": target["start"],
                "end": target["end"],
                "project": project,
                "funnel": f"funnel{funnel_id}",
                "funnel_id": funnel_id,
                "ob_users": int(ob_users),
                "member_page_users": int(member_page_users),
                "member_submit_users": int(member_submit_users),
                "member_pay_users": int(member_pay_users),
                "penetration_rate": round(pct(member_page_users, ob_users), 4),
                "submit_rate": round(pct(member_submit_users, member_page_users), 4),
                "pay_rate": round(pct(member_pay_users, member_submit_users), 4),
                "product_page_pay_rate": round(pct(member_pay_users, member_page_users), 4),
                "overall_pay_rate": round(pct(member_pay_users, ob_users), 4),
                "estimated_revenue": 0.0,
                "member_arpu_by_ob_user": 0.0,
                "member_arpu_by_page_user": 0.0,
                "member_arppu_by_pay_user": 0.0,
            }
        )

    summary_by_key = {row["target_key"]: row for row in rows}
    sku_rows: list[dict[str, Any]] = []
    for (target_key, sku), pay_users in sorted(sku_payments_by_key.items(), key=lambda item: (summary_by_key[item[0][0]]["project"], summary_by_key[item[0][0]]["start"], int(summary_by_key[item[0][0]]["funnel_id"]) if str(summary_by_key[item[0][0]]["funnel_id"]).isdigit() else summary_by_key[item[0][0]]["funnel_id"], -item[1], item[0][1])):
        summary = summary_by_key[target_key]
        project = summary["project"]
        funnel_id = summary["funnel_id"]
        member_pay_users = float(summary["member_pay_users"])
        member_page_users = float(summary["member_page_users"])
        member_submit_users = float(summary["member_submit_users"])
        ob_users = float(summary["ob_users"])
        global_orders, global_revenue, avg_price = avg_prices_by_project_window[(project, summary["start"], summary["end"])].get(sku, (0, 0.0, 0.0))
        estimated_revenue = float(pay_users) * avg_price
        summary["estimated_revenue"] = round(float(summary["estimated_revenue"]) + estimated_revenue, 2)
        sku_rows.append(
            {
                "target_key": target_key,
                "period": summary["period"],
                "countries": countries_label,
                "start": summary["start"],
                "end": summary["end"],
                "project": project,
                "funnel": f"funnel{funnel_id}",
                "funnel_id": funnel_id,
                "sku": sku,
                "member_pay_users": pay_users,
                "global_orders": global_orders,
                "global_revenue": round(global_revenue, 2),
                "avg_revenue_per_order": round(avg_price, 4),
                "estimated_revenue": round(estimated_revenue, 2),
                "pay_mix": round(pct(float(pay_users), member_pay_users), 4),
                "sku_pay_submit_rate": round(pct(float(pay_users), member_submit_users), 4),
                "sku_overall_pay_rate": round(pct(float(pay_users), ob_users), 4),
                "revenue_mix": 0.0,
                "sku_product_page_pay_rate": round(pct(float(pay_users), member_page_users), 4),
                "sku_arpu_by_page_user": round(estimated_revenue / member_page_users, 4) if member_page_users else 0.0,
            }
        )

    for summary in rows:
        ob_users = float(summary["ob_users"])
        member_pay_users = float(summary["member_pay_users"])
        estimated_revenue = float(summary["estimated_revenue"])
        summary["member_arpu_by_ob_user"] = round(estimated_revenue / ob_users, 4) if ob_users else 0.0
        summary["member_arpu_by_page_user"] = round(estimated_revenue / float(summary["member_page_users"]), 4) if float(summary["member_page_users"]) else 0.0
        summary["member_arppu_by_pay_user"] = round(estimated_revenue / member_pay_users, 4) if member_pay_users else 0.0

    revenue_totals = {row["target_key"]: float(row["estimated_revenue"]) for row in rows}
    for row in sku_rows:
        row["revenue_mix"] = round(pct(float(row["estimated_revenue"]), revenue_totals.get(row["target_key"], 0.0)), 4)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target_slug = "_".join(f"{target['project']}-{target['funnel_id']}-{target['start']}_{target['end']}" for target in targets)
    country_slug = "all" if not countries else "country-" + "-".join(countries)
    stem = f"penetration_pay_{label}_{country_slug}_{target_slug}"
    summary_path = output_dir / f"{stem}_summary.tsv"
    sku_detail_path = output_dir / f"{stem}_member_sku_detail.tsv"
    report_path = output_dir / f"{stem}_report.md"
    raw_path = output_dir / f"{stem}_raw.json"

    write_tsv(summary_path, rows)
    write_tsv(sku_detail_path, sku_rows)
    write_report(report_path, label, rows, sku_rows)
    raw_path.write_text(json.dumps({"summary": rows, "member_sku_detail": sku_rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(report_path)
    print(summary_path)
    print(sku_detail_path)
    print(raw_path)
    print(report_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
