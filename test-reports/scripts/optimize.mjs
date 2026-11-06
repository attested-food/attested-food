// Prover-friendly rewrite of a raw (normalized) PDF: fewer bytes and fewer tokens for the guest,
// same rendering, same text-show operators in the same order with the same glyphs.
//
// Page content: every text run moves into one BT ... ET at the end of the page, positioned with
// Td (Tm only for non-translation matrices), Tf / colour emitted only on change, string-only
// TJ arrays become Tj, non-PII strings become literal strings (2 bytes per glyph instead of 4;
// PII strings stay hex for the redaction contract); graphics keep their order, numbers rounded
// (coords 1 dp, colours 3 dp), q ... Q groups that paint nothing are dropped, unit-cm groups are
// flattened, closed axis-aligned 4-point paths become re, consecutive same-paint subpaths share
// one paint op. Objects: ICC colour spaces -> Device*, ToUnicode CMaps as bfrange, no XMP
// metadata, no /ProcSet, unreachable objects dropped.
//
// usage: node scripts/optimize.mjs <raw.pdf> <out.pdf>

import { readFileSync, writeFileSync } from "node:fs";
import { Doc, Parser, hexOf, parseCMap } from "./pdf.mjs";
import { serialize, streamObject, rewrite } from "./normalize.mjs";
import { PII_BASEFONT } from "./check.mjs";

const COLOR_OPS = new Set(["sc", "scn", "SC", "SCN", "rg", "RG", "g", "G", "k", "K"]);
const PAINT_OPS = new Set(["f", "F", "f*", "B", "B*", "b", "b*", "S", "s", "sh", "Do"]);
const SHOW_OPS = new Set(["Tj", "TJ", "'", '"']);

const fmt = (x, dp) => String(+x.toFixed(dp) || 0);
const mul = (m, n) => [
  m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3],
  m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3],
  m[4] * n[0] + m[5] * n[2] + n[4], m[4] * n[1] + m[5] * n[3] + n[5],
];
const ID = [1, 0, 0, 1, 0, 0];

function parseOps(data) {
  const p = new Parser(data, 0);
  const ops = [];
  let args = [];
  for (;;) {
    p.skipWs();
    if (p.p >= data.length) return ops;
    const v = p.value();
    if (v && v.kw !== undefined) {
      if (v.kw === "BI") throw new Error("inline images unsupported");
      ops.push({ op: v.kw, args });
      args = [];
    } else args.push(v);
  }
}

function graphicsOp({ op, args }) {
  const dps = op === "cm" ? [4, 4, 4, 4, 2, 2] : null;
  const a = args.map((v, i) => (typeof v === "number" ? fmt(v, COLOR_OPS.has(op) ? 3 : dps ? dps[i] : 1) : serialize(v)));
  return [...a, op].join(" ");
}

// Drop q ... Q groups (recursively) that contain no painting operator.
function prune(gops) {
  const out = [];
  const stack = [];
  for (const g of gops) {
    if (g.op === "q") {
      stack.push({ start: out.length, paints: false });
      out.push(g);
    } else if (g.op === "Q") {
      const fr = stack.pop();
      if (!fr.paints) out.length = fr.start;
      else out.push(g);
      if (fr.paints && stack.length) stack[stack.length - 1].paints = true;
    } else {
      if (PAINT_OPS.has(g.op) && stack.length) stack[stack.length - 1].paints = true;
      out.push(g);
    }
  }
  if (stack.length) throw new Error("unbalanced q/Q");
  return out;
}

const PATH_OPS = new Set(["m", "l", "c", "v", "y", "h", "re"]);
const STATE_OPS = { cs: "fill", scn: "fill", sc: "fill", g: "fill", rg: "fill", CS: "stroke", SCN: "stroke", SC: "stroke", G: "stroke", RG: "stroke", w: "w", M: "M", J: "J", j: "j", d: "d" };
const r2 = (x) => +x.toFixed(1);

