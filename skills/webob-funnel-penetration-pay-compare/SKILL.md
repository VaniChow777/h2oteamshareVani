---
name: webob-funnel-penetration-pay-compare
description: Compare WebOB penetration, member product-page pay rate, member pay-rate, member ARPU, authorized-user value, and member SKU mix across one or more Sensors funnel IDs or custom time windows. Use when Codex needs to analyze 神策/webob/渗透率/会员商品页付费率/会员付费率/会员ARPU/授权价值 differences between multiple funnels, projects, or periods; diagnose conversion drops by OB, penetration, product-page submit, submit-pay, country mix, and payment-method mix such as PayPal/Adyen/Stripe; and judge whether low-price or free-trial member authorization is recovered by first-/second-upsell monetization.
---

# WebOB Penetration And Pay Compare

## Overview

Use this skill to compare WebOB penetration and member payment conversion across funnel IDs, including multi-funnel and multi-period comparisons.

The bundled script produces:

- summary: 进入OB人数, 会员页人数, 会员提交人数, 会员支付人数, 渗透率, 商品页付费率, 商品页-提交率, 提交-支付率, 整体付费率, estimated revenue, member ARPU, member ARPPU
- member SKU detail: `funnel_id x 会员支付SKU` 支付人数, 支付占比, SKU支付/商品页, SKU支付/提交, SKU支付/OB, realized average revenue/order, estimated revenue, 商品页ARPU贡献, revenue mix
- Markdown report and TSV/raw outputs
- diagnostic outputs for conversion drops: member-chain diagnosis, submit-pay breakdown by country, and submit-pay breakdown by payment method

Supported comparison shapes:

- multiple funnels in the same project or across projects
- one shared date window for all funnels
- custom date windows per funnel
- the same funnel compared across different date windows

## Data Source And口径

- Sensors credentials: read `SENSORS_OPENAPI_KEY` from `/Users/zhoumeng/Documents/Codex/2026-04-24/new-chat/.env`; never print secrets. This skill uses Sensors OpenAPI API Key auth only. API Secret / legacy `token=` authentication is not a supported path.
- Canonical dashboard: `1522` (`【webob】webob周报数据拉取`)
- Funnel card: bookmark `23211` (`【全家福】funnel_前序ob页面会员付费页_提交支付`)
- Revenue source: segmentation bookmark `23217`, using `purchase_yoga_dance.origin_money`
- Funnel steps:
  - Step 1: `onboard_pageview_wf_h2o`, page_index `1`, grouped by `event.onboard_pageview_wf_h2o.funnel_id`
  - Step 2: `view_deal_detail_wf_h2o`, member deal_id `50000`
  - Step 3: `submit_vip_order_yoga_dance_muscl_bend`, `webob_product_type=会员`
  - Step 4: `purchase_yoga_dance`, `webob_product_type=会员`

## Quick Start

Same-project comparison:

```bash
python3 /Users/zhoumeng/.codex/skills/webob-funnel-penetration-pay-compare/scripts/compare_penetration_pay.py \
  --project bend \
  --funnels 73,288 \
  --start 2026-05-01 \
  --end 2026-05-06
```

Cross-project comparison:

```bash
python3 /Users/zhoumeng/.codex/skills/webob-funnel-penetration-pay-compare/scripts/compare_penetration_pay.py \
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
- `--auth`: optional; only `openapi` is supported.

Advanced examples:

```bash
# Multiple funnels, same period
python3 /Users/zhoumeng/.codex/skills/webob-funnel-penetration-pay-compare/scripts/compare_penetration_pay.py \
  --project bend \
  --funnels 73,288,301 \
  --start 2026-05-01 \
  --end 2026-05-07

# Different funnels, different periods
python3 /Users/zhoumeng/.codex/skills/webob-funnel-penetration-pay-compare/scripts/compare_penetration_pay.py \
  --target-periods \
  bend:73:2026-04-24:2026-04-30:before \
  bend:288:2026-05-01:2026-05-07:after

# Same funnel, different periods
python3 /Users/zhoumeng/.codex/skills/webob-funnel-penetration-pay-compare/scripts/compare_penetration_pay.py \
  --target-periods \
  bend:73:2026-04-24:2026-04-30:before \
  bend:73:2026-05-01:2026-05-07:after
```

## Diagnostic Quick Start

Use these scripts when the user asks why today/one period is worse, which project or funnel caused a drop, whether PayPal is broken, or whether the issue is country mix versus payment-method mix.

First locate the weak chain step:

```bash
python3 /Users/zhoumeng/.codex/skills/webob-funnel-penetration-pay-compare/scripts/diagnose_member_chain.py \
  --baseline-start 2026-05-03 \
  --baseline-end 2026-05-09 \
  --compare-start 2026-05-10 \
  --compare-end 2026-05-10 \
  --projects dance,muscle,walkup \
  --output-dir .
