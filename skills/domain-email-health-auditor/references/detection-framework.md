# Domain And Email Health Detection Framework

## Scope

Audit domains that are already in use, especially domains that host customer-service mailboxes, acquisition landing pages, app deep links, checkout/payment pages, password reset links, or support flows. Separate evidence into passive posture checks, active browser experience checks, and active deliverability checks.

## Passive Checks

### Domain And DNS Health

- DNS resolution: A/AAAA, NS, SOA, CNAME loops, lame delegation, inconsistent answers.
- Registration/RDAP: registrar, creation date, expiry date, status locks, nameserver changes.
- DNSSEC: DS and DNSKEY presence, validation state where tooling supports it.
- CAA: expected certificate authorities, overly broad or missing records.
- HTTP/HTTPS: HTTP reachability, redirect chain, final host, canonical `www`/bare-domain behavior, path/query preservation, certificate CN/SAN coverage, issuer, expiry, TLS handshake.
- Reputation surface: Google Safe Browsing or equivalent if credentials are available, URL redirects, parked-domain pages, malware warnings.

### Web Experience And Payment Risk

- Browser compatibility: compare Chromium, WebKit/Safari, Firefox, mobile Safari-like viewport, and mobile Chromium viewport.
- Load reliability: status code, final URL, redirect count, TTFB, DOMContentLoaded, load event, request failures, console errors, blank screen, hydration/runtime errors.
- TLS/browser trust: certificate warnings, outdated TLS, mixed content, HSTS issues, insecure form posts, blocked third-party scripts.
- Rendering: above-the-fold content visible, primary CTA visible/clickable, language/geo correct, cookie banner not blocking checkout, layout not broken on mobile.
- Payment path: subscription/paywall loads, checkout button works, payment provider opens, return/callback URL resolves, query parameters and attribution survive redirects.
- Analytics and attribution: campaign parameters survive redirects, app/web attribution scripts load, blocked analytics does not block checkout.
- Regional behavior: CDN edge consistency, Great Firewall or regional DNS issues where China traffic matters, payment provider availability by market.

Treat these as conversion risks even when email authentication is perfect. A domain with valid MX/SPF/DKIM can still reduce paid conversion if users see browser warnings, slow loading, blank pages, or payment callback failures.

### Mail Routing

- MX presence and priority order.
- MX host resolution.
- SMTP reachability where network policy allows it.
- STARTTLS advertisement and TLS certificate validity.
- Expected provider match, e.g. Google Workspace, Microsoft 365, Zendesk, Intercom, Freshdesk, Help Scout, self-hosted.

### SPF

- Exactly one SPF record at the root domain.
- Includes all legitimate senders and excludes unknown legacy senders.
- Ends with `-all` or `~all`; `+all` is critical.
- Stays under the 10-DNS-lookup limit after expansion.
- Avoids broad `include` and `ip4/ip6` ranges unless justified.

### DKIM

- Check all known selectors supplied by the user.
- Common selectors to try when unknown: `default`, `selector1`, `selector2`, `google`, `k1`, `s1`, `s2`, `mail`, `smtp`, `zendesk1`, `zendesk2`.
- Confirm key record exists, is TXT/CNAME as provider expects, and uses a sufficiently strong key.
- Active delivery headers are the source of truth for DKIM pass/fail and alignment.

### DMARC

- `_dmarc.<domain>` exists.
- Policy starts at least `p=none` for monitoring; mature sender domains should move toward `quarantine` or `reject`.
- `rua` exists for aggregate reports when the organization can process them.
- Alignment (`adkim`, `aspf`) matches the sender architecture.
- Subdomain policy (`sp`) is explicit for domains with many delegated subdomains.

### MTA-STS And TLS-RPT

- `_mta-sts.<domain>` TXT exists with `v=STSv1; id=...`.
- `https://mta-sts.<domain>/.well-known/mta-sts.txt` is reachable and valid.
- `_smtp._tls.<domain>` TXT exists with `v=TLSRPTv1; rua=...`.
- Missing records are usually medium severity; broken records can be high severity because they create false confidence.

