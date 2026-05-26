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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose WebOB member payment chain changes.")
    parser.add_argument("--baseline-start", required=True, help="Baseline start date YYYY-MM-DD.")
    parser.add_argument("--baseline-end", required=True, help="Baseline end date YYYY-MM-DD.")
    parser.add_argument("--compare-start", required=True, help="Compare period start date YYYY-MM-DD.")
    parser.add_argument("--compare-end", required=True, help="Compare period end date YYYY-MM-DD.")
    parser.add_argument("--projects", help="Comma-separated project names, such as yoga,dance. Defaults to all projects.")
    parser.add_argument("--funnels", help="Comma-separated funnel IDs. When set, groups by project + funnel_id.")
    parser.add_argument("--countries", help="Comma-separated country filter. Defaults to all countries.")
    parser.add_argument("--country-field", default=COUNTRY_FIELD)
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("--dashboard-id", type=int, default=DEFAULT_DASHBOARD_ID)
    parser.add_argument("--bookmark-id", type=int, default=DEFAULT_BOOKMARK_ID)
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
    projects: set[str],
    funnels: set[str],
    countries: list[str],
    country_field: str,
) -> dict[tuple[str, str], dict[str, float]]:
    payload = funnel_payload(bookmark, dashboard_id, start, end)
    by_fields = [PROJECT_FIELD]
    by_steps = [0]
    if funnels:
        by_fields.append(FUNNEL_FIELD)
        by_steps.append(0)
    payload["by_fields"] = by_fields
    payload["by_field_steps"] = by_steps
    payload["unit"] = "day"
    payload["state"] = "trends"
    add_filter(payload, country_field, countries)
    report = funnel_report(settings, bookmark["id"], payload)

    out: dict[tuple[str, str], dict[str, float]] = {}
    for row in report.get("table_data", {}).get("cells", []):
        if row.get("event.onboard_pageview_wf_h2o.$time"):
            continue
        project = str(row.get(PROJECT_FIELD) or "").strip()
        if projects and project not in projects:
            continue
        funnel_id = str(row.get(FUNNEL_FIELD) or "").strip() if funnels else ""
        if funnels and funnel_id not in funnels:
            continue
        ob = float(row.get("step_1.user_count") or 0)
        page = float(row.get("step_2.user_count") or 0)
        submit = float(row.get("step_3.user_count") or 0)
        pay = float(row.get("step_fold.user_count") or row.get("step_4.user_count") or 0)
        out[(project, funnel_id)] = {
            "ob": ob,
            "page": page,
            "submit": submit,
            "pay": pay,
            "penetration": pct(page, ob),
            "page_submit": pct(submit, page),
            "submit_pay": pct(pay, submit),
            "page_pay": pct(pay, page),
            "auth": pct(pay, ob),
        }
    return out


def diagnose(prev: dict[str, float], cur: dict[str, float]) -> str:
    deltas = {
        "渗透": cur.get("penetration", 0.0) - prev.get("penetration", 0.0),
        "商品页-提交": cur.get("page_submit", 0.0) - prev.get("page_submit", 0.0),
        "提交-支付": cur.get("submit_pay", 0.0) - prev.get("submit_pay", 0.0),
    }
    worst_name, worst_delta = min(deltas.items(), key=lambda item: item[1])
    if worst_delta >= -2:
        return "基本稳定"
    return f"{worst_name}差"


def write_outputs(
    output_dir: Path,
    baseline_label: str,
    compare_label: str,
    baseline_days: int,
    compare_days: int,
    baseline: dict[tuple[str, str], dict[str, float]],
    current: dict[tuple[str, str], dict[str, float]],
) -> tuple[Path, Path]:
    rows: list[dict[str, Any]] = []
    for project, funnel_id in sorted(set(baseline) | set(current)):
        prev = baseline.get((project, funnel_id), {})
        cur = current.get((project, funnel_id), {})
        rows.append(
            {
                "project": project,
                "funnel_id": funnel_id,
                "baseline_ob": round(prev.get("ob", 0.0), 4),
                "compare_ob": round(cur.get("ob", 0.0), 4),
                "baseline_daily_pay": round(prev.get("pay", 0.0) / baseline_days, 4),
                "compare_daily_pay": round(cur.get("pay", 0.0) / compare_days, 4),
                "daily_pay_delta": round(cur.get("pay", 0.0) / compare_days - prev.get("pay", 0.0) / baseline_days, 4),
                "baseline_penetration": round(prev.get("penetration", 0.0), 4),
                "compare_penetration": round(cur.get("penetration", 0.0), 4),
                "penetration_delta_pp": round(cur.get("penetration", 0.0) - prev.get("penetration", 0.0), 4),
                "baseline_page_submit": round(prev.get("page_submit", 0.0), 4),
                "compare_page_submit": round(cur.get("page_submit", 0.0), 4),
                "page_submit_delta_pp": round(cur.get("page_submit", 0.0) - prev.get("page_submit", 0.0), 4),
                "baseline_submit_pay": round(prev.get("submit_pay", 0.0), 4),
                "compare_submit_pay": round(cur.get("submit_pay", 0.0), 4),
                "submit_pay_delta_pp": round(cur.get("submit_pay", 0.0) - prev.get("submit_pay", 0.0), 4),
                "baseline_page_pay": round(prev.get("page_pay", 0.0), 4),
                "compare_page_pay": round(cur.get("page_pay", 0.0), 4),
                "baseline_auth": round(prev.get("auth", 0.0), 4),
                "compare_auth": round(cur.get("auth", 0.0), 4),
                "diagnosis": diagnose(prev, cur),
            }
        )
    rows.sort(key=lambda row: row["daily_pay_delta"])

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "member_chain_diagnosis.tsv"
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    report_path = output_dir / "member_chain_diagnosis.md"
    lines = [
        f"# WebOB Member Chain Diagnosis - {compare_label} vs {baseline_label}",
        "",
        "| project | funnel | daily pay delta | penetration delta | page-submit delta | submit-pay delta | diagnosis |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows[:20]:
        lines.append(
            "| {project} | {funnel_id} | {daily_pay_delta:.2f} | {penetration_delta_pp:.2f}pp | {page_submit_delta_pp:.2f}pp | {submit_pay_delta_pp:.2f}pp | {diagnosis} |".format(
                **row
            )
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_path, report_path


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
    baseline = rollup(
        settings,
        bookmark,
        args.dashboard_id,
        args.baseline_start,
        args.baseline_end,
        projects,
        funnels,
        countries,
        args.country_field,
    )
    current = rollup(
        settings,
        bookmark,
        args.dashboard_id,
        args.compare_start,
        args.compare_end,
        projects,
        funnels,
        countries,
        args.country_field,
    )
    summary_path, report_path = write_outputs(
        Path(args.output_dir),
        f"{args.baseline_start}~{args.baseline_end}",
        f"{args.compare_start}~{args.compare_end}",
        baseline_days,
        compare_days,
        baseline,
        current,
    )
    print(summary_path.resolve())
    print(report_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
