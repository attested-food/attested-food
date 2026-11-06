// Holder side: raw PDF -> redacted PDF of the same length.
//
// Overwrites the hex digits of every PII-font text string with "0", so each PII glyph becomes
// glyph 0 (.notdef, drawn blank, same advance in a monospace font). No byte outside those digits
// changes, so offsets, the xref and every other object stay identical. Writes a manifest with the
// spans and both SHA-256s, which is what check.mjs and the proof consume.
//
// usage: node scripts/redact.mjs <raw.pdf> <redacted.pdf> [--expect data/<id>.json]
//   --expect: also assert none of the data file's customer strings survive in the output.

import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { Doc, scanText, hexOf } from "./pdf.mjs";
import { piiSpans, guestCheck, verifierPolicy } from "./check.mjs";

const sha256 = (b) => createHash("sha256").update(b).digest("hex");

export function redact(raw) {
  const spans = piiSpans(raw);
  const out = Buffer.from(raw);
  for (const [a, b] of spans) out.fill(0x30, a, b);
  return { out, spans };
}

// All text on all pages, decoded through each font's ToUnicode, glyph 0 dropped.
export function pageText(buf) {
  const doc = new Doc(buf);
  let text = "";
  for (const page of doc.pages()) {
    const fonts = doc.fonts(page.resources);
    for (const num of page.contents)
      scanText(doc.streamData(doc.obj(num)), ({ font, str }) => {
        const f = fonts.get(font);
        const codes = f.twoByte ? hexOf(str.str).match(/.{4}/g) ?? [] : [...str.str].map((c) => hexOf(Buffer.of(c)));
        text += codes.map((c) => (/^0+$/.test(c) ? "" : f.toUnicode.get(c) ?? "�")).join("") + "\n";
      });
  }
  return text;
}

function assertGone(buf, data) {
  const c = data.customer;
  const needles = [c.name, c.contact, ...[c.address].flat()].filter(Boolean);
  const squash = (s) => s.replace(/[\s ]+/g, "").toLowerCase();
  const text = squash(pageText(buf));
  const bytes = squash(buf.toString("latin1"));
  for (const n of needles) {
    if (text.includes(squash(n))) throw new Error(`"${n}" still in page text`);
    if (bytes.includes(squash(n))) throw new Error(`"${n}" still in raw bytes`);
  }
  return needles.length;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const ei = args.indexOf("--expect");
  const expect = ei >= 0 ? JSON.parse(readFileSync(args.splice(ei, 2)[1], "utf8")) : null;
  const [inp, outp] = args;
  if (!inp || !outp) {
    console.error("usage: node scripts/redact.mjs <raw.pdf> <redacted.pdf> [--expect data/<id>.json]");
    process.exit(2);
  }
  const raw = readFileSync(inp);
  const { out, spans } = redact(raw);
  const { changed } = guestCheck(raw, out, spans);
  verifierPolicy(out, spans);
  if (expect) assertGone(out, expect);
  writeFileSync(outp, out);
  const manifest = {
    original: { sha256: sha256(raw), length: raw.length },
    redacted: { sha256: sha256(out), length: out.length },
    changed_bytes: changed,
    spans,
  };
  writeFileSync(outp.replace(/\.pdf$/, "") + ".manifest.json", JSON.stringify(manifest, null, 2) + "\n");
  console.log(`${outp}: ${spans.length} PII strings blanked, ${changed} of ${raw.length} bytes changed`);
}
