// Minimal PDF reader for the files Typst writes: one classic xref table, no object streams,
// no xref streams, no encryption. Works on raw bytes (Buffer) and reports byte offsets, so the
// callers can edit in place. Node built-ins only.

import { inflateSync } from "node:zlib";

const WS = new Set([0x00, 0x09, 0x0a, 0x0c, 0x0d, 0x20]);
const DELIM = new Set([...'()<>[]{}/%'].map((c) => c.charCodeAt(0)));
export const isWs = (c) => WS.has(c);
const isRegular = (c) => !WS.has(c) && !DELIM.has(c);
export const isHex = (c) =>
  (c >= 0x30 && c <= 0x39) || (c >= 0x41 && c <= 0x46) || (c >= 0x61 && c <= 0x66);

// ---------------------------------------------------------------------------------------------
// Object parser. Values: number, {name}, {str: Buffer, hex}, array, {dict: Map}, {ref: [n, g]}, {kw}.

export class Parser {
  constructor(buf, pos = 0) {
    this.b = buf;
    this.p = pos;
  }
  skipWs() {
    const b = this.b;
    for (;;) {
      while (this.p < b.length && isWs(b[this.p])) this.p++;
      if (b[this.p] !== 0x25) return; // %
      while (this.p < b.length && b[this.p] !== 0x0a && b[this.p] !== 0x0d) this.p++;
    }
  }
  token() {
    const s = this.p;
    while (this.p < this.b.length && isRegular(this.b[this.p])) this.p++;
    return this.b.toString("latin1", s, this.p);
  }
  value() {
    this.skipWs();
    const b = this.b;
    const c = b[this.p];
    if (c === 0x2f) {
      this.p++;
      return { name: this.token() };
    }
    if (c === 0x3c && b[this.p + 1] === 0x3c) {
      this.p += 2;
      const dict = new Map();
      for (;;) {
        this.skipWs();
        if (b[this.p] === 0x3e && b[this.p + 1] === 0x3e) {
          this.p += 2;
          return { dict };
        }
        const k = this.value();
        if (!k || k.name === undefined) throw new Error(`dict key at ${this.p}`);
        dict.set(k.name, this.value());
      }
    }
    if (c === 0x3c) return this.hexString();
    if (c === 0x28) return this.literalString();
    if (c === 0x5b) {
      this.p++;
      const arr = [];
      for (;;) {
        this.skipWs();
        if (b[this.p] === 0x5d) {
          this.p++;
          return arr;
        }
        arr.push(this.value());
      }
    }
    const t = this.token();
    if (t === "") throw new Error(`unexpected byte 0x${c?.toString(16)} at ${this.p}`);
    if (/^[+-]?(\d+\.?\d*|\.\d+)$/.test(t)) {
      // "n g R" reference
      if (/^\d+$/.test(t)) {
        const save = this.p;
        this.skipWs();
        const g = this.token();
        this.skipWs();
        if (/^\d+$/.test(g) && this.b[this.p] === 0x52 && !isRegular(this.b[this.p + 1] ?? 0x20)) {
          this.p++;
          return { ref: [Number(t), Number(g)] };
        }
        this.p = save;
      }
      return Number(t);
    }
    return { kw: t };
  }
  hexString() {
    const start = this.p;
    this.p++;
    const end = this.b.indexOf(0x3e, this.p);
    let hex = this.b.toString("latin1", this.p, end).replace(/\s+/g, "");
    if (hex.length % 2) hex += "0";
    this.p = end + 1;
    return { str: Buffer.from(hex, "hex"), hex: true, start, end: this.p };
  }
  literalString() {
    const b = this.b;
    const start = this.p;
    this.p++;
    const out = [];
    let depth = 1;
    for (;;) {
      const c = b[this.p++];
      if (c === undefined) throw new Error("unterminated string");
      if (c === 0x5c) {
        const e = b[this.p++];
        const map = { 0x6e: 0x0a, 0x72: 0x0d, 0x74: 0x09, 0x62: 0x08, 0x66: 0x0c };
        if (map[e] !== undefined) out.push(map[e]);
        else if (e >= 0x30 && e <= 0x37) {
          let v = e - 0x30;
          for (let i = 0; i < 2 && b[this.p] >= 0x30 && b[this.p] <= 0x37; i++) v = v * 8 + (b[this.p++] - 0x30);
          out.push(v & 0xff);
        } else if (e === 0x0d) {
          if (b[this.p] === 0x0a) this.p++;
        } else if (e !== 0x0a) out.push(e);
        continue;
      }
      if (c === 0x28) depth++;
      if (c === 0x29 && --depth === 0) break;
      out.push(c);
    }
    return { str: Buffer.from(out), hex: false, start, end: this.p };
  }
}

