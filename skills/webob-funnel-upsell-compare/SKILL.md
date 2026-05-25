---
name: webob-funnel-upsell-compare
description: Compare WebOB first-upsell performance across one or more Sensors funnel IDs or custom time windows. Use when Codex needs to analyze 神策/webob/一级增值/first upsell differences between multiple funnels, projects, or the same funnel across periods, including submit rate, pay rate, overall pay rate, ARPU, ARPPU, revenue estimates, SKU mix, and whether first upsell recovers value from low-price or free-trial member payment authorization.
---

# WebOB Funnel Upsell Compare

## Overview

Use this skill to compare first-upsell performance across WebOB funnel IDs with the same Sensors dashboard口径 used by the WebOB weekly report. It supports multi-funnel comparisons, per-target custom periods, and the same funnel compared across different periods.

The bundled script produces:

- funnel summary: 增值页人数, 提交人数, 支付人数, 提交率, 支付率, 整体付费率, estimated revenue, ARPU, ARPPU
- SKU detail: `product_id_all_product` mix by funnel, paid users, estimated revenue, per-SKU revenue/order
- Markdown report: a concise table and key SKU-mix interpretation

Supported comparison shapes:

- multiple funnels in the same project or across projects
- one shared date window for all funnels
- custom date windows per funnel
- the same funnel compared across different date windows

## Data Source And口径

- Sensors deployment: read `SENSORS_OPENAPI_KEY` from `/Users/zhoumeng/Documents/Codex/2026-04-24/new-chat/.env`; never print secrets. This skill uses Sensors OpenAPI API Key auth only. API Secret / legacy `token=` authentication is not a supported path.
- Canonical dashboard: `1522` (`【webob】webob周报数据拉取`)
- First-upsell funnel card: bookmark `23212`
- First-upsell funnel steps:
  - Step 1: `view_deal_detail_wf_h2o`, deal_id in `50001,50054`, grouped by `event.view_deal_detail_wf_h2o.funnel_id`
  - Step 2: `submit_vip_order_yoga_dance_muscl_bend`, `webob_product_type=增值`, `webob_product_type_is_double_extra=非二级增值`
  - Step 3: `purchase_yoga_dance`, same 增值/非二级增值 filters
- SKU dimension: `event.purchase_yoga_dance.product_id_all_product`
- Revenue source: segmentation bookmark `23217`, using `purchase_yoga_dance.origin_money`

Important limitation: `purchase_yoga_dance.funnel_id` is usually empty. To compute funnel-level ARPU, use the funnel report to obtain `funnel_id x SKU` paid users, then multiply by the same-period project-level SKU realized average revenue/order from the payment event. State that revenue/ARPU is estimated from SKU mix unless a direct revenue-by-funnel source is available.

## Quick Start

Run the bundled script:

```bash
python3 /Users/zhoumeng/.codex/skills/webob-funnel-upsell-compare/scripts/compare_first_upsell.py \
  --project bend \
  --funnels 73,288 \
  --start 2026-05-01 \
  --end 2026-05-06
```

For cross-project comparisons, use `--targets`. Each target is `project:funnel_id[,funnel_id]`; the script computes SKU realized average revenue/order separately for each project before comparing ARPU:

```bash
python3 /Users/zhoumeng/.codex/skills/webob-funnel-upsell-compare/scripts/compare_first_upsell.py \
  --targets bend:73,288 yoga:101,102 \
  --start 2026-05-01 \
  --end 2026-05-06
```

Useful options:

- `--project` + `--funnels`: same-project comparison.
- `--targets`: same-project or cross-project comparison in one shared date window; do not combine with `--project`/`--funnels`.
- `--target-periods`: per-target windows. Each item is `project:funnel_ids:start:end[:label]`.
- `--period-label`: label for the report, default is the date range.
- `--output-dir`: defaults to the current working directory.
- `--dashboard-id`, `--first-upsell-bookmark-id`, `--revenue-bookmark-id`: override only if the dashboard口径 changes.
- `--top-skus`: controls how many SKU rows to show in the Markdown summary.
- `--auth`: optional; only `openapi` is supported.

Advanced examples:

```bash
# Multiple funnels, same period
python3 /Users/zhoumeng/.codex/skills/webob-funnel-upsell-compare/scripts/compare_first_upsell.py \
  --project bend \
  --funnels 73,288,301 \
  --start 2026-05-01 \
  --end 2026-05-07

# Different funnels, different periods
python3 /Users/zhoumeng/.codex/skills/webob-funnel-upsell-compare/scripts/compare_first_upsell.py \
  --target-periods \
  bend:73:2026-04-24:2026-04-30:before \
  bend:288:2026-05-01:2026-05-07:after

# Same funnel, different periods
python3 /Users/zhoumeng/.codex/skills/webob-funnel-upsell-compare/scripts/compare_first_upsell.py \
  --target-periods \
  bend:73:2026-04-24:2026-04-30:before \
  bend:73:2026-05-01:2026-05-07:after
```

## Workflow

