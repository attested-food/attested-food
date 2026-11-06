// What a redaction proof has to establish, split the way the zkVM proof would split it.
//
// guestCheck: runs inside the guest. Private: original PDF. Public: redacted PDF (as its hash),
//   the span list. Asserts the two files have equal length and every byte that differs lies in a
//   span and is "0" in the redacted file. That is the whole guest-side logic: one linear pass.
//
// verifierPolicy: runs outside the proof on the public redacted PDF. Asserts every span is the
//   interior of a hex string shown by a text operator in a page content stream with the PII font,
//   and is all "0" (glyph id 0 = .notdef, blank). The redacted file has the same structure as the
//   original byte for byte outside those hex digits, so checking it here is checking the original.
//
// Together: the redacted file is the original with some PII-font glyphs replaced by glyph 0, and
// nothing else changed. A span can never cover a result value, a "<", a "Not", a number in an
// operator, the xref or the font's ToUnicode map.
//
// usage: node scripts/check.mjs <original.pdf> <redacted.pdf> [<manifest.json>]

import { readFileSync } from "node:fs";
import { Doc, scanText, isHex } from "./pdf.mjs";

// Template convention: the lab sets every customer field, and nothing else, in this font.
export const PII_BASEFONT = /^[A-Z]{6}\+DejaVuSansMono$/;

// Spans [start, end) of the hex digits of every PII-font string in the page content streams.
export function piiSpans(buf) {
  const doc = new Doc(buf);
  const spans = [];
  for (const page of doc.pages()) {
    const fonts = doc.fonts(page.resources);
    for (const num of page.contents) {
      const o = doc.obj(num);
      if (o.dict.has("Filter")) throw new Error(`content stream ${num} is filtered, run normalize first`);
      scanText(doc.streamData(o), ({ font, str }) => {
        const f = fonts.get(font);
        if (!f || !PII_BASEFONT.test(f.baseFont ?? "")) return;
        if (!f.twoByte) throw new Error(`PII font ${font} is not a 2-byte CID font`);
        const start = o.stream.start + str.start + 1;
        const end = o.stream.start + str.end - 1;
        if (!str.hex || (end - start) % 4 !== 0) throw new Error(`PII string at ${start} is not normalized hex`);
        for (let i = start; i < end; i++) if (!isHex(buf[i])) throw new Error(`whitespace in PII hex string at ${i}`);
        spans.push([start, end]);
      });
    }
  }
  return spans;
}

const ZERO = 0x30;

export function guestCheck(original, redacted, spans) {
  if (original.length !== redacted.length) throw new Error("length differs");
  let s = 0;
  let changed = 0;
  for (let i = 0; i < original.length; i++) {
    if (original[i] === redacted[i]) continue;
    while (s < spans.length && spans[s][1] <= i) s++;
    if (s === spans.length || i < spans[s][0]) throw new Error(`byte ${i} changed outside every span`);
    if (redacted[i] !== ZERO) throw new Error(`byte ${i} changed to something other than "0"`);
    changed++;
  }
  return { changed };
}

export function verifierPolicy(redacted, spans) {
  const allowed = new Set(piiSpans(redacted).map(([a, b]) => `${a}:${b}`));
  let prev = -1;
  for (const [a, b] of spans) {
    if (a < prev) throw new Error("spans not sorted / overlapping");
    prev = b;
    if (!allowed.has(`${a}:${b}`)) throw new Error(`span ${a}:${b} is not a PII-font text string`);
    for (let i = a; i < b; i++) if (redacted[i] !== ZERO) throw new Error(`span ${a}:${b} not fully blanked`);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const [o, r, m] = process.argv.slice(2);
  if (!o || !r) {
    console.error("usage: node scripts/check.mjs <original.pdf> <redacted.pdf> [<manifest.json>]");
    process.exit(2);
  }
  const original = readFileSync(o);
  const redacted = readFileSync(r);
  const spans = m ? JSON.parse(readFileSync(m, "utf8")).spans : piiSpans(redacted);
  const { changed } = guestCheck(original, redacted, spans);
  verifierPolicy(redacted, spans);
  const covered = spans.reduce((n, [a, b]) => n + b - a, 0);
  console.log(
    `ok: ${changed} of ${original.length} bytes changed (${((100 * changed) / original.length).toFixed(3)}%), ` +
      `all inside ${spans.length} PII spans (${covered} bytes)`,
  );
}