// ---------------------------------------------------------------------------------------------
// Document: xref table, objects, streams.

export class Doc {
  constructor(buf) {
    this.b = buf;
    const tail = buf.toString("latin1", Math.max(0, buf.length - 64));
    const m = /startxref\s+(\d+)\s+%%EOF\s*$/.exec(tail);
    if (!m) throw new Error("no startxref");
    this.xrefOffset = Number(m[1]);
    const p = new Parser(buf, this.xrefOffset);
    if (p.token() !== "xref") throw new Error("not a classic xref table (xref streams unsupported)");
    this.offsets = new Map(); // obj num -> byte offset of "N G obj"
    for (;;) {
      p.skipWs();
      const first = p.token();
      if (first === "trailer") break;
      p.skipWs();
      const count = Number(p.token());
      for (let i = 0; i < count; i++) {
        p.skipWs();
        const off = Number(p.token());
        p.skipWs();
        p.token();
        p.skipWs();
        const kind = p.token();
        if (kind === "n") this.offsets.set(Number(first) + i, off);
      }
    }
    this.trailerStart = p.p;
    this.trailer = p.value().dict;
    if (this.trailer.has("Prev")) throw new Error("incremental updates unsupported");
    this.cache = new Map();
  }

  // { num, dict|value, start (of "N G obj"), end (after "endobj"), stream?: {start, end} }
  obj(num) {
    if (this.cache.has(num)) return this.cache.get(num);
    const start = this.offsets.get(num);
    if (start === undefined) throw new Error(`object ${num} not in xref`);
    const p = new Parser(this.b, start);
    const n = Number(p.token());
    p.skipWs();
    p.token();
    p.skipWs();
    if (n !== num || p.token() !== "obj") throw new Error(`xref offset of object ${num} is wrong`);
    const value = p.value();
    const o = { num, value, dict: value.dict, start };
    p.skipWs();
    const save = p.p;
    if (p.token() === "stream") {
      if (this.b[p.p] === 0x0d) p.p++;
      if (this.b[p.p] !== 0x0a) throw new Error("stream keyword not followed by EOL");
      p.p++;
      const len = this.resolve(o.dict.get("Length"));
      o.stream = { start: p.p, end: p.p + len };
      p.p += len;
      p.skipWs();
      if (p.token() !== "endstream") throw new Error(`object ${num}: /Length does not end at endstream`);
      p.skipWs();
    } else p.p = save;
    if (p.token() !== "endobj") throw new Error(`object ${num}: no endobj`);
    o.end = p.p;
    this.cache.set(num, o);
    return o;
  }

  resolve(v) {
    while (v && v.ref) v = this.obj(v.ref[0]).value;
    return v;
  }

  streamData(o) {
    const raw = this.b.subarray(o.stream.start, o.stream.end);
    const f = this.resolve(o.dict.get("Filter"));
    const filters = f === undefined ? [] : Array.isArray(f) ? f : [f];
    if (filters.length === 0) return raw;
    if (filters.length === 1 && filters[0].name === "FlateDecode") return inflateSync(raw);
    throw new Error(`unsupported filter ${JSON.stringify(filters)}`);
  }

