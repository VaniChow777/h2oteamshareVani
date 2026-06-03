#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";

const args = process.argv.slice(2);
if (args.length < 3) {
  console.error("Usage: compare_extracted_funnels.mjs <funnelDir...> <outDir>");
  process.exit(2);
}

const outDir = path.resolve(args.at(-1));
const funnelDirs = args.slice(0, -1).map((p) => path.resolve(p));
await fs.mkdir(outDir, { recursive: true });

function csvEscape(value) {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function toCsv(rows, headers) {
  return [headers.map(csvEscape).join(","), ...rows.map((r) => headers.map((h) => csvEscape(r[h])).join(","))].join("\n");
}

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  if (!lines.length) return [];
  const parseLine = (line) => {
    const out = [];
    let cur = "";
    let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const c = line[i];
      if (c === '"' && line[i + 1] === '"') {
        cur += '"';
        i += 1;
      } else if (c === '"') {
        quoted = !quoted;
      } else if (c === "," && !quoted) {
        out.push(cur);
        cur = "";
      } else {
        cur += c;
      }
    }
    out.push(cur);
    return out;
  };
  const headers = parseLine(lines[0]);
  return lines.slice(1).map((line) => Object.fromEntries(headers.map((h, i) => [h, parseLine(line)[i] ?? ""])));
}

async function readCsvIfExists(dir, names) {
  for (const name of names) {
    try {
      return parseCsv(await fs.readFile(path.join(dir, name), "utf8"));
    } catch {}
  }
  return [];
}

const matrix = [];
const pricingSummaries = [];
for (const dir of funnelDirs) {
  const steps = await readCsvIfExists(dir, ["steps.csv", "betterme_flow_1416_steps.csv"]);
  const branches = await readCsvIfExists(dir, ["branches.csv", "betterme_flow_1416_branches.csv"]);
  const salesPages = await readCsvIfExists(dir, ["sales_pages.csv", "betterme_flow_1416_sales_pages.csv"]);
  const pricing = await readCsvIfExists(dir, ["pricing.csv", "betterme_flow_1416_pricing.csv"]);
  const mainPlans = pricing.filter((r) => r.role === "main");
  const preselected = mainPlans.find((r) => r.preselected === "1" || /most popular/i.test(r.plan_set_label || ""));
  matrix.push({
    funnel: path.basename(dir),
    total_steps: steps.length,
    questions: steps.filter((r) => r.type === "QUESTION").length,
    info_pages: steps.filter((r) => r.type === "INFO_PAGE").length,
    loaders: steps.filter((r) => r.type === "LOADER").length,
    conditional_steps: branches.length,
    commercial_pages: salesPages.map((r) => r.url).filter(Boolean).join(" -> "),
    main_plan_count: mainPlans.length,
    default_plan: preselected ? `${preselected.ui_name_female || preselected.plan_name} ${preselected.introductory_price || preselected.discounted_price}` : "",
    currencies: [...new Set(pricing.map((r) => r.currency).filter(Boolean))].join(" | "),
    upsell_roles: [...new Set(pricing.map((r) => r.role).filter((r) => r && r !== "main"))].join(" | "),
  });
  pricingSummaries.push({
    funnel: path.basename(dir),
    mainPlans,
    pricing,
    currencies: [...new Set(pricing.map((r) => r.currency).filter(Boolean))],
    upsellRoles: [...new Set(pricing.map((r) => r.role).filter((r) => r && r !== "main"))],
  });
}

const headers = Object.keys(matrix[0] || { funnel: "" });
await fs.writeFile(path.join(outDir, "funnel_comparison_matrix.csv"), toCsv(matrix, headers), "utf8");

const md = `# Quiz Funnel Comparison

## Matrix

${matrix.map((row) => `- ${row.funnel}: ${row.total_steps} steps, ${row.questions} questions, ${row.conditional_steps} conditional steps, ${row.main_plan_count} main plans, default ${row.default_plan || "unknown"}`).join("\n")}

## Next Analysis Prompts

- Which funnel has the fewest questions before email capture?
- Which branch driver affects the most downstream copy or pages?
- Which funnel has the clearest price ladder?
- Which funnel uses the most aggressive downsell?
- Which upsells are subscription vs one-time?
`;

await fs.writeFile(path.join(outDir, "quiz_flow_comparison.md"), md, "utf8");

const pricingMd = `# Pricing Model Comparison

## Main Plan Ladder

${pricingSummaries.map((summary) => {
  if (!summary.mainPlans.length) return `### ${summary.funnel}\n\nNo main subscription plans found in the available pricing CSV.`;
  const lines = summary.mainPlans.map((plan) => {
    const label = plan.plan_set_label || plan.plan_name || plan.ui_name_female || plan.plan_set_id || "plan";
    const intro = plan.introductory_price || plan.discounted_price || "";
    const recurring = plan.full_price || plan.raw_price || "";
    const marker = plan.preselected === "1" || /most popular/i.test(plan.plan_set_label || "") ? " (default)" : "";
    return `- ${label}${marker}: ${intro}${recurring && recurring !== intro ? ` -> ${recurring}` : ""}`;
  }).join("\n");
  return `### ${summary.funnel}\n\n${lines}`;
}).join("\n\n")}

## Upsell And Discount Roles

${pricingSummaries.map((summary) => {
  const roles = summary.upsellRoles.length ? summary.upsellRoles.join(", ") : "none found";
  const currencies = summary.currencies.length ? summary.currencies.join(", ") : "unknown";
  return `- ${summary.funnel}: currencies ${currencies}; roles ${roles}`;
}).join("\n")}
`;

await fs.writeFile(path.join(outDir, "pricing_model_comparison.md"), pricingMd, "utf8");
console.log(JSON.stringify({ ok: true, outDir, funnels: matrix.length }, null, 2));