// A top-level "q [cm] state* path* paint* Q" group whose cm is a flip/translation (b = c = 0,
// |a| = |d| = 1, so line widths do not change) is replaced by its ops with the coordinates
// mapped through cm. Runs of such groups share one q ... Q and set each state only on change.
function flatten(gops) {
  const out = [];
  let i = 0;
  let batch = null; // { state: Map }
  const close = () => {
    if (batch) out.push({ op: "Q", args: [] });
    batch = null;
  };
  while (i < gops.length) {
    const g = gops[i];
    let j = i + 1;
    let ok = g.op === "q";
    let m = ID;
    if (ok && gops[j]?.op === "cm") {
      m = gops[j].args;
      ok = m[1] === 0 && m[2] === 0 && Math.abs(m[0]) === 1 && Math.abs(m[3]) === 1;
      j++;
    }
    const body = [];
    while (ok && j < gops.length && gops[j].op !== "Q") {
      const o = gops[j];
      if (!(PATH_OPS.has(o.op) || STATE_OPS[o.op] || PAINT_OPS.has(o.op) || o.op === "n") || o.op === "Do" || o.op === "sh") ok = false;
      body.push(o);
      j++;
    }
    if (!ok || j >= gops.length) {
      close();
      out.push(g);
      i++;
      continue;
    }
    if (!batch) {
      batch = { state: new Map() };
      out.push({ op: "q", args: [] });
    }
    const pt = (x, y) => [r2(m[0] * x + m[4]), r2(m[3] * y + m[5])];
    const pending = new Map(); // state key -> ops
    for (const o of body) {
      const key = STATE_OPS[o.op];
      if (key) {
        // cs/CS reset the colour, so a colour is "cs + scn" taken together.
        const prev = pending.get(key) ?? [];
        pending.set(key, o.op === "cs" || o.op === "CS" || o.op === "g" || o.op === "G" || o.op === "rg" || o.op === "RG" || !["fill", "stroke"].includes(key) ? [o] : [...prev.filter((x) => !["scn", "sc", "SCN", "SC"].includes(x.op)), o]);
        continue;
      }
      for (const [k, ops] of pending) {
        const sig = ops.map(graphicsOp).join(" ");
        if (batch.state.get(k) !== sig) {
          // Same colour space already current: only the colour operands are needed.
          const prev = batch.state.get(k);
          const csOp = ops.find((x) => x.op === "cs" || x.op === "CS");
          const emit = csOp && prev && prev.startsWith(graphicsOp(csOp)) ? ops.filter((x) => x !== csOp) : ops;
          out.push(...emit);
          batch.state.set(k, sig);
        }
      }
      pending.clear();
      if (o.op === "re") {
        const [x, y] = pt(o.args[0], o.args[1]);
        out.push({ op: "re", args: [x, y, r2(m[0] * o.args[2]), r2(m[3] * o.args[3])] });
      } else if (PATH_OPS.has(o.op)) {
        const a = [];
        for (let k = 0; k < o.args.length; k += 2) a.push(...pt(o.args[k], o.args[k + 1]));
        out.push({ op: o.op, args: a });
      } else out.push(o);
    }
    i = j + 1;
  }
  close();
  return mergePaints(toRects(out));
}

// m p0 l p1 l p2 l p3 h with axis-aligned sides -> re.
function toRects(ops) {
  const out = [];
  for (let i = 0; i < ops.length; i++) {
    const w = ops.slice(i, i + 5);
    if (w.length === 5 && w[0].op === "m" && w[1].op === "l" && w[2].op === "l" && w[3].op === "l" && w[4].op === "h") {
      const p = w.slice(0, 4).map((o) => o.args);
      const ax = p[0][1] === p[1][1] && p[1][0] === p[2][0] && p[2][1] === p[3][1] && p[3][0] === p[0][0];
      const ay = p[0][0] === p[1][0] && p[1][1] === p[2][1] && p[2][0] === p[3][0] && p[3][1] === p[0][1];
      if (ax || ay) {
        out.push({ op: "re", args: [p[0][0], p[0][1], r2(p[2][0] - p[0][0]), r2(p[2][1] - p[0][1])] });
        i += 4;
        continue;
      }
    }
    out.push(ops[i]);
  }
  return out;
}

