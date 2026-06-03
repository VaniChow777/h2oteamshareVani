#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";

const [url, outDirArg = "output/quiz-funnel"] = process.argv.slice(2);
if (!url) {
  console.error("Usage: extract_next_quiz_funnel.mjs <url> [outDir]");
  process.exit(2);
}

const outDir = path.resolve(outDirArg);
await fs.mkdir(outDir, { recursive: true });

function csvEscape(value) {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function toCsv(rows, headers) {
  return [headers.map(csvEscape).join(","), ...rows.map((r) => headers.map((h) => csvEscape(r[h])).join(","))].join("\n");
}

function stripMarkup(value) {
  return String(value ?? "")
    .replace(/\[themeColor\|[^|\]]+\|([^\]]+)\]/g, "$1")
    .replace(/\[typography\|[^|\]]+\|[^|\]]*\|([^\]]+)\]/g, "$1 ")
    .replace(/\[successStoryDisclaimer\|([^\]]+)\]/g, "$1")
    .replace(/\[b\|([^\]]+)\]/g, "$1")
    .replace(/\[([^|\]]+)\|[^\]]+\]/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

async function fetchText(targetUrl) {
  const res = await fetch(targetUrl, { redirect: "follow" });
  if (!res.ok) throw new Error(`${res.status} ${targetUrl}`);
  return await res.text();
}

function findNextData(html) {
  const match = html.match(/<script id="__NEXT_DATA__" type="application\/json">([\s\S]*?)<\/script>/);
  return match ? JSON.parse(match[1]) : null;
}

function findQuizStructure(obj) {
  const seen = new Set();
  const candidates = [];
  function walk(value, p) {
    if (!value || typeof value !== "object" || seen.has(value)) return;
    seen.add(value);
    if (Array.isArray(value)) {
      const score = value.reduce((n, item) => n + (item && typeof item === "object" && (item.questionId || item.answerOptions || item.type === "QUESTION") ? 1 : 0), 0);
      if (score >= 3) candidates.push({ path: p, value, score });
      value.forEach((v, i) => walk(v, `${p}[${i}]`));
    } else {
      for (const [k, v] of Object.entries(value)) walk(v, `${p}.${k}`);
    }
  }
  walk(obj, "$");
  candidates.sort((a, b) => b.score - a.score);
  return candidates[0] || null;
}

function answerMap(structure) {
  const map = new Map();
  for (const page of structure) {
    for (const answer of page.answerOptions || []) {
      map.set(answer.id, { ...answer, questionId: page.questionId });
    }
  }
  return map;
}

function conditionText(cv, answers) {
  if (!cv) return "";
  return (cv.cases || []).map((c) => {
    const clauses = (c.conditions || []).map((cond) => {
      if (cond.type === "question") {
        const a = answers.get(cond.answerId);
        return `Q${cond.questionId} = ${a?.title || cond.answerId}`;
      }
      if (cond.type === "page") return `page ${cond.pageId} card ${cond.cardIndex}`;
      return JSON.stringify(cond);
    });
    return `${clauses.join(" AND ") || "default"} => ${c.value}`;
  }).join("; ");
}

const html = await fetchText(url);
await fs.writeFile(path.join(outDir, "page.html"), html, "utf8");

const nextData = findNextData(html);
if (!nextData) {
  await fs.writeFile(path.join(outDir, "README.md"), `No __NEXT_DATA__ found. Search raw HTML and JS chunks manually.\nSource: ${url}\n`, "utf8");
  console.log(JSON.stringify({ ok: false, reason: "No __NEXT_DATA__", outDir }, null, 2));
  process.exit(0);
}

await fs.writeFile(path.join(outDir, "next_data.json"), JSON.stringify(nextData, null, 2), "utf8");

const initialState = nextData.props?.pageProps?.initialState || nextData.props?.pageProps || {};
const quizCandidate = findQuizStructure(initialState);
if (!quizCandidate) {
  console.log(JSON.stringify({ ok: false, reason: "No quiz-like array found", outDir }, null, 2));
  process.exit(0);
}

const structure = quizCandidate.value;
const answers = answerMap(structure);
const steps = structure.map((page, index) => ({
  index: index + 1,
  key: page.key || "",
  page_id: page.id || "",
  question_id: page.questionId || "",
  type: page.type || "",
  question_type: page.questionType || "",
  title: stripMarkup(page.pageTitle || page.title || ""),
  condition: conditionText(page.conditionVariable, answers),
  answer_count: (page.answerOptions || []).length,
  answers: (page.answerOptions || []).map((a) => `${a.order || ""}. ${a.title}${a.isNoneAnswer ? " [none]" : ""}`).join(" | "),
  analytics_event: page.analyticsEvent || page.data?.analyticsEvent || "",
  schema: page.schemaName || page.innerType || "",
}));

await fs.writeFile(path.join(outDir, "steps.csv"), toCsv(steps, Object.keys(steps[0])), "utf8");

const branches = structure.filter((p) => p.conditionVariable).map((page) => ({
  index: structure.indexOf(page) + 1,
  question_id: page.questionId || "",
  title: stripMarkup(page.pageTitle || page.title || ""),
  condition: conditionText(page.conditionVariable, answers),
}));
if (branches.length) await fs.writeFile(path.join(outDir, "branches.csv"), toCsv(branches, Object.keys(branches[0])), "utf8");

const generatedSaleFunnel = initialState.generatedSaleFunnel || {};
const salesPages = (generatedSaleFunnel.pagesInfo || []).map((page) => ({
  order: page.pageOrder,
  id: page.id,
  page_id: page.pageId || "",
  url: page.pageUrl,
  page_type: page.pageType || "",
  page_tag: page.pageTag || "",
  variable_count: (page.variables || []).length,
  variable_names: (page.variables || []).map((v) => v.name).join(" | "),
}));
if (salesPages.length) await fs.writeFile(path.join(outDir, "sales_pages.csv"), toCsv(salesPages, Object.keys(salesPages[0])), "utf8");

const typeCounts = steps.reduce((acc, row) => {
  acc[row.type || "UNKNOWN"] = (acc[row.type || "UNKNOWN"] || 0) + 1;
  return acc;
}, {});

const md = `# Quiz Funnel Extraction

Source: ${url}

## Summary

- Quiz structure path: \`${quizCandidate.path}\`
- Steps: ${steps.length}
- Step types: ${Object.entries(typeCounts).map(([k, v]) => `${k} ${v}`).join(", ")}
- Conditional steps: ${branches.length}
- Sales pages: ${salesPages.length}

## Next Actions

- Read \`steps.csv\` for full question/answer flow.
- Read \`branches.csv\` for branch logic.
- Read \`sales_pages.csv\` for post-quiz commercial routes.
- If pricing is missing, inspect JS chunks for plan-set APIs and fetch plan data.
`;
await fs.writeFile(path.join(outDir, "extraction_summary.md"), md, "utf8");

console.log(JSON.stringify({ ok: true, outDir, steps: steps.length, branches: branches.length, salesPages: salesPages.length }, null, 2));