### BIMI

- `default._bimi.<domain>` TXT exists only after DMARC enforcement is ready.
- SVG logo and VMC/CMC certificate are valid where required by target providers.
- Treat BIMI as brand-trust hardening, not a substitute for inbox-placement testing.

### Blacklists And Reverse DNS

- Resolve outbound sending IPs from provider dashboards or message headers.
- Check common DNSBL zones such as Spamhaus, Barracuda, SpamCop, SORBS, and UCEPROTECT with caution; false positives happen.
- Confirm PTR/rDNS and HELO/EHLO identity for self-hosted mail servers.
- Provider-shared IP listings require provider escalation, not only DNS changes.

## Active Deliverability Checks

### Seed Panel

Use provider coverage that matches the customer base:

- US/global: Gmail, Google Workspace, Outlook/Hotmail, Microsoft 365, Yahoo/AOL, iCloud.
- China: QQ Mail, 163/126, Tencent Enterprise Mail, Alibaba Enterprise Mail, Feishu/Lark Mail where relevant.
- B2B: at least one strict corporate gateway or security appliance mailbox if available.

### Send Matrix

For each domain and mailbox:

- Send from real support mailbox via its normal sending path.
- Send plain text and HTML variants.
- Include a unique subject marker: `[Deliverability Test <run_id>]`.
- Avoid attachments unless attachment delivery is part of the support workflow.
- Include the same support-domain links users normally receive.
- Keep volume low and controlled to avoid creating the very reputation issue being measured.

### Collection

For each seed inbox, record:

- Provider, mailbox, folder placement, delivery timestamp, latency.
- Raw headers: `Authentication-Results`, `Received-SPF`, `DKIM-Signature`, `DMARC`, `ARC`, `X-Forefront-Antispam-Report`, Gmail category labels where available.
- Spam reason or banner text when shown.
- Bounce DSN if delivery fails.

### Placement Classification

- `inbox`: primary inbox or equivalent default inbox.
- `secondary`: promotions, updates, other, focused/other split.
- `spam`: spam/junk folder.
- `quarantine`: admin quarantine or security hold.
- `missing`: not found after 60 minutes and no bounce.
- `bounced`: rejected with DSN or SMTP error.

## Active Browser Experience Checks

### URL Matrix

For each important domain, test:

- `https://domain/`
- `http://domain/`
- `https://www.domain/`
- `http://www.domain/`
- Known landing pages, app deep-link landing pages, login, reset password, pricing/paywall, checkout, payment return/callback, support/contact pages.

### Browser Matrix

Minimum:

- Chromium desktop.
- WebKit/Safari-equivalent desktop.
- Firefox desktop.
- Mobile Safari-equivalent viewport.
- Mobile Chromium viewport.

Add real devices or cloud device testing when Safari/iOS or Android WebView traffic is material.

### Evidence To Capture

- Screenshot after page settles.
- Final URL, redirect chain, status code, and whether path/query parameters survived.
- Timing: TTFB, DOMContentLoaded, load event, largest resource hints if available.
- Console errors and page errors.
- Failed network requests and blocked third-party resources.
- Security warnings, mixed-content warnings, certificate errors, CSP errors.
- Payment path state: payment provider loaded, checkout token/session created, callback route reachable.

### Classification

- `pass`: page loads, renders, and primary action is available.
- `degraded`: page loads but slow, has non-critical console errors, or secondary resources fail.
- `conversion-risk`: primary CTA, paywall, checkout, app link, attribution, or payment provider has a visible or functional issue.
- `blocked`: TLS warning, browser block, blank page, 4xx/5xx, infinite redirect, or checkout/payment cannot proceed.

## Scoring

Start from 100 per domain.

