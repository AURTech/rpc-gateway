#!/usr/bin/env node
/**
 * lint-no-arbitrary-tw — blocks regression of arbitrary Tailwind values
 * that should use named tokens instead. Run as part of `pnpm lint`; biome
 * can't lint inside Tailwind class strings, so this is a focused supplement.
 *
 * Patterns flagged:
 *   - rounded-[Npx]           → use rounded-sm/md/lg/xl/2xl/full
 *   - text-[Npx]              → use text-2xs..4xl
 *   - bg-[#hex]               → use a token (bg-good-tint etc.)
 *   - long brand tint var backgrounds → use bg-brand-tint-5/8/10
 *   - shadow-[var(--shadow-*)]→ use shadow-card/cta/pill/detail
 *   - radius var arbitrary values → use rounded-sm/md/lg/xl/2xl/full
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");
const srcDir = join(root, "src");

const RULES = [
  /* —— Existing rules —— */
  {
    name: "rounded-arbitrary",
    regex: /\brounded-\[/,
    hint: "use rounded-sm/md/lg/xl/2xl/full or a custom radius token in globals.css @theme",
  },
  {
    name: "text-px-arbitrary",
    regex: /\btext-\[\d+(?:\.\d+)?(?:px|rem|em)?\]/,
    hint: "use text-2xs/xs/sm/base/md/lg/xl/2xl/3xl/4xl or add a typography token in @theme",
  },
  {
    name: "bg-hex-arbitrary",
    regex: /\bbg-\[#[0-9a-fA-F]{3,8}\]/,
    hint: "register a semantic color in @theme and use the utility (e.g. bg-accent)",
  },
  {
    name: "bg-brand-tint-long",
    regex: /\bbg-\[color:var\(--brand-tint-/,
    hint: "use bg-brand-tint-5/8/10 (defined in globals.css @theme)",
  },
  {
    name: "shadow-var-arbitrary",
    regex: /\bshadow-\[var\(--shadow-/,
    hint: "use a named shadow utility (e.g. shadow-sidebar/section/action) defined in @theme",
  },
  {
    name: "rounded-var-arbitrary",
    regex: /\brounded-\[var\(--radius-/,
    hint: "use rounded-sm/md/lg/xl/2xl/3xl/full or a named radius (rounded-sidebar/section/nav/pill)",
  },

  /* —— Phase D+ — extended coverage aligned with uix skill standards —— */
  {
    name: "spacing-arbitrary",
    regex:
      /\b(?:gap|gap-x|gap-y|space-x|space-y|p|pt|pr|pb|pl|px|py|m|mt|mr|mb|ml|mx|my)-\[\d/,
    hint: "use Tailwind named spacing (gap-2, p-4, mt-6) or add a --spacing-* token in @theme",
  },
  {
    name: "sizing-arbitrary",
    regex: /\b(?:w|h|min-w|max-w|min-h|max-h)-\[\d/,
    hint: "use Tailwind named sizing (w-64, max-w-prose) or add a --width-* / --height-* token in @theme",
  },
  {
    name: "tracking-arbitrary",
    regex: /\btracking-\[/,
    hint: "use tracking-tight/normal/wide/wider or set letter-spacing on a typography token",
  },
  {
    name: "leading-arbitrary",
    regex: /\bleading-\[/,
    hint: "use leading-none/tight/snug/normal/relaxed or set --text-*--line-height in @theme",
  },
  {
    name: "border-px-arbitrary",
    regex: /\bborder-\[\d+(?:\.\d+)?px\]/,
    hint: "this console is borderless — drop the border or use a registered token",
  },
  {
    name: "bg-var-arbitrary",
    regex: /\bbg-\[(?:color:)?var\(--/,
    hint: "register the color in @theme (e.g. --color-accent), then use the utility (bg-accent)",
  },
  {
    name: "text-color-var-arbitrary",
    regex: /\btext-\[(?:color:)?var\(--/,
    hint: "register the color in @theme (e.g. --color-ink-700), then use the utility (text-ink-700)",
  },
  {
    name: "font-arbitrary",
    regex: /\bfont-\[(?:'|"|var)/,
    hint: "register the font stack/weight in @theme, then use the utility (font-sans, font-semibold)",
  },
];

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      if (entry === "node_modules" || entry.startsWith(".")) continue;
      yield* walk(full);
    } else if (
      st.isFile() &&
      (full.endsWith(".tsx") || full.endsWith(".ts")) &&
      !full.endsWith(".d.ts")
    ) {
      yield full;
    }
  }
}

const violations = [];
for (const file of walk(srcDir)) {
  const rel = relative(root, file);
  const lines = readFileSync(file, "utf8").split("\n");
  for (let i = 0; i < lines.length; i++) {
    for (const rule of RULES) {
      if (rule.regex.test(lines[i])) {
        violations.push({
          file: rel,
          line: i + 1,
          rule: rule.name,
          hint: rule.hint,
          excerpt: lines[i].trim().slice(0, 120),
        });
      }
    }
  }
}

if (violations.length === 0) {
  console.log("lint-no-arbitrary-tw: 0 violations");
  process.exit(0);
}

console.error(
  `lint-no-arbitrary-tw: ${violations.length} violation${
    violations.length === 1 ? "" : "s"
  }`,
);
for (const v of violations) {
  console.error(`\n  ${v.file}:${v.line}  [${v.rule}]`);
  console.error(`    ${v.excerpt}`);
  console.error(`    → ${v.hint}`);
}
process.exit(1);
