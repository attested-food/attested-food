// Generation-time step (lab side): Typst PDF -> "raw" PDF that goes to S3.
//
// Page content streams are stored uncompressed and every text-showing string is rewritten as a
// hex string, so each 2-byte glyph id is exactly 4 ASCII hex digits at a fixed offset. That is
// what lets redact.mjs blank a glyph by overwriting 4 bytes in place, leaving every other byte
// (and every xref offset) unchanged. Nothing else in the file is touched; the xref is rebuilt.
//
// usage: node scripts/normalize.mjs <in.pdf> <out.pdf>

import { readFileSync, writeFileSync } from "node:fs";
import { Doc, scanText, hexOf } from "./pdf.mjs";

export function serialize(v) {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(+v.toFixed(6));
  if (Array.isArray(v)) return "[" + v.map(serialize).join(" ") + "]";
  if (v.name !== undefined) return "/" + v.name;
  if (v.ref) return `${v.ref[0]} ${v.ref[1]} R`;
  if (v.str) return "<" + hexOf(v.str) + ">";
  if (v.kw !== undefined) return v.kw;
  if (v.dict) return "<<" + [...v.dict].map(([k, x]) => ` /${k} ${serialize(x)}`).join("") + " >>";
  throw new Error("cannot serialize " + JSON.stringify(v));
}

// "N 0 obj <<dict>> stream ... endstream endobj" with body stored uncompressed.
export function streamObject(num, dict, body) {
  dict = new Map(dict);
  dict.delete("Filter");
  dict.delete("DecodeParms");
  dict.set("Length", body.length);
  return Buffer.concat([
    Buffer.from(`${num} 0 obj\n${serialize({ dict })}\nstream\n`, "latin1"),
    body,
    Buffer.from("\nendstream\nendobj", "latin1"),
  ]);
}

export function normalize(input) {
  const doc = new Doc(input);
  const contentNums = new Set(doc.pages().flatMap((p) => p.contents));

  const replacement = new Map(); // obj num -> Buffer of the whole "N 0 obj ... endobj"
  for (const num of contentNums) {
    const o = doc.obj(num);
    const data = doc.streamData(o);
    // Rewrite literal text strings as hex, keep every other byte of the stream as is.
    const parts = [];
    let last = 0;
    scanText(data, ({ str }) => {
      if (str.hex) return;
      parts.push(data.subarray(last, str.start), Buffer.from("<" + hexOf(str.str) + ">", "latin1"));
      last = str.end;
    });
    parts.push(data.subarray(last));
    const body = Buffer.concat(parts);
    replacement.set(num, streamObject(num, o.dict, body));
  }

  return rewrite(input, doc, replacement);
}

// Re-emit the file object by object in original order; bytes between objects are kept. A
// replacement maps obj num -> Buffer ("N 0 obj ... endobj") or null to drop the object.
export function rewrite(input, doc, replacement) {
  const order = [...doc.offsets].sort((a, b) => a[1] - b[1]);
  const out = [input.subarray(0, order[0][1])];
  const newOffsets = new Map();
  let size = out[0].length;
  for (const [num, off] of order) {
    const o = doc.obj(num);
    const next = order.find(([, x]) => x > off)?.[1] ?? doc.xrefOffset;
    if (replacement.get(num) === null) continue;
    const gap = input.subarray(o.end, next); // whitespace after endobj
    const bytes = replacement.get(num) ?? input.subarray(off, o.end);
    newOffsets.set(num, size);
    out.push(bytes, gap);
    size += bytes.length + gap.length;
  }

  const maxNum = Math.max(...doc.offsets.keys());
  let xref = `xref\n0 ${maxNum + 1}\n0000000000 65535 f \n`;
  for (let n = 1; n <= maxNum; n++) {
    const off = newOffsets.get(n);
    xref += off === undefined ? "0000000000 00000 f \n" : `${String(off).padStart(10, "0")} 00000 n \n`;
  }
  const trailer = new Map(doc.trailer);
  trailer.set("Size", maxNum + 1);
  xref += `trailer\n${serialize({ dict: trailer })}\nstartxref\n${size}\n%%EOF\n`;
  out.push(Buffer.from(xref, "latin1"));
  return Buffer.concat(out);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const [inp, outp] = process.argv.slice(2);
  if (!inp || !outp) {
    console.error("usage: node scripts/normalize.mjs <in.pdf> <out.pdf>");
    process.exit(2);
  }
  const raw = normalize(readFileSync(inp));
  new Doc(raw).pages(); // re-parse as a sanity check
  writeFileSync(outp, raw);
  console.log(`${outp}: ${raw.length} bytes`);
}
