#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = SKILL_ROOT / "scripts" / "lib"
DEFAULT_SENSORS_ENV = Path.home() / ".codex-secrets" / "sensors" / "webob.env"
sys.path.insert(0, str(SCRIPT_ROOT))

from export_dashboard_funnels import dashboard_detail, funnel_payload, funnel_report
from sensors_api_tool import ROOT, Settings, load_dotenv


def load_sensors_env() -> None:
    code_env = os.environ.get("CODEX_SENSORS_ENV")
    if code_env:
        load_dotenv(Path(code_env).expanduser())
    load_dotenv(DEFAULT_SENSORS_ENV)
    load_dotenv(SKILL_ROOT / ".env")


DEFAULT_DASHBOARD_ID = 1522
DEFAULT_BOOKMARK_ID = 23211
PROJECT_FIELD = "event.onboard_pageview_wf_h2o.webfunnel_name"
FUNNEL_FIELD = "event.onboard_pageview_wf_h2o.funnel_id"
COUNTRY_FIELD = "event.$Anything.$country"
PAYMENT_FIELD = "event.submit_vip_order_yoga_dance_muscl_bend.purchase_type_all_product"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Break down WebOB member submit-pay changes by country and payment method.")
    parser.add_argument("--baseline-start", required=True, help="Baseline start date YYYY-MM-DD.")
    parser.add_argument("--baseline-end", required=True, help="Baseline end date YYYY-MM-DD.")
    parser.add_argument("--compare-start", required=True, help="Compare period start date YYYY-MM-DD.")
    parser.add_argument("--compare-end", required=True, help="Compare period end date YYYY-MM-DD.")
    parser.add_argument("--projects", help="Comma-separated project names, such as dance,muscle,walkup. Defaults to all projects.")
    parser.add_argument("--funnels", help="Comma-separated funnel IDs. When set, groups by project + funnel_id + dimension.")
    parser.add_argument("--countries", help="Optional country filter before breakdown.")
    parser.add_argument("--payment-methods", help="Optional payment method filter before breakdown, such as paypal,adyen.")
    parser.add_argument("--country-field", default=COUNTRY_FIELD)
    parser.add_argument("--payment-field", default=PAYMENT_FIELD)
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("--dashboard-id", type=int, default=DEFAULT_DASHBOARD_ID)
    parser.add_argument("--bookmark-id", type=int, default=DEFAULT_BOOKMARK_ID)
    parser.add_argument("--top", type=int, default=30, help="Rows per dimension to include in Markdown report.")
    parser.add_argument("--auth", choices=("openapi",), default="openapi", help="Sensors auth mode. Only OpenAPI/API Key is supported.")
    return parser.parse_args()


def split_csv(raw: str | None) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()] if raw else []


def validate_window(start: str, end: str) -> int:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if end_date < start_date:
        raise SystemExit(f"End date {end} must be >= start date {start}.")
    return (end_date - start_date).days + 1


def pct(numerator: float, denominator: float) -> float:
    return numerator / denominator * 100 if denominator else 0.0


def add_filter(payload: dict[str, Any], field: str, values: list[str]) -> None:
    if not values:
        return
    function = "equal" if len(values) == 1 else "in"
    payload.setdefault("filter", {}).setdefault("conditions", []).append(
        {"field": field, "function": function, "params": values}
    )


def get_bookmark(settings: Settings, dashboard_id: int, bookmark_id: int) -> dict[str, Any]:
    detail = dashboard_detail(settings, dashboard_id)
    for item in detail.get("items", []):
        bookmark = item.get("bookmark")
        if bookmark and bookmark.get("id") == bookmark_id:
            return bookmark
    raise SystemExit(f"Bookmark {bookmark_id} not found in dashboard {dashboard_id}.")