// "path S path S" -> "path path S" when only path ops sit between the two paints.
function mergePaints(ops) {
  const out = [];
  for (let i = 0; i < ops.length; i++) {
    const o = ops[i];
    if (PAINT_OPS.has(o.op) && o.op !== "Do" && o.op !== "sh") {
      let j = i + 1;
      while (j < ops.length && PATH_OPS.has(ops[j].op)) j++;
      if (j > i + 1 && j < ops.length && ops[j].op === o.op && (ops[i + 1].op === "m" || ops[i + 1].op === "re")) continue;
    }
    out.push(o);
  }
  return out;
}

// Literal string body for 2-byte codes; only ( ) \ and EOL bytes need escaping.
function literal(buf) {
  let s = "(";
  for (const c of buf) s += c === 0x28 || c === 0x29 || c === 0x5c ? "\\" + String.fromCharCode(c) : c === 0x0a ? "\\n" : c === 0x0d ? "\\r" : String.fromCharCode(c);
  return s + ")";
}

export function optimizeContent(data, piiFonts = new Set()) {
  const gops = [];
  const runs = [];
  let gs = { ctm: ID, cs: "DeviceGray", fill: [0] };
  const stack = [];
  let inText = false;
  let tlm = ID;
  let moved = true;
  let font = null, size = null, tr = 0;
  for (const o of parseOps(data)) {
    const { op, args } = o;
    if (op === "cs") gs = { ...gs, cs: args[0].name, fill: [0] };
    else if (op === "scn" || op === "sc") gs = { ...gs, fill: args };
    else if (op === "g") gs = { ...gs, cs: "DeviceGray", fill: args, csOp: true };
    else if (op === "rg") gs = { ...gs, cs: "DeviceRGB", fill: args, csOp: true };
    if (inText) {
      if (op === "ET") inText = false;
      else if (op === "Tf") [font, size] = [args[0].name, args[1]];
      else if (op === "Tr") tr = args[0];
      else if (op === "Tm") [tlm, moved] = [args, true];
      else if (op === "Td") [tlm, moved] = [mul([1, 0, 0, 1, args[0], args[1]], tlm), true];
      else if (SHOW_OPS.has(op)) {
        if (op !== "Tj" && op !== "TJ") throw new Error(`text op ${op} unsupported`);
        runs.push({ font, size, tr, cs: gs.cs, fill: gs.fill, m: moved ? mul(tlm, gs.ctm) : null, op, args });
        moved = false;
      } else if (!["cs", "scn", "sc", "g", "rg"].includes(op)) throw new Error(`op ${op} inside BT unsupported`);
      continue;
    }
    if (op === "BT") {
      [inText, tlm, moved] = [true, ID, true];
      continue;
    }
    if (op === "q") stack.push(gs);
    else if (op === "Q") gs = stack.pop();
    else if (op === "cm") gs = { ...gs, ctm: mul(args, gs.ctm) };
    gops.push(o);
  }

  const lines = flatten(prune(gops)).map(graphicsOp);
  const text = ["BT"];
  let cur = { font: null, size: null, tr: 0, cs: null, fill: null };
  let line = null; // last emitted line matrix, e/f in hundredths
  for (const r of runs) {
    if (r.font !== cur.font || r.size !== cur.size) text.push(`/${r.font} ${fmt(r.size, 2)} Tf`);
    if (r.tr !== cur.tr) text.push(`${r.tr} Tr`);
    const fill = r.fill.map((v) => fmt(v, 3)).join(" ");
    if (r.cs !== cur.cs) text.push(r.cs === "DeviceGray" ? `${fill} g` : r.cs === "DeviceRGB" ? `${fill} rg` : `/${r.cs} cs ${fill} scn`);
    else if (fill !== cur.fill) text.push(r.cs === "DeviceGray" ? `${fill} g` : r.cs === "DeviceRGB" ? `${fill} rg` : `${fill} scn`);
    cur = { font: r.font, size: r.size, tr: r.tr, cs: r.cs, fill };
    if (r.m) {
      const abcd = r.m.slice(0, 4).map((v) => +v.toFixed(4));
      const e = Math.round(r.m[4] * 10), f = Math.round(r.m[5] * 10);
      const translate = abcd.join() === "1,0,0,1";
      if (translate && (line === null || line.translate)) {
        const [pe, pf] = line ? [line.e, line.f] : [0, 0];
        text.push(`${fmt((e - pe) / 10, 1)} ${fmt((f - pf) / 10, 1)} Td`);
      } else text.push(`${abcd.join(" ")} ${fmt(e / 10, 1)} ${fmt(f / 10, 1)} Tm`);
      line = { e, f, translate };
    }
    const arr = r.op === "TJ" ? r.args[0] : [r.args[0]];
    const str = (b) => (piiFonts.has(r.font) ? `<${hexOf(b)}>` : literal(b));
    if (arr.every((v) => v.str)) text.push(`${str(Buffer.concat(arr.map((v) => v.str)))} Tj`);
    else text.push(`[${arr.map((v) => (v.str ? str(v.str) : fmt(v, 0))).join(" ")}] TJ`);
  }
  text.push("ET");
  return Buffer.from(["q", ...lines, "Q", ...(runs.length ? text : [])].join("\n") + "\n", "latin1");
}

