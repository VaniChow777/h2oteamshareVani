---
name: quiz-funnel-extractor
description: Use when the user gives a competitor quiz funnel webpage URL and wants the quiz questions, branching logic, sales funnel, pricing model, upsells, or a readable funnel teardown extracted from the site.
---

# Quiz Funnel Extractor

Use this skill for one competitor funnel URL. The goal is to produce both machine-readable data and human-readable product analysis.

## Workflow

1. Create an output folder named after the host/path under the current workspace.
2. Fetch the page HTML with `curl -L -s`, quoting URLs with query strings.
3. Check for embedded app state:
   - Next.js: `<script id="__NEXT_DATA__" type="application/json">`
   - Nuxt/Astro/Remix/custom globals: search `__NUXT__`, `window.__`, `quiz`, `funnel`, `question`, `planSet`, `checkout`.
4. If app state exists, parse it first. Prefer structured JSON over browser clicking.
5. Extract:
   - first page / landing-page choices
   - ordered quiz steps
   - question ids, titles, types, answer options
   - condition variables and branch predicates
   - post-quiz commercial routes
   - sales variables used in email/purchase/checkout/upsell pages
6. Download relevant JS chunks only when app state is insufficient. Use `_buildManifest.js` or script tags to find page chunks, then search for API endpoints and plan/pricing logic.
7. For pricing, identify sales funnel id, plan set ids, plan ids, country/region pricing, intro/trial/renewal/downsell/upsell roles, and payment methods.
8. Produce outputs:
   - raw HTML and raw JSON/API files
   - `*_steps.csv`
   - `*_branches.csv`
   - `*_sales_pages.csv`
   - `*_sales_variables.csv`
   - `*_pricing.csv`
   - `*_readable_quiz_map.md`
   - `*_readable_pricing_model.md`
   - `*_competitor_analysis.md`

## Recommended Script

Use `scripts/extract_next_quiz_funnel.mjs` as a starting point for Next.js/BetterMe-like funnels:

```bash
node scripts/extract_next_quiz_funnel.mjs \
  'https://example.com/first-page?flow=1234' \
  output/example-flow
```

The script is intentionally conservative. Patch or extend it inside the working project when a site has a different schema.

## Analysis Rules

- Do not treat every answer option as a branch. A branch exists only when a downstream page/variable condition references the answer.
- Separate quiz branching from copy personalization. Many funnels keep the path linear while swapping titles, testimonials, and checkout bullets.
- Mark inferred behavior clearly when it comes from frontend code rather than a completed browser path.
- Pricing is often region-sensitive. Record country/currency exactly as returned by the API and avoid generalizing it globally.
- For checkout, distinguish:
  - main subscription plans
  - trial or intro pricing
  - additional discount/dobivashka plans
  - downsell plans
  - subscription upsells
  - one-time content upsells
  - e-commerce/hardware upsells

## Readable Output Pattern

The readable quiz report should include:

- one-sentence structure
- Mermaid overview
- stage map table
- key branch driver(s)
- branch difference table
- compressed step order
- conversion mechanics and reusable patterns

The readable pricing report should include:

- main price ladder table
- discount/downsell ladder
- post-purchase upsell map
- subscription vs one-time vs hardware separation
- region/currency caveats

## When Browser Automation Is Needed

Use browser automation only after static/app-state extraction fails or when validating final rendered behavior. Avoid brute-force clicking all answer combinations unless the site hides state and no structured config can be found.
