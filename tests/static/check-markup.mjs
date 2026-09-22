// Checks the chat page's text rendering: app/static/app.js turns the model's
// answer into HTML, and that is the one place in the product where a string
// from an LLM reaches innerHTML. Run it with:
//
//     node tests/static/check-markup.mjs
//
// The helpers live inside app.js's IIFE and touch no DOM, so they are lifted
// out textually and evaluated here. That is deliberate: checking a copy of the
// regexes would pass while the shipped file was broken, which is exactly the
// failure this file exists to catch (a newline that landed inside the
// double-asterisk regex made the whole script a syntax error, and every
// server-side test still passed).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const APP_JS = path.join(here, "..", "..", "app", "static", "app.js");
const src = fs.readFileSync(APP_JS, "utf8").split("\r\n").join("\n");

function grab(startMarker, endMarker) {
  const start = src.indexOf(startMarker);
  if (start === -1) throw new Error("not found in app.js: " + startMarker);
  const end = src.indexOf(endMarker, start);
  if (end === -1) throw new Error("end not found for: " + startMarker);
  return src.slice(start, end + endMarker.length);
}

const helpers = new Function(
  [
    grab("function escapeHtml(text) {", "\n  }"),
    grab("var LINK_PATTERN =", ";\n"),
    grab("function linkify(html) {", "\n  }"),
    grab("function formatMarkup(text) {", "\n  }"),
    "return { formatMarkup: formatMarkup };",
  ].join("\n")
)();

// [input, must contain, must not contain (null to skip)]
const CASES = [
  // The chat model writes standard Markdown; the web channel has no
  // equivalent of whatsapp._to_whatsapp_markdown(), so it must render it.
  ["El menú val **23,90 €** per persona.", "<strong>23,90 €</strong>", "**"],
  // WhatsApp's own single-asterisk syntax still works.
  ["Text amb *negreta* de WhatsApp.", "<strong>negreta</strong>", "*negreta*"],
  ["_cursiva_ i ~ratllat~", "<em>cursiva</em>", null],
  // Bold and a link in one line: neither pass may eat the other's output.
  [
    "**Online**: a https://caravistareservas.com/appointment",
    '<a href="https://caravistareservas.com/appointment"',
    "**",
  ],
  ["Truca al 600 764 517 o escriu-nos.", 'href="tel:600764517"', null],
  ["Escriu a info@caravistarestaurant.com", 'href="mailto:info@caravistarestaurant.com"', null],
  // A year is not a phone number.
  ["Obrim el 2026 amb el menú a 42 €", "2026", 'href="tel:'],
  // Escaping happens before any markup, so markup is the only HTML produced.
  ["<script>alert(1)</script>", "&lt;script&gt;", "<script>"],
  ["Un asterisc solt * no trenca res", "asterisc solt * no", "<strong>"],
];

let failed = 0;
for (const [input, must, mustNot] of CASES) {
  const out = helpers.formatMarkup(input);
  const missing = !out.includes(must);
  const leaked = mustNot !== null && out.includes(mustNot);
  if (missing || leaked) {
    failed++;
    console.log("FAIL", JSON.stringify(input));
    console.log("  ->", out);
    if (missing) console.log("  missing:", must);
    if (leaked) console.log("  should not contain:", mustNot);
  }
}

console.log(
  failed === 0
    ? `${CASES.length} markup cases pass`
    : `${failed} of ${CASES.length} markup cases failed`
);
process.exit(failed === 0 ? 0 : 1);