// ToUnicode CMap with bfrange: consecutive codes with consecutive single code points -> one
// range, other consecutive codes -> array ranges, multi-char targets (ligatures) stay bfchar.
export function compactCMap(map) {
  const hex4 = (n) => n.toString(16).toUpperCase().padStart(4, "0");
  const entries = [...map].map(([k, v]) => [parseInt(k, 16), v]).sort((a, b) => a[0] - b[0]);
  const chars = [], ranges = [];
  let i = 0;
  while (i < entries.length) {
    const [c, u] = entries[i];
    if (u.length !== 1) {
      chars.push(`<${hex4(c)}> <${Buffer.from(u, "utf16le").swap16().toString("hex").toUpperCase()}>`);
      i++;
      continue;
    }
    // run of consecutive codes with single-unit targets
    let j = i + 1;
    while (j < entries.length && entries[j][0] === entries[j - 1][0] + 1 && entries[j][1].length === 1 && j - i < 100) j++;
    const run = entries.slice(i, j);
    let k = 0;
    while (k < run.length) {
      let l = k + 1;
      while (l < run.length && run[l][1].charCodeAt(0) === run[l - 1][1].charCodeAt(0) + 1) l++;
      if (l - k >= 2 || run.length === 1) {
        ranges.push(`<${hex4(run[k][0])}> <${hex4(run[l - 1][0])}> <${hex4(run[k][1].charCodeAt(0))}>`);
        k = l;
        continue;
      }
      // array segment until the next ascending pair
      let m = k + 1;
      while (m < run.length && !(m + 1 < run.length && run[m + 1][1].charCodeAt(0) === run[m][1].charCodeAt(0) + 1)) m++;
      ranges.push(`<${hex4(run[k][0])}> <${hex4(run[m - 1][0])}> [${run.slice(k, m).map(([, u]) => `<${hex4(u.charCodeAt(0))}>`).join(" ")}]`);
      k = m;
    }
    i = j;
  }
  const block = (kw, xs) => {
    let s = "";
    for (let a = 0; a < xs.length; a += 100) s += `${Math.min(100, xs.length - a)} begin${kw}\n${xs.slice(a, a + 100).join("\n")}\nend${kw}\n`;
    return s;
  };
  return Buffer.from(
    "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n/CMapName /Custom def\n/CMapType 2 def\n" +
      "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n" + block("bfchar", chars) + block("bfrange", ranges) +
      "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n",
    "latin1",
  );
}

