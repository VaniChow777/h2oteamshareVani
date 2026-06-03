---
name: quiz-funnel-compare
description: Use when the user gives multiple competitor quiz funnel URLs or extracted funnel folders and wants a side-by-side comparison of quiz flow, branch logic, pricing model, upsells, and conversion patterns.
---

# Quiz Funnel Compare

Use this skill for two or more competitor funnels. It depends on the standard outputs from `quiz-funnel-extractor` when URLs have not already been extracted.

## Input Types

Accept either:

- URLs to competitor quiz funnels
- folders containing extractor outputs such as `steps.csv`, `branches.csv`, `sales_pages.csv`, `sales_variables.csv`, and `pricing.csv`
- a mix of both

If URLs are provided, first use `quiz-funnel-extractor` on each URL and store each extraction in a separate folder.

## Comparison Workflow

1. Normalize each funnel into a named folder with standard files.
2. Build a comparison matrix:
   - entry/first page
   - total quiz steps
   - question count
   - information/trust page count
   - loader count
   - branch drivers
   - major branch variants
   - email capture placement
   - commercial route chain
   - main plan ladder
   - default selected plan
   - intro/trial/downsell strategy
   - upsell types
   - payment methods and region/currency
3. Produce readable outputs:
   - `quiz_flow_comparison.md`
   - `pricing_model_comparison.md`
   - `funnel_comparison_matrix.csv`
   - optional Mermaid diagrams for side-by-side funnel skeletons
4. End with a product-strategy summary:
   - what is common across competitors
   - which competitor has the strongest personalization
   - which price model is most aggressive
   - which ideas are reusable for the user's product

## Recommended Script

Use `scripts/compare_extracted_funnels.mjs` once each funnel has an extracted folder:

```bash
node scripts/compare_extracted_funnels.mjs \
  output/funnel-a output/funnel-b output/comparison
```

The script creates a baseline matrix. Add narrative analysis manually after checking the CSVs.

## Comparison Principles

- Compare structure before details. A 60-step flow and a 20-step flow may use the same psychological sequence.
- Separate true branching from copy personalization.
- Normalize prices by role, not only displayed price:
  - main subscription
  - intro/trial
  - additional discount
  - downsell
  - subscription upsell
  - one-time upsell
  - hardware/e-commerce upsell
- Keep country/currency caveats visible.
- Do not claim a competitor has no branch or no upsell unless the extraction method covered app state, chunks, and sales APIs sufficiently.

## Final Answer Shape

For the user, lead with:

1. the biggest structural difference
2. the biggest price-model difference
3. the most reusable conversion idea
4. links to generated comparison files
