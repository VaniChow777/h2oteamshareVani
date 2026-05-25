---
name: webob-funnel-second-upsell-compare
description: Compare WebOB second-upsell performance across one or more Sensors funnel IDs or custom time windows. Use when Codex needs to analyze 神策/webob/二级增值/second upsell differences between multiple funnels, projects, or the same funnel across periods, including submit rate, pay rate, overall pay rate, ARPU, ARPPU, revenue estimates, SKU mix, and whether second upsell deepens payback from low-price or free-trial member payment authorization.
---

# WebOB Second-Upsell Compare

## Overview

Use this skill to compare WebOB second-upsell funnel performance with the same output structure as first-upsell analysis. It supports multi-funnel comparisons, per-target custom periods, and the same funnel compared across different periods.

The bundled script produces:

- funnel summary: 二级增值页人数, 提交人数, 支付人数, 提交率, 支付率, 整体付费率, estimated revenue, ARPU, ARPPU
- SKU detail: `product_id_all_product` mix by funnel, paid users, estimated revenue, per-SKU revenue/order
- Markdown report: summary table and SKU mix tables

Supported comparison shapes:

- multiple funnels in the same project or across projects
- one shared date window for all funnels
- custom date windows per funnel
- the same funnel compared across different date windows

## Data Source And口径

- Sensors credentials: read `SENSORS_OPENAPI_KEY` from `/Users/zhoumeng/Documents/Codex/2026-04-24/new-chat/.env`; never print secrets. This skill uses Sensors OpenAPI API Key auth only. API Secret / legacy `token=` authentication is not a supported path.
- Canonical dashboard: `1522` (`【webob】webob周报数据拉取`)
- Second-upsell funnel card: bookmark `23213`
- Revenue source: segmentation bookmark `23217`, using `purchase_yoga_dance.origin_money`
- Second-upsell event filters:
  - `webob_product_type=增值`
  - `webob_product_type_is_double_extra=二级增值`
- SKU dimension: `event.purchase_yoga_dance.product_id_all_product`

Important limitation: `purchase_yoga_dance.funnel_id` is usually empty. Compute funnel-level ARPU by multiplying funnel-level `funnel_id x SKU` paid users by same-period project-level SKU realized average revenue/order. State that revenue/ARPU is estimated from SKU mix.

## Quick Start

Same-project comparison:

```bash
python3 /Users/zhoumeng/.codex/skills/webob-funnel-second-upsell-compare/scripts/compare_second_upsell.py \
  --project bend \
  --funnels 73,288 \
  --start 2026-05-01 \
  --end 2026-05-06
```

Cross-project comparison:

```bash
python3 /Users/zhoumeng/.codex/skills/webob-funnel-second-upsell-compare/scripts/compare_second_upsell.py \
  --targets bend:73,288 yoga:101,102 \
  --start 2026-05-01 \
  --end 2026-05-06
```

Useful options:

- `--project` + `--funnels`: same-project comparison.
- `--targets`: same-project or cross-project comparison in one shared date window.
- `--target-periods`: per-target windows. Each item is `project:funnel_ids:start:end[:label]`.
- `--period-label`: report label.
- `--countries`: optional comma-separated country filter. Omit it for all countries.
- `--country-field`: Sensors country field override; default is `event.$Anything.$country`.
- `--output-dir`: defaults to current working directory.
- `--top-skus`: SKU rows shown in Markdown.
- `--auth`: optional; only `openapi` is supported.

Advanced examples:

```bash
# Multiple funnels, same period
python3 /Users/zhoumeng/.codex/skills/webob-funnel-second-upsell-compare/scripts/compare_second_upsell.py \
  --project bend \
  --funnels 73,288,301 \
  --start 2026-05-01 \
  --end 2026-05-07

# Different funnels, different periods
python3 /Users/zhoumeng/.codex/skills/webob-funnel-second-upsell-compare/scripts/compare_second_upsell.py \
  --target-periods \
  bend:73:2026-04-24:2026-04-30:before \
  bend:288:2026-05-01:2026-05-07:after

# Same funnel, different periods
python3 /Users/zhoumeng/.codex/skills/webob-funnel-second-upsell-compare/scripts/compare_second_upsell.py \
  --target-periods \
  bend:73:2026-04-24:2026-04-30:before \
  bend:73:2026-05-01:2026-05-07:after
```