- Critical active failure: -30 each, e.g. Gmail/Outlook spam or missing for primary support mailbox.
- Critical browser/payment failure: -30 each, e.g. TLS warning, blank checkout page, payment provider unreachable, broken callback, infinite redirect.
- Conversion-risk browser issue: -15 each, e.g. primary CTA missing on mobile, query parameters lost, severe console error, critical third-party script blocked.
- Authentication fail: -25 each, e.g. DMARC fail, DKIM fail, SPF fail on active headers.
- Missing core authentication: -15 each, e.g. no DMARC, no DKIM for active sender, multiple SPF records.
- DNS/MX breakage: -20 each, e.g. no MX, MX host unresolved, expired support-domain TLS cert.
- Reputation listing: -10 to -30 depending on source credibility and sending IP ownership.
- Web performance/reliability gap: -5 to -15 each, depending on page criticality and repeatability.
- Weak policy/hardening gap: -3 to -8 each, e.g. DMARC `p=none`, missing TLS-RPT, missing BIMI.

Classification:

- `Healthy`: 85-100, no critical findings.
- `Watch`: 70-84, no active failure, some hardening gaps.
- `At Risk`: 50-69, authentication or reputation issue likely to affect delivery.
- `Critical`: below 50, any primary support mailbox missing/spam/bounced at Gmail or Outlook, or any checkout/payment-critical path is blocked.

## Remediation Playbook

- Multiple SPF records: merge into one record and retest TXT lookup.
- SPF lookup overflow: flatten only when managed, remove unused includes, or shift senders to DKIM alignment.
- DKIM missing: enable DKIM in sender provider, publish selector records, wait for DNS propagation, send seed test.
- DMARC missing: publish monitoring policy with `rua`, then tighten after alignment is proven.
- DMARC fail: fix From-domain alignment; do not hide the issue by weakening policy permanently.
- MX mismatch: confirm whether support mailbox is hosted by the expected provider, then correct MX priority and routing.
- Spam placement with pass authentication: inspect content, links, sender reputation, complaint history, and seed provider-specific headers.
- DNSBL listing: identify whether listed IP is dedicated or shared, request delisting or provider migration, then retest active delivery.
- Expired TLS: renew certificate, confirm full chain, and retest HTTPS plus SMTP STARTTLS where applicable.
- Broken canonical redirect: choose canonical host, preserve path/query parameters, avoid redirect chains longer than two hops, and retest ad/app/email URLs.
- Browser-specific blank page: inspect console/page errors in the failing engine, usually WebKit/Safari for storage, CSP, syntax, media, or third-party-cookie differences.
- Slow landing page: reduce blocking JS, optimize CDN caching, compress images, preconnect payment/CDN origins, and retest by market and device.
- Payment callback failure: verify allowed domains in payment provider settings, HTTPS certificate, callback route, query signature preservation, and app/web handoff logic.
- Lost attribution parameters: preserve UTM/click IDs through all redirects and app-link handoffs; verify analytics scripts do not block checkout.

## Report Template

```markdown
# Domain Email Health Audit

## Executive Summary

- Domains audited:
- Customer-service mailboxes audited:
- Critical domains:
- At-risk domains:
- Main cross-domain pattern:

## Priority Findings

| Severity | Domain | Area | Finding | Evidence | User/Payment Impact | Fix | Retest |
|---|---|---|---|---|---|---|

## Domain Scorecard

| Domain | Score | Status | DNS | Web/TLS | Browser UX | Payment Path | Email Auth | MX | Reputation | Active Delivery |
|---|---:|---|---|---|---|---|---|---|---|---|

## Browser Experience Matrix

| URL | Browser/Device | Final URL | Status | Load | Console/Request Errors | Screenshot | Classification |
|---|---|---|---:|---:|---|---|---|

## Active Delivery Matrix

| Sender | Seed Provider | Placement | Auth Result | Latency | Notes |
|---|---|---|---|---:|---|

## Remediation Plan

| Priority | Owner | Action | Expected Effect | Due | Retest Method |
|---|---|---|---|---|---|
```
