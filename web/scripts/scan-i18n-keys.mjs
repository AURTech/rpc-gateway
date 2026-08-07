#!/usr/bin/env node
// Ad-hoc scanner: resolve every static t()/getTranslations key against the
// English message tree (mirrors src/i18n/request.ts).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");
const localesDir = join(root, "src", "locales");
const srcDir = join(root, "src");
const PAGE_NS = ["home", "auth", "dashboard"];

function loadJson(p) {
  try {
    return JSON.parse(readFileSync(p, "utf8"));
  } catch {
    return null;
  }
}

function buildMessages(locale) {
  const common = loadJson(join(localesDir, locale, "common.json")) ?? {};
  const messages = { ...common };
  for (const ns of PAGE_NS) {
    const data = loadJson(join(localesDir, locale, `${ns}.json`));
    if (data) messages[ns] = data;
  }
  return messages;
}

function resolve(tree, dottedKey) {
  let node = tree;
  for (const seg of dottedKey.split(".")) {
    if (node && typeof node === "object" && seg in node) node = node[seg];
    else return undefined;
  }
  return node;
}

const en = buildMessages("en");

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const s = statSync(p);
    if (s.isDirectory()) {
      if (name === "node_modules" || name === ".next") continue;
      walk(p, out);
    } else if (/\.(tsx|ts)$/.test(p) && !/\.test\.tsx?$/.test(p)) {
      out.push(p);
    }
  }
  return out;
}

const files = walk(srcDir);
const missing = [];
const dynamic = [];

// var = useTranslations("ns")  OR  var = await getTranslations("ns")
const bindRe =
  /(?:const|let)\s+(\w+)\s*=\s*(?:await\s+)?(?:useTranslations|getTranslations)\(\s*(?:"([^"]*)"|'([^']*)'|`([^`]*)`)?\s*\)/g;

for (const file of files) {
  const src = readFileSync(file, "utf8");
  const vars = new Map(); // varName -> namespace
  bindRe.lastIndex = 0;
  let m = bindRe.exec(src);
  while (m) {
    vars.set(m[1], m[2] ?? m[3] ?? m[4] ?? "");
    m = bindRe.exec(src);
  }
  if (vars.size === 0) continue;

  for (const [varName, ns] of vars) {
    // literal key calls: var("a.b")  / var.rich("a.b") / var.markup("a.b")
    const callRe = new RegExp(
      `\\b${varName}(?:\\.rich|\\.markup)?\\(\\s*(?:"([^"]+)"|'([^']+)')`,
      "g",
    );
    let c = callRe.exec(src);
    while (c) {
      const key = c[1] ?? c[2];
      const full = ns ? `${ns}.${key}` : key;
      const inEn = resolve(en, full) !== undefined;
      if (!inEn) {
        const miss = [];
        if (!inEn) miss.push("en");
        missing.push({ file: file.replace(`${root}/`, ""), full, miss });
      }
      c = callRe.exec(src);
    }
    // dynamic template-literal keys: var(`...${...}`)
    const dynRe = new RegExp(
      `\\b${varName}(?:\\.rich|\\.markup)?\\(\\s*\``,
      "g",
    );
    while (dynRe.exec(src)) {
      dynamic.push({ file: file.replace(`${root}/`, ""), ns });
    }
  }
}

// de-dup
const seen = new Set();
const uniqMissing = missing.filter((x) => {
  const k = `${x.file}|${x.full}|${x.miss.join(",")}`;
  if (seen.has(k)) return false;
  seen.add(k);
  return true;
});

console.log(`\n=== MISSING KEYS (${uniqMissing.length}) ===`);
for (const x of uniqMissing.sort((a, b) => a.full.localeCompare(b.full))) {
  console.log(`  [${x.miss.join("+")}] ${x.full}   <- ${x.file}`);
}

const dynFiles = [...new Set(dynamic.map((d) => `${d.file} (ns="${d.ns}")`))];
console.log(
  `\n=== DYNAMIC KEYS — not statically checkable (${dynFiles.length} files) ===`,
);
for (const f of dynFiles.sort()) console.log(`  ${f}`);
console.log("");
