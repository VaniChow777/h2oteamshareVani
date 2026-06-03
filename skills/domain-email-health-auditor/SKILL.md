---
name: domain-email-health-auditor
description: Audit domain health, website user experience, payment-path risk, and customer-service mailbox deliverability for active domains. Use when Codex needs to evaluate DNS correctness, HTTPS/TLS health, redirect behavior, page loading speed, browser/device differences, payment conversion risk, domain reputation, SPF/DKIM/DMARC/MTA-STS/TLS-RPT/BIMI setup, MX health, blacklist risk, or whether support emails land in inbox/spam across seed mailboxes such as Gmail, Outlook, Yahoo, iCloud, QQ, or enterprise mail.
---

# Domain Email Health Auditor

## Overview

Use this skill to design, run, and report a full health audit for domains, website entry paths, payment-critical flows, and customer-service mailboxes. Treat domain health as a conversion and trust problem, not only an email problem: a domain can send mail correctly but still hurt paid conversion through slow loads, broken redirects, TLS/browser incompatibility, security warnings, blocked third-party scripts, or payment-page failures.

## Workflow

1. Collect the domain inventory.
   - Required: domain, active customer-service mailbox addresses, sending provider or SMTP source, business priority.
   - Helpful: DKIM selectors, expected MX provider, expected SPF includes, known transactional/marketing senders, recent complaints or bounce examples.
   - Use a CSV with columns: `domain,mailboxes,dkim_selectors,expected_mx,priority,notes`.

2. Run passive technical checks.
   - Use `scripts/domain_email_health_check.py` for DNS, HTTPS/TLS, redirect, email-authentication, MX, and DNSBL checks.
   - Use the detailed criteria in `references/detection-framework.md` when deciding severity and remediation.

3. Run active browser experience checks for domains that affect acquisition, login, checkout, or paid conversion.
   - Test Chrome/Chromium, Safari/WebKit, Firefox, iOS-sized and Android-sized viewports, and key geographies when possible.
   - Capture final URL, status code, redirect chain, visual screenshot, console errors, request failures, time to first byte, DOM loaded, load event, layout shifts, and payment/checkout blockers.
   - Prioritize home page, landing page, login, subscription/paywall, checkout/payment callback, and customer-support entry points.

4. Run active deliverability checks when seed inbox access is available.
   - Send controlled test mail from each real customer-service mailbox or provider route to a seed list.
   - Check inbox placement, spam placement, missing delivery, authentication result headers, latency, and URL/content warnings.
   - Keep test content realistic but neutral; include a unique run id in subject and body.

5. Score and classify.
   - Domain health: DNS, HTTP/TLS, redirect correctness, registration, blacklist, MX, and security records.
   - Web experience: browser compatibility, speed, rendering, request failures, console errors, mixed content, blocked resources, payment flow continuity.
   - Mail authentication: SPF, DKIM, DMARC, alignment, MTA-STS, TLS-RPT, BIMI.
   - Deliverability: seed inbox placement, spam placement, missing delivery, bounce rate, authentication headers, complaint/unsubscribe signals.
   - Report each domain as `Healthy`, `Watch`, `At Risk`, or `Critical`.

6. Produce an action-oriented report.
   - Lead with the domains that need action.
   - For each finding include evidence, user impact, payment/conversion risk, remediation, owner/provider, and retest method.
   - Separate "must fix before sending volume" from "best practice hardening".

## Quick Start

Create an inventory CSV:

```csv
domain,mailboxes,dkim_selectors,expected_mx,priority,notes
example.com,"support@example.com,help@example.com","selector1,selector2",Google,high,primary support domain
```

Run the passive audit:

```bash
python3 scripts/domain_email_health_check.py \
  --input domains.csv \
  --output report.json \
  --format json
```

Generate a Markdown summary:

```bash
python3 scripts/domain_email_health_check.py \
  --input domains.csv \
  --output report.md \
  --format md
```

## Active Delivery Test Design

Use active tests only with domains and mailboxes the user owns or is authorized to test.

Minimum seed panel:
- Gmail personal and Google Workspace
- Outlook/Hotmail and Microsoft 365
- Yahoo/AOL where relevant
- iCloud
- QQ/163/enterprise China mailboxes when China delivery matters
- The user's own corporate mail system

For each run:
- Generate a `run_id`, e.g. `DEHA-20260509-001`.
- Send one plain-text and one HTML email per sender route.
- Use realistic support content without promotional claims, URL shorteners, attachments, or spammy formatting.
- Wait 15, 30, and 60 minutes before final placement classification.
- Collect raw headers from delivered messages.
- Record placement as `inbox`, `promotions/other`, `spam/junk`, `quarantine`, `missing`, or `bounced`.

## Active Browser Experience Design

Use real browser checks for domains that appear in ads, app deep links, email links, checkout pages, password reset flows, or customer support flows.

Minimum browser/device matrix:
- Desktop Chromium at 1366x768 and 1440x900.
- Desktop WebKit/Safari-equivalent at 1440x900.
- Desktop Firefox at 1366x768.
- Mobile Safari-equivalent at iPhone viewport.
- Mobile Chromium at Android viewport.

For each critical URL:
- Test `http://`, `https://`, bare domain, and `www` variant.
- Verify redirect target is canonical and preserves path/query parameters.
- Capture screenshot and note visible blank pages, cookie banners blocking action, geo/language mismatch, certificate warnings, payment-provider errors, and unsupported-browser banners.
- Record TTFB, DOMContentLoaded, load event, total transferred bytes, failed requests, console errors, and third-party script failures.
- For payment paths, verify the full route to checkout/payment provider and return/callback URL without making a real payment unless explicitly authorized.

## Reporting Rules

Prioritize findings in this order:

1. Active delivery failures: missing delivery, spam placement, bounces, provider blocks.
2. Payment-path or browser failures: TLS warning, checkout unreachable, blank page, broken redirect, callback failure, unsupported browser, critical JS error.
3. Authentication failures: DMARC fail, DKIM missing/fail, SPF fail, alignment mismatch.
4. Reputation risks: DNSBL listings, compromised-looking content, browser safe-browsing warnings, newly registered domains, suspicious redirects.
5. Reliability risks: broken MX, expired TLS, missing MTA-STS/TLS-RPT, DNSSEC issues, slow or unstable page loads.
6. Best-practice improvements: BIMI, stricter DMARC policy, tighter SPF, consistent reverse DNS, security headers, canonical redirects.

Use concise language:
- `Impact`: how this affects support reachability, customer trust, or paid conversion.
- `Evidence`: exact DNS record/header/provider result.
- `Fix`: the concrete DNS/provider/mailbox change.
- `Retest`: the check to rerun after propagation.

## Resources

- `scripts/domain_email_health_check.py`: passive domain and email-authentication audit script.
- `references/detection-framework.md`: detailed checks, scoring, active seed-test design, remediation guidance, and report template.