  // Pages in order: [{ num, dict, resources, contents: [obj num] }]
  pages() {
    const root = this.resolve(this.trailer.get("Root")).dict;
    const out = [];
    const walk = (ref, inheritedRes) => {
      const node = this.obj(ref.ref[0]).dict;
      const res = node.get("Resources") ?? inheritedRes;
      if (node.get("Type").name === "Pages") {
        for (const kid of this.resolve(node.get("Kids"))) walk(kid, res);
        return;
      }
      let c = node.get("Contents");
      c = c === undefined ? [] : c.ref ? [c] : this.resolve(c);
      out.push({ num: ref.ref[0], dict: node, resources: this.resolve(res).dict, contents: c.map((r) => r.ref[0]) });
    };
    walk(root.get("Pages"), undefined);
    return out;
  }

  // Font resource name -> { num, baseFont, twoByte, toUnicode: Map(code -> string) }
  fonts(resources) {
    const out = new Map();
    const fd = this.resolve(resources?.get("Font"));
    if (!fd) return out;
    for (const [name, ref] of fd.dict) {
      const font = this.resolve(ref).dict;
      const enc = this.resolve(font.get("Encoding"));
      const twoByte = font.get("Subtype").name === "Type0" && enc?.name === "Identity-H";
      const tu = font.get("ToUnicode");
      out.set(name, {
        num: ref.ref?.[0],
        baseFont: font.get("BaseFont")?.name,
        twoByte,
        toUnicode: tu ? parseCMap(this.streamData(this.obj(tu.ref[0])).toString("latin1")) : new Map(),
      });
    }
    return out;
  }
}

// ToUnicode CMap: bfchar and bfrange (both forms). Codes are hex strings like "0012".
export function parseCMap(s) {
  const map = new Map();
  const utf16 = (h) => Buffer.from(h, "hex").swap16().toString("utf16le");
  for (const blk of s.matchAll(/beginbfchar([\s\S]*?)endbfchar/g))
    for (const m of blk[1].matchAll(/<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>/g)) map.set(m[1].toUpperCase(), utf16(m[2]));
  for (const blk of s.matchAll(/beginbfrange([\s\S]*?)endbfrange/g))
    for (const m of blk[1].matchAll(/<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]*>|\[[^\]]*\])/g)) {
      const lo = parseInt(m[1], 16), hi = parseInt(m[2], 16), w = m[1].length;
      const dsts = m[3].startsWith("[") ? [...m[3].matchAll(/<([0-9A-Fa-f]*)>/g)].map((x) => x[1]) : null;
      for (let c = lo; c <= hi; c++) {
        const key = c.toString(16).toUpperCase().padStart(w, "0");
        if (dsts) map.set(key, utf16(dsts[c - lo]));
        else {
          const base = Buffer.from(m[3].slice(1, -1), "hex");
          base.writeUInt16BE(base.readUInt16BE(base.length - 2) + (c - lo), base.length - 2);
          map.set(key, base.swap16().toString("utf16le"));
        }
      }
    }
  return map;
}

// ---------------------------------------------------------------------------------------------
// Content stream text scan. Calls onString({ font, str, op }) for every string operand of
// Tj, TJ, ' and ", with str.start/str.end as offsets into `data` (start points at "(" or "<").
// Only tracks Tf; enough for Typst output, which sets the font inside every BT block.

export function scanText(data, onString) {
  const p = new Parser(data, 0);
  let operands = [];
  let font = null;
  for (;;) {
    p.skipWs();
    if (p.p >= data.length) break;
    const v = p.value();
    if (v && v.kw !== undefined) {
      const op = v.kw;
      if (op === "Tf") font = operands[0].name;
      if (op === "BI") throw new Error("inline images unsupported");
      if (op === "Tj" || op === "'" || op === '"' || op === "TJ") {
        const arg = operands[operands.length - 1];
        for (const s of Array.isArray(arg) ? arg : [arg]) if (s && s.str) onString({ font, str: s, op });
      }
      operands = [];
    } else operands.push(v);
  }
}

export const hexOf = (buf) => buf.toString("hex").toUpperCase();
