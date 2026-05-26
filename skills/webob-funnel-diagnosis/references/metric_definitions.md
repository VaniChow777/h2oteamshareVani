# WebOB Funnel Diagnosis Metrics

## Member Funnel

- `penetration_rate = member_page_users / ob_users`
- `submit_rate = member_submit_users / member_page_users`
- `pay_rate = member_pay_users / member_submit_users`
- `product_page_pay_rate = member_pay_users / member_page_users`
- `overall_pay_rate = member_pay_users / ob_users`
- `member_ARPU = estimated_member_revenue / ob_users`
- `member_ARPPU = estimated_member_revenue / member_pay_users`

## Upsell Funnels

- `upsell_submit_rate = submit_users / page_users`
- `upsell_pay_rate = pay_users / submit_users`
- `upsell_overall_pay_rate = pay_users / page_users`
- `upsell_ARPU = estimated_revenue / page_users`
- `upsell_ARPPU = estimated_revenue / pay_users`

## Integrated Value

- `authorized_users = member_pay_users`
- `all_upsell_revenue = first_upsell_estimated_revenue + second_upsell_estimated_revenue`
- `total_revenue = member_estimated_revenue + first_upsell_estimated_revenue + second_upsell_estimated_revenue`
- `member_plus_all_upsell_ARPU = total_revenue / ob_users`
- `all_upsell_ARPPU = all_upsell_revenue / authorized_users`
- `member_plus_all_upsell_ARPPU = total_revenue / authorized_users`

## Diagnosis Notes

Low member ARPU is not automatically bad when a test intentionally creates low-price or free-trial authorization. Judge the strategy with total value per OB user and total value per authorized user after first and second upsell recovery.