function mapValue(v, f) {
  const r = f(v);
  if (r !== undefined) return r;
  if (Array.isArray(v)) return v.map((x) => mapValue(x, f));
  if (v && v.dict) return { dict: new Map([...v.dict].map(([k, x]) => [k, mapValue(x, f)])) };
  return v;
}

function refs(v, out) {
  if (Array.isArray(v)) v.forEach((x) => refs(x, out));
  else if (v && v.ref) out.push(v.ref[0]);
  else if (v && v.dict) for (const x of v.dict.values()) refs(x, out);
}

export function optimize(input) {
  const doc = new Doc(input);
  const nums = [...doc.offsets.keys()];
  const pages = doc.pages();
  const contentNums = new Set(pages.flatMap((p) => p.contents));
  const piiByContent = new Map();
  for (const p of pages) {
    const pii = new Set([...doc.fonts(p.resources)].filter(([, f]) => PII_BASEFONT.test(f.baseFont ?? "")).map(([k]) => k));
    for (const c of p.contents) piiByContent.set(c, pii);
  }
  const tounicode = new Set();
  for (const n of nums) {
    const tu = doc.obj(n).dict?.get("ToUnicode");
    if (tu?.ref) tounicode.add(tu.ref[0]);
  }

  // ICC-based colour space objects -> Device* names.
  const icc = new Map();
  for (const n of nums) {
    const v = doc.obj(n).value;
    if (Array.isArray(v) && v[0]?.name === "ICCBased") {
      const comps = doc.resolve(doc.obj(v[1].ref[0]).dict.get("N"));
      icc.set(n, { name: { 1: "DeviceGray", 3: "DeviceRGB", 4: "DeviceCMYK" }[comps] });
    }
  }
  const values = new Map(); // num -> new value (non-stream) or new dict (stream)
  const replacement = new Map();
  for (const n of nums) {
    const o = doc.obj(n);
    let v = mapValue(o.value, (x) => (x && x.ref && icc.has(x.ref[0]) ? icc.get(x.ref[0]) : undefined));
    if (v.dict) {
      const d = new Map(v.dict);
      if (d.get("Type")?.name === "Catalog") d.delete("Metadata");
      d.delete("ProcSet");
      for (const [k, x] of d) if (k === "Resources" && x.dict) x.dict.delete("ProcSet");
      v = { dict: d };
    }
    values.set(n, v);
    const changed = serialize(v) !== serialize(o.value);
    if (contentNums.has(n)) {
      // ICC names in the content (/c0 cs) are resource names, kept; resources now map them to Device*.
      replacement.set(n, streamObject(n, v.dict, optimizeContent(doc.streamData(o), piiByContent.get(n))));
    } else if (tounicode.has(n)) {
      replacement.set(n, streamObject(n, v.dict, compactCMap(parseCMap(doc.streamData(o).toString("latin1")))));
    } else if (changed) {
      const head = `${n} 0 obj\n${serialize(v)}\n`;
      replacement.set(
        n,
        o.stream
          ? Buffer.concat([Buffer.from(head + "stream\n", "latin1"), input.subarray(o.stream.start, o.stream.end), Buffer.from("\nendstream\nendobj", "latin1")])
          : Buffer.from(head + "endobj", "latin1"),
      );
    }
  }

  // Keep only what the trailer reaches.
  const seen = new Set();
  const todo = [];
  refs({ dict: doc.trailer }, todo);
  while (todo.length) {
    const n = todo.pop();
    if (seen.has(n)) continue;
    seen.add(n);
    refs(values.get(n), todo);
  }
  for (const n of nums) if (!seen.has(n)) replacement.set(n, null);
  return rewrite(input, doc, replacement);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const [inp, outp] = process.argv.slice(2);
  if (!inp || !outp) {
    console.error("usage: node scripts/optimize.mjs <raw.pdf> <out.pdf>");
    process.exit(2);
  }
  const out = optimize(readFileSync(inp));
  new Doc(out).pages();
  writeFileSync(outp, out);
  console.log(`${outp}: ${out.length} bytes`);
}
