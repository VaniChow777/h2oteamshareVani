#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an integrated WebOB funnel diagnosis across member pay, first upsell, and second upsell."
    )
    parser.add_argument("--project", help="Project/all_product_name, such as bend, yoga, dance, muscle, walkup.")
    parser.add_argument("--funnels", help="Comma-separated funnel IDs for --project, such as 73,288.")
    parser.add_argument("--targets", nargs="+", help="One or more project:funnel_ids targets, such as bend:73,288 yoga:101,102.")
    parser.add_argument(
        "--target-periods",
        nargs="+",
        help="Targets with their own windows: project:funnel_ids:start:end[:label].",
    )
    parser.add_argument("--start", help="Start date YYYY-MM-DD.")
    parser.add_argument("--end", help="End date YYYY-MM-DD.")
    parser.add_argument("--period-label", help="Display label for this date window.")
    parser.add_argument("--countries", help="Comma-separated country values to filter. Defaults to all countries.")
    parser.add_argument("--country-field", default="event.$Anything.$country", help="Sensors field used for country filtering.")
    parser.add_argument("--output-dir", default="output", help="Directory for integrated outputs.")
    parser.add_argument("--top-skus", type=int, default=8)
    parser.add_argument("--baseline-index", type=int, default=1, help="1-based row index used as the comparison baseline in the report.")
    parser.add_argument("--min-users", type=int, default=100, help="Sample-size warning threshold for OB users or page users.")
    parser.add_argument("--auth", choices=("openapi",), default="openapi", help="Sensors auth mode. Only OpenAPI/API Key is supported.")
    parser.add_argument("--debug-raw", action="store_true", help="Keep component raw JSON files.")
    return parser.parse_args()


def shared_target_args(args: argparse.Namespace, include_top_skus: bool = True) -> list[str]:
    result: list[str] = []
    if args.target_periods:
        result.append("--target-periods")
        result.extend(args.target_periods)
    elif args.targets:
        result.append("--targets")
        result.extend(args.targets)
        result.extend(["--start", args.start or "", "--end", args.end or ""])
    else:
        result.extend(["--project", args.project or "", "--funnels", args.funnels or "", "--start", args.start or "", "--end", args.end or ""])

    if args.period_label:
        result.extend(["--period-label", args.period_label])
    if args.countries:
        result.extend(["--countries", args.countries])
    if args.country_field:
        result.extend(["--country-field", args.country_field])
    if args.auth:
        result.extend(["--auth", args.auth])
    if include_top_skus:
        result.extend(["--top-skus", str(args.top_skus)])
    return result


def run_component(
    name: str,
    script_name: str,
    args: argparse.Namespace,
    output_dir: Path,
    include_top_skus: bool = True,
) -> dict[str, Path]:
    component_dir = output_dir / name
    component_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(SCRIPT_DIR / script_name), *shared_target_args(args, include_top_skus), "--output-dir", str(component_dir)]
    completed = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode:
        raise SystemExit(
            f"{name} component failed with exit code {completed.returncode}.\n"
            f"Command: {' '.join(cmd)}\n"
            f"stderr:\n{completed.stderr}\n"
            f"stdout:\n{completed.stdout[:4000]}"
        )
    paths = latest_component_paths(component_dir)
    if not args.debug_raw:
        for raw_path in component_dir.glob("*_raw.json"):
            raw_path.unlink(missing_ok=True)
    return paths