def rollup(
    settings: Settings,
    bookmark: dict[str, Any],
    dashboard_id: int,
    start: str,
    end: str,
    dimension_field: str,
    dimension_step: int,
    projects: set[str],
    funnels: set[str],
    countries: list[str],
    payment_methods: list[str],
    country_field: str,
    payment_field: str,
) -> dict[tuple[str, str, str], dict[str, float]]:
    payload = funnel_payload(bookmark, dashboard_id, start, end)
    by_fields = [PROJECT_FIELD]
    by_steps = [0]
    if funnels:
        by_fields.append(FUNNEL_FIELD)
        by_steps.append(0)
    by_fields.append(dimension_field)
    by_steps.append(dimension_step)
    payload["by_fields"] = by_fields
    payload["by_field_steps"] = by_steps
    payload["unit"] = "day"
    payload["state"] = "trends"
    add_filter(payload, country_field, countries)
    add_filter(payload, payment_field, payment_methods)
    report = funnel_report(settings, bookmark["id"], payload)

    out: dict[tuple[str, str, str], dict[str, float]] = {}
    for row in report.get("table_data", {}).get("cells", []):
        if row.get("event.onboard_pageview_wf_h2o.$time"):
            continue
        project = str(row.get(PROJECT_FIELD) or "").strip()
        if projects and project not in projects:
            continue
        funnel_id = str(row.get(FUNNEL_FIELD) or "").strip() if funnels else ""
        if funnels and funnel_id not in funnels:
            continue
        raw_value = row.get(dimension_field)
        value = str(raw_value if raw_value not in (None, "") else "(空)")
        page = float(row.get("step_2.user_count") or 0)
        submit = float(row.get("step_3.user_count") or 0)
        pay = float(row.get("step_fold.user_count") or row.get("step_4.user_count") or 0)
        out[(project, funnel_id, value)] = {
            "page": page,
            "submit": submit,
            "pay": pay,
            "submit_pay": pct(pay, submit),
        }
    return out


