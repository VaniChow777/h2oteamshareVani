---
name: webob-funnel-diagnosis
description: Pull and diagnose integrated WebOB funnel performance from Sensors across member payment, first upsell, and second upsell. Use when Codex needs to analyze 神策/WebOB/funnel/会员支付/渗透率/授权率/一级增值/二级增值/ARPU/ARPPU/SKU mix/conversion-drop causes across one or more funnel IDs, projects, countries, or custom time windows, and identify whether the core problem is OB scale, penetration, submit rate, submit-pay rate, SKU price mix, authorized-user value, or downstream upsell recovery.
---

# WebOB Funnel Diagnosis

## Local Secret Handling

- Do not store real keys, tokens, webhook URLs, cookies, app secrets, or exported private raw data in this skill folder, shared repositories, generated outputs, or chat replies.
- Prefer loading local-only Sensors credentials from `CODEX_SENSORS_ENV` or `~/.codex-secrets/sensors/webob.env`.
- Include only `config/sensors.env.example` in shared repositories. Each user or deployment environment supplies real values locally.
- When a required secret is missing, ask the user to configure the env file or environment variable; never ask them to paste the secret into chat.

## Overview

Use this skill for one integrated WebOB funnel diagnosis instead of three separate reports. The unified script pulls:

- member payment funnel: OB users, member page users, submit users, pay users, penetration, authorization rate, member revenue/ARPU/ARPPU, member SKU mix
- first upsell funnel: page users, submit users, pay users, submit/pay/overall pay rate, estimated revenue, ARPU/ARPPU, first-upsell SKU mix
- second upsell funnel: page users, submit users, pay users, submit/pay/overall pay rate, estimated revenue, ARPU/ARPPU, second-upsell SKU mix

The default output is a single integrated Markdown diagnosis plus TSV files for deeper inspection.

## Data Source And口径

- Sensors auth: OpenAPI API Key auth by default. Set `SENSORS_AUTH_MODE=openapi` and `SENSORS_OPENAPI_KEY`.
- Canonical dashboard: `1522` (`【webob】webob周报数据拉取`)
- Member funnel bookmark: `23211` (`【全家福】funnel_前序ob页面会员付费页_提交支付`)
- First-upsell bookmark: `23212`
- Second-upsell bookmark: `23213`
- Revenue source: segmentation bookmark `23217`, using `purchase_yoga_dance.origin_money`
- OpenAPI migrated dashboard config: `config/webob_openapi_queries.json`

Revenue and ARPU are estimated from funnel-level SKU paid users multiplied by same-period project-level SKU realized average revenue/order, because purchase events usually do not carry `funnel_id`.

## Quick Start

Run the integrated diagnosis:

```bash
python3 scripts/diagnose_webob_funnel.py \
  --project bend \
  --funnels 73,288 \
  --start 2026-05-01 \
  --end 2026-05-06 \
  --output-dir output/bend_73_288
```

Cross-project comparison:

```bash
python3 scripts/diagnose_webob_funnel.py \
  --targets bend:73,288 yoga:101,102 \
  --start 2026-05-01 \
  --end 2026-05-06 \
  --output-dir output/cross_project
```

Different periods:

```bash
python3 scripts/diagnose_webob_funnel.py \
  --target-periods \
  bend:73:2026-04-24:2026-04-30:before \
  bend:288:2026-05-01:2026-05-07:after \
  --output-dir output/period_compare
```

Country filter:

```bash
python3 scripts/diagnose_webob_funnel.py \
  --project bend \
  --funnels 73,288 \
  --start 2026-05-01 \
  --end 2026-05-06 \
  --countries US \
  --output-dir output/bend_us
```

## Useful Options

- `--project` + `--funnels`: same-project comparison.
- `--targets`: same-window same-project or cross-project comparison.
- `--target-periods`: per-target windows. Each item is `project:funnel_ids:start:end[:label]`.
- `--countries`: optional country filter. Omit it for all countries.
- `--country-field`: Sensors country field override; default is `event.$Anything.$country`.
- `--top-skus`: SKU rows shown in component Markdown reports.
- `--output-dir`: output directory for integrated and component reports.
- `--debug-raw`: keep component raw JSON files. Omit by default to reduce private-data spread.

## Output Files

The integrated script writes:

- `webob_funnel_diagnosis_report.md`: integrated business diagnosis
- `webob_funnel_integrated_summary.tsv`: one row per target with member, first-upsell, second-upsell, total ARPU, and authorized-user value
- `webob_funnel_diagnosis_manifest.json`: generated file manifest
- component folders: `member/`, `first_upsell/`, `second_upsell/`, each containing summary, SKU detail, and component Markdown reports

## Interpretation Rules

- `penetration_rate = member_page_users / ob_users`
- `member_product_page_pay_rate = member_pay_users / member_page_users`
- `member_authorization_rate = member_pay_users / ob_users`
- `member_ARPU_by_OB = member_estimated_revenue / ob_users`
- `first_upsell_rate = first_upsell_pay_users / first_upsell_page_users`
- `second_upsell_rate = second_upsell_pay_users / second_upsell_page_users`
- `all_upsell_revenue = first_upsell_estimated_revenue + second_upsell_estimated_revenue`
- `member_plus_all_upsell_ARPU = (member + first + second revenue) / ob_users`
- `all_upsell_ARPPU = all_upsell_revenue / member_pay_users`
- `member_plus_all_upsell_ARPPU = total_revenue / member_pay_users`

Treat `member_pay_users` as authorized users. A low-price or free-trial member SKU may still be valuable if it creates enough authorized users and first-/second-upsell recovery lifts total value.

Do not sum daily rows for aggregate user counts; use aggregate rows from Sensors. Mention sample-size risk when volume is small.

## Diagnostic Workflow

1. Resolve the requested project(s), funnel IDs, country filter, and exact date window(s). Convert relative dates to concrete dates in Asia/Shanghai.
2. Run `scripts/diagnose_webob_funnel.py` with explicit dates.
3. Read `webob_funnel_diagnosis_report.md` first.
4. Use the integrated TSV to compare total value and authorized-user value.
5. Use component SKU detail TSVs when the core issue appears to be price mix, zero-price mix, trial mix, or revenue share.
6. If the user asks why a period dropped, run `scripts/diagnose_member_chain.py` first, then `scripts/diagnose_submit_pay_breakdown.py` when the weak step is submit-pay.

## Output Style

Start with `一句话结论`, then show the integrated table. Explain whether the gap mainly comes from OB scale, penetration, store-page pay efficiency, authorization rate, member ARPU/ARPPU, first-upsell recovery, second-upsell recovery, or SKU mix.

When member ARPU is lower because of low-price/free-trial/0-pay authorization, do not judge it alone. Check `会员+增值ARPU/OB` and `会员+增值ARPPU/授权`.

Link the generated integrated report, integrated TSV, and relevant component SKU TSVs.