def latest_component_paths(component_dir: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    patterns = {
        "summary": "*_summary.tsv",
        "sku_detail": "*_sku_detail.tsv",
        "member_sku_detail": "*_member_sku_detail.tsv",
        "report": "*_report.md",
        "raw": "*_raw.json",
    }
    for key, pattern in patterns.items():
        matches = sorted(component_dir.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
        if matches:
            paths[key] = matches[0]
    if "summary" not in paths:
        raise SystemExit(f"No summary TSV was generated in {component_dir}.")
    return paths


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def f(row: dict[str, Any] | None, key: str) -> float:
    if not row:
        return 0.0
    value = row.get(key, 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def s(row: dict[str, Any] | None, key: str) -> str:
    return str(row.get(key, "")) if row else ""


def pct(numerator: float, denominator: float) -> float:
    return numerator / denominator * 100 if denominator else 0.0


def rel_delta(value: float, baseline: float) -> float:
    return (value - baseline) / baseline * 100 if baseline else 0.0


def money(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def index_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["target_key"]: row for row in rows if row.get("target_key")}


def combined_rows(
    member_rows: list[dict[str, str]],
    first_rows: list[dict[str, str]],
    second_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    first_by_key = index_rows(first_rows)
    second_by_key = index_rows(second_rows)
    result: list[dict[str, Any]] = []
    for member in member_rows:
        key = member["target_key"]
        first = first_by_key.get(key)
        second = second_by_key.get(key)
        ob_users = f(member, "ob_users")
        member_pay_users = f(member, "member_pay_users")
        member_revenue = f(member, "estimated_revenue")
        first_revenue = f(first, "estimated_revenue")
        second_revenue = f(second, "estimated_revenue")
        total_revenue = member_revenue + first_revenue + second_revenue
        all_upsell_revenue = first_revenue + second_revenue
        result.append(
            {
                "target_key": key,
                "period": s(member, "period"),
                "countries": s(member, "countries"),
                "project": s(member, "project"),
                "funnel": s(member, "funnel"),
                "funnel_id": s(member, "funnel_id"),
                "ob_users": int(ob_users),
                "member_page_users": int(f(member, "member_page_users")),
                "member_submit_users": int(f(member, "member_submit_users")),
                "member_pay_users": int(member_pay_users),
                "penetration_rate": f(member, "penetration_rate"),
                "member_product_page_pay_rate": f(member, "product_page_pay_rate"),
                "member_authorization_rate": f(member, "overall_pay_rate"),
                "member_revenue": round(member_revenue, 2),
                "member_arpu_by_ob_user": f(member, "member_arpu_by_ob_user"),
                "member_arppu_by_pay_user": f(member, "member_arppu_by_pay_user"),
                "first_upsell_page_users": int(f(first, "page_users")),
                "first_upsell_pay_users": int(f(first, "pay_users")),
                "first_upsell_rate": f(first, "overall_pay_rate"),
                "first_upsell_revenue": round(first_revenue, 2),
                "first_upsell_arpu_by_page_user": f(first, "arpu_by_page_user"),
                "second_upsell_page_users": int(f(second, "page_users")),
                "second_upsell_pay_users": int(f(second, "pay_users")),
                "second_upsell_rate": f(second, "overall_pay_rate"),
                "second_upsell_revenue": round(second_revenue, 2),
                "second_upsell_arpu_by_page_user": f(second, "arpu_by_page_user"),
                "all_upsell_revenue": round(all_upsell_revenue, 2),
                "total_revenue": round(total_revenue, 2),
                "all_upsell_arpu_by_ob_user": round(all_upsell_revenue / ob_users, 4) if ob_users else 0.0,
                "member_plus_all_upsell_arpu_by_ob_user": round(total_revenue / ob_users, 4) if ob_users else 0.0,
                "all_upsell_arppu_by_authorized_user": round(all_upsell_revenue / member_pay_users, 4) if member_pay_users else 0.0,
                "member_plus_all_upsell_arppu_by_authorized_user": round(total_revenue / member_pay_users, 4) if member_pay_users else 0.0,
            }
        )
    return result


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def strongest_gap(row: dict[str, Any], baseline: dict[str, Any]) -> str:
    checks = [
        ("OB规模", pct(row["ob_users"] - baseline["ob_users"], baseline["ob_users"]), "rel_pct"),
        ("渗透率", row["penetration_rate"] - baseline["penetration_rate"], "pp"),
        ("会员商品页付费率", row["member_product_page_pay_rate"] - baseline["member_product_page_pay_rate"], "pp"),
        ("会员ARPU/OB", row["member_arpu_by_ob_user"] - baseline["member_arpu_by_ob_user"], "money4"),
        ("一级增值ARPU/page", row["first_upsell_arpu_by_page_user"] - baseline["first_upsell_arpu_by_page_user"], "money4"),
        ("二级增值ARPU/page", row["second_upsell_arpu_by_page_user"] - baseline["second_upsell_arpu_by_page_user"], "money4"),
        (
            "授权用户总价值",
            row["member_plus_all_upsell_arppu_by_authorized_user"] - baseline["member_plus_all_upsell_arppu_by_authorized_user"],
            "money2",
        ),
    ]
    if not checks:
        return "样本不足"
    name, delta, unit = max(checks, key=lambda item: abs(item[1]))
    if abs(delta) < 0.0001:
        return "整体接近"
    direction = "更高" if delta > 0 else "更低"
    if unit == "pp":
        suffix = f"{abs(delta):.2f}pp"
    elif unit == "rel_pct":
        suffix = f"{abs(delta):.1f}%"
    elif unit == "money4":
        suffix = f"{abs(delta):.4f}"
    else:
        suffix = f"{abs(delta):.2f}"
    return f"{name}{direction} {suffix}"


def sku_label(sku: str) -> str:
    parts = str(sku).split("_")
    return parts[-1] if parts else str(sku)


def sku_price(row: dict[str, str]) -> float | None:
    raw = row.get("sku_price_from_id")
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None


def summarize_sku_rows(rows: list[dict[str, str]], pay_col: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        key = row.get("target_key")
        if key:
            grouped.setdefault(key, []).append(row)

    summaries: dict[str, dict[str, Any]] = {}
    for key, items in grouped.items():
        sorted_by_revenue = sorted(items, key=lambda item: f(item, "estimated_revenue"), reverse=True)
        sorted_by_pay = sorted(items, key=lambda item: f(item, pay_col), reverse=True)
        top_revenue = sorted_by_revenue[0] if sorted_by_revenue else {}
        top_pay = sorted_by_pay[0] if sorted_by_pay else {}
        low_price_pay_mix = 0.0
        zero_price_pay_mix = 0.0
        for item in items:
            price = sku_price(item)
            pay_mix = f(item, "pay_mix")
            if price is not None and price <= 1:
                low_price_pay_mix += pay_mix
            if price == 0:
                zero_price_pay_mix += pay_mix
        summaries[key] = {
            "top_revenue_sku": sku_label(s(top_revenue, "sku")),
            "top_revenue_mix": f(top_revenue, "revenue_mix"),
            "top_pay_sku": sku_label(s(top_pay, "sku")),
            "top_pay_mix": f(top_pay, "pay_mix"),
            "low_price_pay_mix": low_price_pay_mix,
            "zero_price_pay_mix": zero_price_pay_mix,
            "sku_count": len(items),
        }
    return summaries


def load_sku_summaries(component_paths: dict[str, dict[str, Path]]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    member_path = component_paths["member"].get("member_sku_detail") or component_paths["member"].get("sku_detail")
    if member_path:
        result["member"] = summarize_sku_rows(read_tsv(member_path), "member_pay_users")
    first_path = component_paths["first_upsell"].get("sku_detail")
    if first_path:
        result["first_upsell"] = summarize_sku_rows(read_tsv(first_path), "pay_users")
    second_path = component_paths["second_upsell"].get("sku_detail")
    if second_path:
        result["second_upsell"] = summarize_sku_rows(read_tsv(second_path), "pay_users")
    return result


def compare_phrase(value: float, baseline: float, label: str, unit: str = "") -> str:
    delta = value - baseline
    direction = "高" if delta > 0 else "低"
    if unit == "pp":
        return f"{label}{direction}{abs(delta):.2f}pp"
    if unit == "rel":
        return f"{label}{direction}{abs(rel_delta(value, baseline)):.1f}%"
    return f"{label}{direction}{abs(delta):.4f}"


def primary_diagnosis(row: dict[str, Any], baseline: dict[str, Any]) -> str:
    if row["target_key"] == baseline["target_key"]:
        return "基准样本，用作对照。"
    total_delta = row["member_plus_all_upsell_arpu_by_ob_user"] - baseline["member_plus_all_upsell_arpu_by_ob_user"]
    factors = [
        (abs(row["penetration_rate"] - baseline["penetration_rate"]), compare_phrase(row["penetration_rate"], baseline["penetration_rate"], "渗透率", "pp")),
        (
            abs(row["member_product_page_pay_rate"] - baseline["member_product_page_pay_rate"]),
            compare_phrase(row["member_product_page_pay_rate"], baseline["member_product_page_pay_rate"], "会员商品页付费率", "pp"),
        ),
        (
            abs(row["first_upsell_arpu_by_page_user"] - baseline["first_upsell_arpu_by_page_user"]) * 100,
            compare_phrase(row["first_upsell_arpu_by_page_user"], baseline["first_upsell_arpu_by_page_user"], "一级增值ARPU/page"),
        ),
        (
            abs(row["second_upsell_arpu_by_page_user"] - baseline["second_upsell_arpu_by_page_user"]) * 100,
            compare_phrase(row["second_upsell_arpu_by_page_user"], baseline["second_upsell_arpu_by_page_user"], "二级增值ARPU/page"),
        ),
        (
            abs(row["member_plus_all_upsell_arppu_by_authorized_user"] - baseline["member_plus_all_upsell_arppu_by_authorized_user"]),
            compare_phrase(row["member_plus_all_upsell_arppu_by_authorized_user"], baseline["member_plus_all_upsell_arppu_by_authorized_user"], "授权用户总价值"),
        ),
    ]
    strongest = max(factors, key=lambda item: item[0])[1]
    direction = "更强" if total_delta > 0 else "更弱"
    return f"总ARPU/OB {direction} {abs(total_delta):.4f}，最明显差异是{strongest}。"


def issue_tags(row: dict[str, Any], min_users: int) -> list[str]:
    tags: list[str] = []
    component_min_users = max(30, min_users // 2)
    if row["ob_users"] < min_users:
        tags.append("样本量偏小")
    if row["penetration_rate"] < 5:
        tags.append("渗透率偏低")
    if row["member_product_page_pay_rate"] < 5:
        tags.append("会员商品页付费效率偏低")
    if row["member_authorization_rate"] < 0.5:
        tags.append("授权率偏低")
    if row["first_upsell_page_users"] and row["first_upsell_page_users"] < component_min_users:
        tags.append("一级增值样本偏小")
    if row["second_upsell_page_users"] and row["second_upsell_page_users"] < component_min_users:
        tags.append("二级增值样本偏小")
    if row["all_upsell_arppu_by_authorized_user"] <= 0:
        tags.append("增值未回收")
    if not tags:
        tags.append("无明显单点异常")
    return tags


def write_report(
    path: Path,
    rows: list[dict[str, Any]],
    component_paths: dict[str, dict[str, Path]],
    baseline_index: int,
    min_users: int,
) -> None:
    lines: list[str] = ["# WebOB Funnel Integrated Diagnosis", ""]
    if not rows:
        lines.append("No data was generated.")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    best = max(rows, key=lambda row: row["member_plus_all_upsell_arpu_by_ob_user"])
    baseline = rows[max(0, min(baseline_index - 1, len(rows) - 1))]
    sku_summaries = load_sku_summaries(component_paths)
    if best["target_key"] == baseline["target_key"] and len(rows) > 1:
        runner_up = max(
            [row for row in rows if row["target_key"] != best["target_key"]],
            key=lambda row: row["member_plus_all_upsell_arpu_by_ob_user"],
        )
        best_lift = rel_delta(best["member_plus_all_upsell_arpu_by_ob_user"], runner_up["member_plus_all_upsell_arpu_by_ob_user"])
        comparison = f"领先第二名 {runner_up['project']} {runner_up['funnel']} {best_lift:.1f}%"
    elif best["target_key"] == baseline["target_key"]:
        comparison = "当前只有一个目标，需补充对照组判断优劣"
    else:
        best_lift = rel_delta(best["member_plus_all_upsell_arpu_by_ob_user"], baseline["member_plus_all_upsell_arpu_by_ob_user"])
        comparison = f"相对基准 {baseline['project']} {baseline['funnel']} 为 {best_lift:+.1f}%"
    lines.append(
        f"一句话结论：按会员+一级增值+二级增值总 ARPU/OB 看，"
        f"{best['project']} {best['funnel']} 当前最高，为 {best['member_plus_all_upsell_arpu_by_ob_user']:.4f}；{comparison}。"
    )
    lines.extend(["", "## 核心归因", ""])
    for row in rows:
        tags = "、".join(issue_tags(row, min_users))
        lines.append(f"- {row['project']} {row['funnel']}: {primary_diagnosis(row, baseline)} 标签：{tags}。")

    lines.extend(["", "## 统一指标表", ""])
    lines.append(
        "| period | project | funnel | OB用户 | 渗透率 | 会员商品页付费率 | 授权率 | 会员ARPU/OB | 一级增值率 | 一级增值ARPU/page | 二级增值率 | 二级增值ARPU/page | 会员+增值ARPU/OB | 会员+增值ARPPU/授权 | 诊断 |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in rows:
        judgment = "基准" if row["target_key"] == baseline["target_key"] else strongest_gap(row, baseline)
        lines.append(
            "| {period} | {project} | {funnel} | {ob_users} | {penetration_rate:.2f}% | {member_product_page_pay_rate:.2f}% | {member_authorization_rate:.2f}% | {member_arpu_by_ob_user:.4f} | {first_upsell_rate:.2f}% | {first_upsell_arpu_by_page_user:.4f} | {second_upsell_rate:.2f}% | {second_upsell_arpu_by_page_user:.4f} | {member_plus_all_upsell_arpu_by_ob_user:.4f} | {member_plus_all_upsell_arppu_by_authorized_user:.2f} | {judgment} |".format(
                judgment=judgment, **row
            )
        )

    lines.extend(["", "## SKU 结构摘要", ""])
    for row in rows:
        key = row["target_key"]
        parts: list[str] = []
        for label, source in (("会员", "member"), ("一级增值", "first_upsell"), ("二级增值", "second_upsell")):
            summary = sku_summaries.get(source, {}).get(key)
            if not summary:
                continue
            low_price = f"，低价/0价支付占比 {summary['low_price_pay_mix']:.1f}%" if summary["low_price_pay_mix"] else ""
            parts.append(
                f"{label}收入主SKU {summary['top_revenue_sku']}，收入占比 {summary['top_revenue_mix']:.1f}%"
                f"，支付主SKU {summary['top_pay_sku']}，支付占比 {summary['top_pay_mix']:.1f}%{low_price}"
            )
        lines.append(f"- {row['project']} {row['funnel']}: " + "；".join(parts) + "。")

    lines.extend(["", "## 风险与下一步", ""])
    for row in rows:
        next_steps: list[str] = []
        if row["penetration_rate"] < baseline["penetration_rate"]:
            next_steps.append("检查 OB 到会员页曝光、国家/流量源 mix、前序页面跳转")
        if row["member_product_page_pay_rate"] < baseline["member_product_page_pay_rate"]:
            next_steps.append("检查会员页价格展示、SKU 默认选择、支付按钮与页面性能")
        if row["second_upsell_arpu_by_page_user"] < baseline["second_upsell_arpu_by_page_user"]:
            next_steps.append("检查二级增值 SKU 价格/收入结构、低价路径和页面承接")
        if row["member_plus_all_upsell_arppu_by_authorized_user"] < baseline["member_plus_all_upsell_arppu_by_authorized_user"]:
            next_steps.append("验证授权用户后续 LTV、退款、续费和增值回收")
        if not next_steps:
            next_steps.append("保持当前策略，继续用更长周期验证 LTV、退款和续费")
        lines.append(f"- {row['project']} {row['funnel']}: " + "；".join(next_steps) + "。")

    lines.extend(["", "## 生成文件", ""])
    lines.append(f"- integrated summary: `{path.with_name('webob_funnel_integrated_summary.tsv')}`")
    for name, paths in component_paths.items():
        report = paths.get("report")
        summary = paths.get("summary")
        if report and summary:
            lines.append(f"- {name}: `{summary}` / `{report}`")
    lines.append("")
    lines.append(
        "Note: 会员和增值 revenue/ARPU 由 funnel-level SKU paid users 乘以同周期项目级 SKU realized average revenue/order 估算，因为 purchase events 通常不携带 funnel_id。"
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    component_paths = {
        "member": run_component("member", "compare_penetration_pay.py", args, output_dir, include_top_skus=False),
        "first_upsell": run_component("first_upsell", "compare_first_upsell.py", args, output_dir),
        "second_upsell": run_component("second_upsell", "compare_second_upsell.py", args, output_dir),
    }
    member_rows = read_tsv(component_paths["member"]["summary"])
    first_rows = read_tsv(component_paths["first_upsell"]["summary"])
    second_rows = read_tsv(component_paths["second_upsell"]["summary"])
    rows = combined_rows(member_rows, first_rows, second_rows)

    summary_path = output_dir / "webob_funnel_integrated_summary.tsv"
    report_path = output_dir / "webob_funnel_diagnosis_report.md"
    manifest_path = output_dir / "webob_funnel_diagnosis_manifest.json"
    write_tsv(summary_path, rows)
    write_report(report_path, rows, component_paths, args.baseline_index, args.min_users)
    manifest_path.write_text(
        json.dumps(
            {
                "summary": str(summary_path),
                "report": str(report_path),
                "components": {name: {key: str(value) for key, value in paths.items()} for name, paths in component_paths.items()},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(report_path)
    print(summary_path)
    print(manifest_path)
    print(report_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
