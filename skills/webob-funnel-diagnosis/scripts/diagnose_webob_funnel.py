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


def write_report(path: Path, rows: list[dict[str, Any]], component_paths: dict[str, dict[str, Path]]) -> None:
    lines: list[str] = ["# WebOB Funnel Integrated Diagnosis", ""]
    if not rows:
        lines.append("No data was generated.")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    best = max(rows, key=lambda row: row["member_plus_all_upsell_arpu_by_ob_user"])
    baseline = rows[0]
    lines.append(
        f"一句话结论：按会员+一级增值+二级增值总 ARPU/OB 看，"
        f"{best['project']} {best['funnel']} 当前最高，为 {best['member_plus_all_upsell_arpu_by_ob_user']:.4f}。"
    )
    lines.extend(["", "## 统一指标表", ""])
    lines.append(
        "| period | project | funnel | OB用户 | 渗透率 | 会员商品页付费率 | 授权率 | 会员ARPU/OB | 一级增值率 | 一级增值ARPU/page | 二级增值率 | 二级增值ARPU/page | 会员+增值ARPU/OB | 会员+增值ARPPU/授权 | 判断 |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for index, row in enumerate(rows):
        judgment = "基准" if index == 0 else strongest_gap(row, baseline)
        lines.append(
            "| {period} | {project} | {funnel} | {ob_users} | {penetration_rate:.2f}% | {member_product_page_pay_rate:.2f}% | {member_authorization_rate:.2f}% | {member_arpu_by_ob_user:.4f} | {first_upsell_rate:.2f}% | {first_upsell_arpu_by_page_user:.4f} | {second_upsell_rate:.2f}% | {second_upsell_arpu_by_page_user:.4f} | {member_plus_all_upsell_arpu_by_ob_user:.4f} | {member_plus_all_upsell_arppu_by_authorized_user:.2f} | {judgment} |".format(
                judgment=judgment, **row
            )
        )

    lines.extend(["", "## 核心问题定位", ""])
    for row in rows:
        weak_points: list[str] = []
        if row["ob_users"] < 100:
            weak_points.append("样本量偏小")
        if row["penetration_rate"] < 20:
            weak_points.append("OB 到会员页渗透偏低")
        if row["member_product_page_pay_rate"] < 5:
            weak_points.append("会员商品页付费效率偏低")
        if row["all_upsell_arppu_by_authorized_user"] <= 0:
            weak_points.append("增值未形成授权后回收")
        elif row["member_plus_all_upsell_arppu_by_authorized_user"] < row["member_arppu_by_pay_user"]:
            weak_points.append("增值回收不足以抬升授权用户价值")
        if not weak_points:
            weak_points.append("暂无单点异常，重点看 SKU 结构与实验目标")
        lines.append(f"- {row['project']} {row['funnel']}: " + "；".join(weak_points) + "。")

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
    write_report(report_path, rows, component_paths)
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