## Interpretation Rules

- `submit_rate = submit_users / page_users`
- `pay_rate = pay_users / submit_users`
- `overall_pay_rate = pay_users / page_users`
- `ARPU = estimated_revenue / page_users`
- `ARPPU = estimated_revenue / pay_users`
- Treat `0.00` SKUs as real mix and call out ARPU drag.
- Analyze second upsell as deeper post-authorization monetization. If member payment authorization was obtained through 7-day free trial, low-price trial, or zero-price authorization, second-upsell conversion can be part of the payback path, not just an isolated upsell funnel.
- If the user gives multiple funnels and no special time instruction, use the same date window for all funnels. If the user does not mention country, do not add a country filter; if they specify one or more countries, pass `--countries` and keep the same filter across member, first-upsell, second-upsell, and revenue queries.
- If the user gives different experiment periods, use `--target-periods`; compare by `period + project + funnel`, not by funnel alone.
- Do not sum daily rows for aggregate user counts; use aggregate rows from Sensors.
- Mention sample-size risk when volume is small.

## Integrated Output Role

When the user asks for overall funnel performance together with member payment and first upsell, second-upsell metrics should be summarized inside the integrated table, not only as a standalone report.

Required second-upsell rows in the integrated table:

- `二级增值率 = second_upsell_pay_users / second_upsell_page_users`
- `二级增值ARPU = second_upsell_estimated_revenue / second_upsell_page_users`

Required contribution to total-value rows:

- contribute `second_upsell_estimated_revenue` to `所有增值ARPU` and `会员+所有增值ARPU`
- when member data is available, use `member_pay_users` as authorized users and contribute second-upsell revenue to `所有增值ARPPU = (first + second upsell revenue) / member_pay_users`

Interpret second upsell as the deeper recovery layer after member authorization. It can validate a low-price or free-trial member strategy only if it improves total value per OB user or value per authorized user enough to offset member-side ARPU dilution.

## Analysis Checklist

When explaining second-upsell SKU mix:

- Parse SKU strings into first-pay price, first-pay duration, renewal price, and flow ID.
- Compare whether the test funnel concentrates payment in the main second-upsell SKU or leaks into low-price/free SKU paths.
- Compare conversion and value together:
  - If `overall_pay_rate` is similar but ARPU differs, the cause is SKU price mix.
  - If ARPU is similar but pay rate differs, the cause is page/submission/payment efficiency.
- Highlight any low-price SKU share because second-upsell ARPU is usually sensitive to small low-price leakage.
- Add an authorization-payback layer when member and first-upsell data are also available:
  - compare second-upsell pay users/revenue against `member_pay_users` or first-upsell pay users to see whether authorization continues to monetize
  - if member ARPU is low but first + second upsell revenue per authorized user is high, describe the strategy as "authorization-led monetization" rather than simply low-value
  - if second-upsell conversion or ARPU is weak, say downstream payback is insufficient and the free/low-price authorization strategy needs LTV, refund, and renewal validation
  - evaluate total value as `member revenue + first-upsell revenue + second-upsell revenue`, preferably per OB user and per authorized user
- Include a concise “which funnel wins and why” conclusion when the user asks for analysis.

## Output Style

If second-upsell is part of a full funnel comparison, place its rate and ARPU in the integrated table after first upsell, then use its revenue in `会员+所有增值ARPU/ARPPU` and `所有增值ARPU/ARPPU`. If second-upsell is analyzed alone, lead with ARPU/ARPPU and the rate table, then explain SKU mix differences. When the same analysis includes member and first-upsell reports, explicitly say whether second upsell strengthens or fails to strengthen the authorization-led monetization story. Link `report.md`, `summary.tsv`, and `sku_detail.tsv`.