1. Resolve the requested project(s), funnel IDs, and date window(s). If the user says “本月/最近7天/截至昨天”, convert it to concrete dates in Asia/Shanghai, but query Sensors with the dashboard's server timezone口径.
2. Run `compare_first_upsell.py` with explicit dates. Use `--project`/`--funnels` or `--targets` for one shared window; use `--target-periods` when any target has its own window or when comparing one funnel across time.
3. Read the generated Markdown report first. Use the TSVs for deeper detail.
4. In the answer, lead with ARPU/ARPPU and explain which SKU mix differences caused it.
5. Include the direct file links to the generated `summary.tsv`, `sku_detail.tsv`, and `report.md`.

## Interpretation Rules

- `submit_rate = submit_users / page_users`
- `pay_rate = pay_users / submit_users`
- `overall_pay_rate = pay_users / page_users`
- `ARPU = estimated_revenue / page_users`
- `ARPPU = estimated_revenue / pay_users`
- Treat `0.00` SKUs as real SKU mix. They can keep payment conversion high while dragging ARPU.
- Analyze first upsell as post-authorization monetization. Users who authorized member payment, including 7-day free trial or low first-pay SKU users, can often pay first upsell with very low friction; therefore first-upsell conversion can be the recovery path for low member ARPU.
- For cross-project comparisons, compare ARPU confidently only after confirming each project's SKU realized average revenue/order was calculated separately by `--targets`.
- If the user gives multiple funnels and no special time instruction, use the same date window for all funnels. If the user does not mention country, do not add a country filter; if they specify one or more countries, pass `--countries` and keep the same filter across member, first-upsell, second-upsell, and revenue queries.
- If the user gives different experiment periods, use `--target-periods`; compare by `period + project + funnel`, not by funnel alone.
- Do not sum daily funnel rows to derive aggregate user counts; use aggregate rows from the Sensors report because user deduping differs by aggregation level.
- If sample sizes are small, say so plainly before making strong conclusions.

## Integrated Output Role

When the user asks for overall funnel performance together with member payment and second upsell, first-upsell metrics should be summarized inside the integrated table, not only as a standalone report.

Required first-upsell rows in the integrated table:

- `一级增值率 = first_upsell_pay_users / first_upsell_page_users`
- `一级增值ARPU = first_upsell_estimated_revenue / first_upsell_page_users`

Required contribution to total-value rows:

- contribute `first_upsell_estimated_revenue` to `所有增值ARPU` and `会员+所有增值ARPU`
- when member data is available, use `member_pay_users` as authorized users and contribute first-upsell revenue to `所有增值ARPPU = (first + second upsell revenue) / member_pay_users`

Interpret first upsell as the first recovery layer after member authorization. A funnel with lower member ARPU can still be better if first upsell lifts total value per OB user and value per authorized user.

## Analysis Checklist

When explaining first-upsell SKU mix:

- Parse SKU strings into strategy variables: first-pay price, first-pay duration, renewal price, and flow ID. Example: `14.99d28-30.99d28-flow14-866` means first pay `14.99` for 28 days, renewal `30.99` for 28 days, flow `14`.
- Group visible SKU roles when possible: direct pay, winback/save, free or zero-price trial winback, monthly/quarterly renewal path.
- Compare pay share and revenue share. A zero-price or low-price SKU can improve conversion while dragging ARPU; a high-price SKU can improve ARPU even with lower pay share.
- Call out both conversion and value:
  - `overall_pay_rate` says whether the page converts.
  - `ARPU/page` says whether the converted SKU mix is valuable.
  - `ARPPU` says paid-user value.
- Add an authorization-recovery layer when member data is also available:
  - compare first-upsell pay users/revenue against `member_pay_users` as a proxy for authorized-user recovery
  - if a funnel has lower member ARPU but higher authorized users and higher first-upsell revenue per authorized user, say the trial strategy may be buying authorization successfully
  - if member ARPU is lower and first-upsell ARPU/pay rate does not recover, say the low-price/free-trial strategy is not yet paying back in the first upsell
  - evaluate total value as `member revenue + first-upsell revenue`, and when second-upsell data is present use `member + first + second`
- For A/B comparisons, include relative deltas for major KPI gaps when useful, especially ARPU and zero-price SKU share.
  Also include whether first upsell offsets member-side ARPU loss from low-price/free-trial authorization.

## Output Style

Keep the user-facing answer short and business-oriented:

- If first-upsell is part of a full funnel comparison, place its rate and ARPU in the integrated table after the member metrics and before second upsell.
- If first-upsell is analyzed alone, start with the comparison table.
- Then name the main SKU-mix driver, for example: “funnel288 的 0 元 SKU 支付占比更高，所以 ARPU 被拖低.”
- When the member funnel contains 7-day free trial, low-price trial, or 0-pay authorization, avoid judging the member segment alone. Add whether first-upsell monetization recovered the authorization cost.
- Include a short “优势/风险/下一步” if the user asks for analysis, not just data.
- Mention the estimation caveat once.
- Link the generated files.