def compare_rows(
    baseline: dict[tuple[str, str, str], dict[str, float]],
    current: dict[tuple[str, str, str], dict[str, float]],
    baseline_days: int,
    compare_days: int,
) -> list[dict[str, Any]]:
    baseline_totals: dict[tuple[str, str], float] = {}
    current_totals: dict[tuple[str, str], float] = {}
    for project, funnel_id, _value in baseline:
        baseline_totals[(project, funnel_id)] = baseline_totals.get((project, funnel_id), 0.0) + baseline[(project, funnel_id, _value)]["submit"]
    for project, funnel_id, _value in current:
        current_totals[(project, funnel_id)] = current_totals.get((project, funnel_id), 0.0) + current[(project, funnel_id, _value)]["submit"]

    rows: list[dict[str, Any]] = []
    for project, funnel_id, value in sorted(set(baseline) | set(current)):
        prev = baseline.get((project, funnel_id, value), {})
        cur = current.get((project, funnel_id, value), {})
        prev_daily_submit = prev.get("submit", 0.0) / baseline_days
        cur_daily_submit = cur.get("submit", 0.0) / compare_days
        prev_daily_pay = prev.get("pay", 0.0) / baseline_days
        cur_daily_pay = cur.get("pay", 0.0) / compare_days
        prev_share = pct(prev.get("submit", 0.0), baseline_totals.get((project, funnel_id), 0.0))
        cur_share = pct(cur.get("submit", 0.0), current_totals.get((project, funnel_id), 0.0))
        rows.append(
            {
                "project": project,
                "funnel_id": funnel_id,
                "dimension_value": value,
                "baseline_submit": round(prev.get("submit", 0.0), 4),
                "compare_submit": round(cur.get("submit", 0.0), 4),
                "baseline_daily_submit": round(prev_daily_submit, 4),
                "compare_daily_submit": round(cur_daily_submit, 4),
                "daily_submit_delta": round(cur_daily_submit - prev_daily_submit, 4),
                "baseline_pay": round(prev.get("pay", 0.0), 4),
                "compare_pay": round(cur.get("pay", 0.0), 4),
                "baseline_daily_pay": round(prev_daily_pay, 4),
                "compare_daily_pay": round(cur_daily_pay, 4),
                "daily_pay_delta": round(cur_daily_pay - prev_daily_pay, 4),
                "baseline_submit_pay": round(prev.get("submit_pay", 0.0), 4),
                "compare_submit_pay": round(cur.get("submit_pay", 0.0), 4),
                "submit_pay_delta_pp": round(cur.get("submit_pay", 0.0) - prev.get("submit_pay", 0.0), 4),
                "baseline_submit_share": round(prev_share, 4),
                "compare_submit_share": round(cur_share, 4),
                "submit_share_delta_pp": round(cur_share - prev_share, 4),
            }
        )
    rows.sort(key=lambda row: (row["project"], row["funnel_id"], row["daily_pay_delta"], -row["compare_submit"]))
    return rows


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not rows:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, title: str, country_rows: list[dict[str, Any]], payment_rows: list[dict[str, Any]], top: int) -> None:
    lines = [f"# {title}", ""]
    for section, rows in (("Country", country_rows), ("Payment Method", payment_rows)):
        lines.extend(
            [
                f"## {section}",
                "",
                "| project | funnel | value | daily pay delta | submit-pay delta | submit share delta | compare submit |",
                "|---|---:|---|---:|---:|---:|---:|",
            ]
        )
        for row in rows[:top]:
            lines.append(
                "| {project} | {funnel_id} | {dimension_value} | {daily_pay_delta:.2f} | {submit_pay_delta_pp:.2f}pp | {submit_share_delta_pp:.2f}pp | {compare_submit:.0f} |".format(
                    **row
                )
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    baseline_days = validate_window(args.baseline_start, args.baseline_end)
    compare_days = validate_window(args.compare_start, args.compare_end)
    load_sensors_env()
    if args.auth:
        os.environ["SENSORS_AUTH_MODE"] = args.auth
    settings = Settings.from_env()
    bookmark = get_bookmark(settings, args.dashboard_id, args.bookmark_id)
    projects = set(split_csv(args.projects))
    funnels = set(split_csv(args.funnels))
    countries = split_csv(args.countries)
    payment_methods = split_csv(args.payment_methods)

    country_baseline = rollup(
        settings,
        bookmark,
        args.dashboard_id,
        args.baseline_start,
        args.baseline_end,
        args.country_field,
        0,
        projects,
        funnels,
        countries,
        payment_methods,
        args.country_field,
        args.payment_field,
    )
    country_current = rollup(
        settings,
        bookmark,
        args.dashboard_id,
        args.compare_start,
        args.compare_end,
        args.country_field,
        0,
        projects,
        funnels,
        countries,
        payment_methods,
        args.country_field,
        args.payment_field,
    )
    payment_baseline = rollup(
        settings,
        bookmark,
        args.dashboard_id,
        args.baseline_start,
        args.baseline_end,
        args.payment_field,
        2,
        projects,
        funnels,
        countries,
        payment_methods,
        args.country_field,
        args.payment_field,
    )
    payment_current = rollup(
        settings,
        bookmark,
        args.dashboard_id,
        args.compare_start,
        args.compare_end,
        args.payment_field,
        2,
        projects,
        funnels,
        countries,
        payment_methods,
        args.country_field,
        args.payment_field,
    )

    country_rows = compare_rows(country_baseline, country_current, baseline_days, compare_days)
    payment_rows = compare_rows(payment_baseline, payment_current, baseline_days, compare_days)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    country_path = output_dir / "submit_pay_by_country.tsv"
    payment_path = output_dir / "submit_pay_by_payment_method.tsv"
    report_path = output_dir / "submit_pay_breakdown_diagnosis.md"
    write_tsv(country_path, country_rows)
    write_tsv(payment_path, payment_rows)
    write_report(
        report_path,
        f"WebOB Submit-Pay Breakdown - {args.compare_start}~{args.compare_end} vs {args.baseline_start}~{args.baseline_end}",
        country_rows,
        payment_rows,
        args.top,
    )
    print(country_path.resolve())
    print(payment_path.resolve())
    print(report_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
