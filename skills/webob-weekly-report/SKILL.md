---
name: webob-weekly-report
description: Pull Daily Yoga webob weekly reporting data from the private Sensors Analytics deployment, sync results to Feishu Bitable via API, and send a short Enterprise WeChat summary. Use when the user asks to 拉取/更新/生成 webob 周报数据, 神策周报指标, funnel 指标, 业务指标, 飞书多维表格, or 企业微信摘要推送.
---

# WebOB Weekly Report

## Overview

Use this skill to generate the WebOB weekly report data from Sensors Analytics and sync the result to the Feishu Bitable linked from:

`https://bqwrbbbbtoc.feishu.cn/wiki/BEN0weeYJiKs01kIkHnc4DNtnvd`

Do not expose API keys, API secrets, cookies, or `.env` contents in replies. The canonical working directory is:

`WEBOB_REPORT_WORKSPACE`, a local directory containing `generate_webob_weekly_summary.py`, `generate_webob_business_summary.py`, their config files, and `.env`.

## Workflow

1. Run the bundled helper:

```bash
python3 scripts/run_webob_report.py
```

2. To sync generated TSVs to Feishu Bitable API, run this after action-time confirmation:

```bash
python3 scripts/run_webob_report.py --sync-feishu
```

Every normal sync appends new records and preserves historical data. Do not delete existing records for the same `拉取时间`.

To simulate a past run date, pass `--today YYYY-MM-DD`. This changes all relative windows and sets `拉取时间` to that simulated date:

```bash
python3 scripts/run_webob_report.py --today 2026-04-27 --sync-feishu
```

For historical backfills, sync Feishu only by default and do not send Enterprise WeChat notifications unless the user explicitly asks to notify the group.

If a previous run created blank records before fields existed, confirm deletion first, then run:

```bash
python3 scripts/run_webob_report.py --sync-feishu --cleanup-empty
```

3. To also send a short summary and Bitable link to 企业微信, only run this after action-time confirmation:

```bash
python3 scripts/run_webob_report.py --sync-feishu --send-qiwei
```

4. Confirm both generated TSVs exist under the workspace `output/` directory:

```text
funnel指标_<YYYYMMDD_HHMMSS>.tsv
业务指标_<YYYYMMDD_HHMMSS>.tsv
```

5. Before modifying Feishu or sending 企业微信, ask for action-time confirmation unless the user already explicitly approved this exact write/send in the current turn.

6. Use Feishu OpenAPI only. Do not paste data into Feishu through the browser.

7. Enterprise WeChat messages should contain only the pull timestamp and the Feishu Bitable link. Do not include full table text, row counts, or metric values.

8. Normal Feishu writes must append records only. Never remove historical records unless the user explicitly asks for cleanup and approves the deletion.

## Data Sources

- Sensors base URL: `https://shence.dailyyoga.com.cn/`
- Sensors project key: `h2o_product`
- Dashboard: `1522`, named `【webob】webob周报数据拉取`
- Detail reference: read `references/metrics.md` when changing metric logic, debugging mismatches, or explaining the report口径.

## Scripts

The helper delegates to the workspace scripts:

- `generate_webob_weekly_summary.py`: first table, `funnel指标+拉取时间`
- `generate_webob_business_summary.py`: second table, `业务指标+拉取时间`

For the funnel table, registration rate uses the new dashboard card `23262` (`webob-注册率`) for all projects except `yoga`; `yoga` uses the same card with payment method `purchase_type_all_product != paypal`. The `webob-到达pwa率` metric uses dashboard card `23263` and is appended as the last exported column.

Dashboard cards are selected by fixed bookmark IDs, not by dashboard position. Moving or adding cards in dashboard `1522` should not change this report.

The workspace `.env` must contain `SENSORS_OPENAPI_KEY`. API Secret / legacy `token=` authentication is not a supported production path for this skill.
If auth fails, ask the user to update `.env`; do not ask them to paste secrets into chat.

OpenAPI mode reads query definitions from `config/webob_openapi_queries.json` and does not call the legacy dashboard API.

OpenAPI migration notes:

- Funnel table uses API Key / OpenAPI only.
- Refund rate converts OpenAPI fractional values to percentage display.
- `webob-到达pwa率` uses card `23263`; preserve the filter semantics `Android/iOS OR (js AND selected PWA page_id)`.
- `webob-注册率` uses card `23262`; for `yoga`, add `purchase_type_all_product != paypal`.
- Monthly and quarterly renewal rates use OpenAPI SQL instead of OpenAPI funnel, because the legacy cards are same-event purchase funnels with `relevance_field=product_id_all_product`; OpenAPI funnel counts the starting purchase itself as a valid later step and returns materially higher rates. The SQL version explicitly joins first purchase to later same-SKU purchase within the legacy conversion window and is within user-level boundary differences of the legacy funnel.
- Unsubscribe rate uses OpenAPI SQL by joining member first purchase to later cancel-subscribe events on `order_id` within 7 days.
- First-/second-upsell funnel metrics may differ from historical legacy/UI by one user in small samples because OpenAPI funnel and legacy dashboard engine handle edge users slightly differently. Use OpenAPI as the source of truth.

The workspace `.env` must contain Feishu app credentials before `--sync-feishu` can work:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_BITABLE_URL`
- `FEISHU_FUNNEL_TABLE_NAME=funnel数据`
- `FEISHU_BUSINESS_TABLE_NAME=业务数据`

The 企业微信 webhook must be stored in `.env` as `QIWEI_WEBHOOK_URL`. Do not print the webhook URL or key. Sending is opt-in via `--send-qiwei`.

## Validation

After running, state the date windows used and the generated file paths. For the first funnel table, preserve aggregate API results; do not sum daily trend rows because funnel user deduping makes daily sums differ from aggregate totals.
