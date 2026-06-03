# WebOB Weekly Metrics

## Feishu Destination

Write all generated report data to Feishu Bitable via OpenAPI:

`https://bqwrbbbbtoc.feishu.cn/wiki/BEN0weeYJiKs01kIkHnc4DNtnvd`

The Bitable contains two tables:

- `funnel数据`
- `业务数据`

Do not use browser paste for Feishu writes.

## First Table: funnel指标+拉取时间

Headers:

`项目, 时间段, 渗透率, 转化率, 一级增值率, 二级增值率, 注册率, pwa-app率, 拉取时间`

Periods:

- 过去7天: yesterday minus 6 days through yesterday.
- 本月: current month day 1 through yesterday.

The `时间段` field must only contain `过去7天` or `本月`, not the concrete date range.

Metric mapping:

- 渗透率: dashboard card 1, first step to second step conversion.
- 转化率: dashboard card 1, total conversion rate.
- 一级增值率: dashboard card 2, total conversion rate.
- 二级增值率: dashboard card 3, total conversion rate.
- 注册率: dashboard card 4, step 3 to step 6 conversion. For `muscle` and `yoga`, override 注册率 with dashboard card 9.
- pwa-app率: dashboard card 4, step 7 to step 8 conversion.

Timezone:

- Respect each dashboard card payload. Cards 1-3 use UTC+00:00; card 4 is configured as UTC+08:00.
- If the user asks for zero-time-zone data, verify `server_time_zone` is `UTC+00:00` for the relevant card.

Important correctness note:

- Use aggregate rows returned by the Sensors funnel API. Do not sum daily rows for user counts or conversion rates.

## Second Table: 业务指标+拉取时间

Headers:

`项目, 月续订率, 季续订率, 退款率, 退订率, 拉取时间`

Do not include `统计时间`.

Metric mapping:

- 月续订率: card 5, by-project total conversion rate.
- 季续订率: card 6, by-project total conversion rate.
- 退款率: card 7, by-project rollup value.
- 退订率: card 8, by-project total conversion rate.

Date windows:

- 月续订率: previous month day 1 through the day corresponding to yesterday. If the target month is shorter, cap to that month end.
- 季续订率: three months before the current month, day 1 through the day corresponding to yesterday. If the target month is shorter, cap to that month end.
- 退款率: past 30 days through yesterday, inclusive.
- 退订率: past 30 days through yesterday, inclusive.

Example with pull date 2026-04-27:

- 月续订率: 2026-03-01~2026-03-26
- 季续订率: 2026-01-01~2026-01-26
- 退款率/退订率: 2026-03-28~2026-04-26

## Historical Backfill

- Use `run_webob_report.py --today YYYY-MM-DD --sync-feishu` to simulate a past execution date.
- The simulated date controls `拉取时间` and all relative date windows.
- Backfills should append records and should not send 企业微信 notifications unless explicitly requested.
- Example: for simulated Monday `2026-04-20`, `过去7天` means `2026-04-13~2026-04-19`, and `拉取时间` is `2026-04-20`.

## Dashboard Cards

Use fixed bookmark IDs. Do not select cards by dashboard position/order.

- `23211` `/funnel/` `【全家福】funnel_前序ob页面会员付费页_提交支付`
- `23212` `/funnel/` `【全家福】funnel_一级增值付费页_一级提交支付`
- `23213` `/funnel/` `【全家福】funnel_增值付费页_二级增值付费_二级增值支付`
- `23214` `/funnel/` `【全家福】funnel_进入ob_会员支付_注册/邮箱合并_app/pwa`
- `23215` `/funnel/` `【全家福】月产品_会员_首续率_不含7天产品`
- `23216` `/funnel/` `【全家福】3月产品_会员_首续率_不含7天产品`
- `23217` `/segmentation/` `【全家福】退款金额&退款率`
- `23218` `/funnel/` `【全家福】会员新增支付-7日取消订阅`
- `23219` `/funnel/` used for `muscle` and `yoga` 注册率 override.

## Endpoint Notes

- Funnel cards use `/api/v2/sa/funnel/report/`.
- Funnel API calls may be slow; use retry and a long client read timeout rather than falling back to daily-row summation.
- Refund card 7 uses the older `/api/events/report/`, not `/api/v2/sa/segmentation/report/`.
- For card 7 custom expression, keep the raw expression form such as `sum(event...)/sum(event...)|%2p`; converting it to quoted compiled syntax causes `ILLEGAL_INDICATOR_EXPRESSION`.
- Card 7 rollup values are in `rollup_result.rows`, not `table_data.cells`.

## Enterprise WeChat

- Store the webhook in `.env` as `QIWEI_WEBHOOK_URL`.
- Do not hardcode or print the webhook key in skill instructions, command output summaries, or final answers.
- Sending report data to 企业微信 is third-party communication. Confirm at action time before running `run_webob_report.py --send-qiwei`.
- The message payload must include only the pull timestamp and the Feishu Bitable link. Do not include row counts, metric values, or the full TSV/table text in 企业微信.

## Feishu Bitable API

- Resolve the Wiki URL to a Bitable app token via `/wiki/v2/spaces/get_node`.
- List tables via `/bitable/v1/apps/{app_token}/tables` and match `funnel数据` / `业务数据` by name.
- Normal sync appends records and preserves history, even when `拉取时间` matches an existing batch.
- Ensure missing Bitable fields are created before inserting records. New fields are created as text fields unless adjusted manually in Feishu.
- If blank records were created before fields existed, run with `--cleanup-empty` only after user confirmation because it deletes cloud records.
- Insert records with `/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create`.
- If fields are numeric percentage fields, convert `14.02%` to `0.1402`; if they are text fields, keep the percent string.