```

Then, if the weak step is `提交-支付`, break it down by country and payment method:

```bash
python3 /Users/zhoumeng/.codex/skills/webob-funnel-penetration-pay-compare/scripts/diagnose_submit_pay_breakdown.py \
  --baseline-start 2026-05-03 \
  --baseline-end 2026-05-09 \
  --compare-start 2026-05-10 \
  --compare-end 2026-05-10 \
  --projects dance,muscle,walkup \
  --output-dir .
```

Useful diagnostic options:

- `--projects`: comma-separated projects. Omit for all projects.
- `--funnels`: optional comma-separated funnel IDs. When set, output is `project + funnel + dimension`.
- `--countries`: optional country filter before diagnosis. Omit for all countries.
- `--payment-methods`: optional payment-method filter before diagnosis, for example `paypal`.
- `--output-dir`: writes `member_chain_diagnosis.tsv`, `member_chain_diagnosis.md`, `submit_pay_by_country.tsv`, `submit_pay_by_payment_method.tsv`, and `submit_pay_breakdown_diagnosis.md`.

## Interpretation Rules

- `penetration_rate = member_page_users / ob_users`
- `submit_rate = member_submit_users / member_page_users`
- `pay_rate = member_pay_users / member_submit_users`
- `product_page_pay_rate = member_pay_users / member_page_users`
- `overall_pay_rate = member_pay_users / ob_users`
- `member_ARPU = estimated_member_revenue / ob_users`
- `member_product_page_ARPU = estimated_member_revenue / member_page_users`
- `member_ARPPU = estimated_member_revenue / member_pay_users`
- SKU-level member pay metrics:
  - `pay_mix = sku_member_pay_users / member_pay_users`
  - `sku_product_page_pay_rate = sku_member_pay_users / member_page_users`
  - `sku_pay_submit_rate = sku_member_pay_users / member_submit_users`
  - `sku_overall_pay_rate = sku_member_pay_users / ob_users`
  - `sku_product_page_ARPU_contribution = sku_estimated_revenue / member_page_users`
  - `revenue_mix = sku_estimated_revenue / estimated_member_revenue`
- Keep 付费率 granularity at funnel ID level, the same target granularity as first-upsell comparison.
- If the user gives multiple funnels and no special time instruction, use the same date window for all funnels. If the user does not mention country, do not add a country filter; if they specify one or more countries, pass `--countries` and keep the same filter across member, first-upsell, second-upsell, and revenue queries.
- If the user gives different experiment periods, use `--target-periods`; compare by `period + project + funnel`, not by funnel alone.
- State that member revenue/ARPU is estimated from funnel-level member SKU paid users multiplied by same-period project-level member SKU realized average revenue/order because purchase events usually do not carry `funnel_id`.
- Treat member payment as both immediate revenue and payment authorization. A low-price or free-trial member SKU may be valuable if it increases authorized users and then improves first-/second-upsell capture.
- Do not sum daily rows for aggregate user counts; use aggregate rows from Sensors.
- Mention sample-size risk when volume is small.

## Conversion Drop Diagnosis

When diagnosing a drop, use a two-layer approach:

1. Identify the weak chain step with `diagnose_member_chain.py`:
   - `OB用户量`
   - `渗透率 = member_page_users / ob_users`
   - `商品页-提交率 = member_submit_users / member_page_users`
   - `提交-支付率 = member_pay_users / member_submit_users`
   - `商品页付费率 = member_pay_users / member_page_users`
   - `会员付费率/授权率 = member_pay_users / ob_users`
2. If `提交-支付` is the weak step, run `diagnose_submit_pay_breakdown.py` and explain whether the decline is caused by:
   - a country whose own submit-pay rate worsened
   - a low-converting country taking more submit share
   - a high-converting country taking less submit share
   - a payment method whose own submit-pay rate worsened
   - a low-converting payment method taking more submit share
   - a high-converting payment method taking less submit share

For period comparisons, compare both absolute volume and normalized daily volume:

- `compare_daily_pay - baseline_daily_pay` estimates the daily paid-user loss.
- `submit_pay_delta_pp` shows conversion deterioration.
- `submit_share_delta_pp` shows mix shift.

The submit-event payment-method field is:

- `event.submit_vip_order_yoga_dance_muscl_bend.purchase_type_all_product`
- Chinese cname: `全家福_支付方式`

Use it at funnel step 3 (`by_field_steps` value `2`) because the payment method is attached to `submit_vip_order_yoga_dance_muscl_bend`, not necessarily to the purchase event. Known values include `paypal`, `adyen`, `applepay_adyen`, `googlepay_adyen`, and `stripe`.

Treat `(空)` payment method as its own meaningful bucket:

- Show its submit share and submit-pay rate when it is material.
- Do not force-map `(空)` to a named payment method.
- If `(空)` is large or worsens, call out a payment-method attribution or instrumentation gap and recommend checking field completeness.

Project-level diagnosis guidance:

- If `渗透率` drops, inspect traffic source, country mix, and OB-to-member-page exposure.
- If `商品页-提交率` drops, inspect product-page offer, price display, SKU selection, and page UX.
- If `提交-支付率` drops, inspect payment method health, PSP errors, country/payment routing, and payment-method mix.
- If only a small number of submits or pays are involved, label the conclusion as small-sample risk and avoid calling it a systemic outage.

## Required Comparison Structure

When the user asks for overall funnel performance, do not present member, first-upsell, and second-upsell as three disconnected reports. Build one integrated comparison table in this order:

1. `OB用户量`
2. `渗透率`, `商店页付费率`, `会员付费率/授权率`, `会员ARPU`, `会员ARPPU`
3. `一级增值率`, `一级增值ARPU`, `二级增值率`, `二级增值ARPU`
4. `会员+所有增值ARPU`, `会员+所有增值ARPPU`, `所有增值ARPU`, `所有增值ARPPU`

Use these derived metrics when first- and second-upsell reports are available:

- `member_authorized_users = member_pay_users`
- `member_authorization_rate = member_pay_users / ob_users`
- `all_upsell_revenue = first_upsell_estimated_revenue + second_upsell_estimated_revenue`
- `total_revenue = member_estimated_revenue + first_upsell_estimated_revenue + second_upsell_estimated_revenue`
- `member_plus_all_upsell_ARPU = total_revenue / ob_users`
- `member_plus_all_upsell_ARPPU = total_revenue / member_authorized_users`
- `all_upsell_ARPU = all_upsell_revenue / ob_users`
- `all_upsell_ARPPU = all_upsell_revenue / member_authorized_users`

Interpret `会员+所有增值ARPPU` and `所有增值ARPPU` as authorized-user value, not isolated purchase-event ARPPU. This matches the business trick: once a user has authorized member payment, first- and second-upsell payments may be close to frictionless.

## Analysis Checklist

When explaining member payment SKU mix, do more than restate the table:

- Identify the pricing strategy behind SKU strings: first-pay price, first-pay duration, renewal price, and flow ID. Example: `15.19d28-38.95d28-flow14-861` means first pay `15.19` for 28 days, renewal `38.95` for 28 days, flow `14`.
- Separate SKU roles when visible from the product setup: direct pay, save/winback, trial winback, low-price trial, monthly product, quarterly product.
- Compare `submit share`, `pay share`, and `revenue share`. A SKU with high pay share but low revenue share may lift payment rate while hurting ARPU.
- Compare product-page pay rate and ARPU/page together:
  - high product-page pay rate + low ARPU/page usually means low-price SKU mix wins conversion but weakens value.
  - low product-page pay rate + high ARPU/page usually means higher-price SKU mix but weaker conversion.
- Add an "authorization value" layer when first-/second-upsell data is also available:
  - `authorized_users = member_pay_users`
  - compare `authorized_user_rate = member_pay_users / ob_users`
  - compare downstream first-upsell and second-upsell pay users/revenue relative to authorized users when possible
  - do not call a low-price/free-trial member strategy bad only because member ARPU is lower; check whether it creates enough authorized users for near-frictionless upsell payment
  - judge total monetization with `member revenue + first-upsell revenue + second-upsell revenue`, preferably also per OB user and per authorized user
- For experiments involving 7-day trial price changes, explicitly compare:
  - trial first-pay price
  - trial renewal price
  - 7-day trial SKU submit/pay share
  - product-page pay rate
  - member ARPU/ARPPU
  - authorized-user lift and downstream upsell recovery
- In conclusions, state whether the variant is “front-door stronger” (higher penetration), “page efficiency stronger” (higher product-page pay), or “value stronger” (higher ARPU/page or ARPPU).
  Also state whether it is “authorization stronger” (more authorized users) and whether downstream upsell monetization recovered any member-side ARPU loss.

## Output Style

Start with `一句话结论`, then the required integrated comparison table with a `判断` column. In `判断`, bold the key point for each row, especially the row that explains the main win or risk.

After the table, explain:

- whether the gap comes mainly from OB scale, penetration, store-page pay efficiency, authorization rate, member ARPU/ARPPU, first-upsell recovery, second-upsell recovery, or SKU mix
- whether low-price/free-trial authorization is being recovered by `所有增值ARPU/ARPPU`
- the main SKU composition difference and its advantage/risk
- a short `下一步建议`

Link `report.md`, `summary.tsv`, `member_sku_detail.tsv`, and `raw.json`.

For diagnostic questions, use this shorter shape:

- Start with the answer: country issue, payment-method issue, mixed issue, or sample too small.
- Provide a table with `项目/对象`, `主因判断`, `国家侧证据`, `支付方式侧证据`, and `判断`.
- Bold the key phrase in `判断`, for example `**PayPal 是核心拖累**` or `**不是 PayPal，样本太小**`.
- Mention `daily pay delta`, `submit-pay delta`, and `submit share delta` for the main drivers.
- Link the generated diagnosis Markdown and TSV files.
