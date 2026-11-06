//! ToUnicode CMap parsing and content-stream text extraction (Identity-H fonts).

use alloc::{string::String, vec::Vec};

use crate::pdf::{is_regular, is_ws, CLASS};

const NONE: u32 = u32::MAX;

/// Code -> unicode scalar, as a direct table (codes are dense and small).
pub struct CMap {
    map: Vec<u32>,
}

impl CMap {
    pub fn empty() -> CMap {
        CMap { map: Vec::new() }
    }

    fn set(&mut self, code: u32, cp: u32) {
        let code = code as usize;
        if code >= self.map.len() {
            self.map.resize(code + 1, NONE);
        }
        self.map[code] = cp;
    }

    #[inline(always)]
    pub(crate) fn get(&self, code: u16) -> Option<char> {
        match self.map.get(code as usize) {
            Some(&cp) if cp != NONE => Some(unsafe { char::from_u32_unchecked(cp) }),
            _ => None,
        }
    }
}

// Hex digit value, or 0x10 for any other byte.
static HEX: [u8; 256] = {
    let mut t = [0x10u8; 256];
    let mut k = 0;
    while k < 10 {
        t[b'0' as usize + k] = k as u8;
        k += 1;
    }
    k = 0;
    while k < 6 {
        t[b'a' as usize + k] = 10 + k as u8;
        t[b'A' as usize + k] = 10 + k as u8;
        k += 1;
    }
    t
};

fn hex_val(c: u8) -> u32 {
    match c {
        b'0'..=b'9' => (c - b'0') as u32,
        b'a'..=b'f' => (c - b'a' + 10) as u32,
        b'A'..=b'F' => (c - b'A' + 10) as u32,
        _ => panic!("bad hex digit"),
    }
}

// Value of the first `max` hex digits of a "<...>" token body (whitespace skipped).
fn hex_prefix(h: &[u8], max: usize) -> (u32, usize) {
    let mut v = 0u32;
    let mut n = 0usize;
    for &c in h {
        if is_ws(c) {
            continue;
        }
        if n < max {
            v = (v << 4) | hex_val(c);
        } else {
            hex_val(c);
        }
        n += 1;
    }
    (v, n)
}

enum Tok<'a> {
    Hex(&'a [u8]),
    Word(&'a [u8]),
    Open,
    Close,
    Other,
}

/// Parse bfchar / bfrange entries of a ToUnicode CMap. A destination maps to
/// its first UTF-16 code unit; bfrange entries are applied after bfchar ones
/// (so they win on overlap), matching the original guest.
pub fn parse_cmap(data: &[u8]) -> CMap {
    let mut toks: Vec<Tok> = Vec::new();
    let mut i = 0;
    while i < data.len() {
        let c = data[i];
        if is_ws(c) {
            i += 1;
        } else if c == b'%' {
            while i < data.len() && data[i] != b'\n' && data[i] != b'\r' {
                i += 1;
            }
        } else if c == b'<' && data.get(i + 1) == Some(&b'<') {
            toks.push(Tok::Other);
            i += 2;
        } else if c == b'>' && data.get(i + 1) == Some(&b'>') {
            toks.push(Tok::Other);
            i += 2;
        } else if c == b'<' {
            let s = i + 1;
            while data[i] != b'>' {
                i += 1;
            }
            toks.push(Tok::Hex(&data[s..i]));
            i += 1;
        } else if c == b'[' {
            toks.push(Tok::Open);
            i += 1;
        } else if c == b']' {
            toks.push(Tok::Close);
            i += 1;
        } else if c == b'(' {
            let mut nest = 1;
            i += 1;
            while nest > 0 {
                match data[i] {
                    b'\\' => i += 1,
                    b'(' => nest += 1,
                    b')' => nest -= 1,
                    _ => {}
                }
                i += 1;
            }
            toks.push(Tok::Other);
        } else if c == b'/' {
            i += 1;
            while i < data.len() && is_regular(data[i]) {
                i += 1;
            }
            toks.push(Tok::Other);
        } else if is_regular(c) {
            let s = i;
            while i < data.len() && is_regular(data[i]) {
                i += 1;
            }
            toks.push(Tok::Word(&data[s..i]));
        } else {
            // Stray ')', '>', '{', '}'.
            toks.push(Tok::Other);
            i += 1;
        }
    }

    let mut cmap = CMap::empty();
    let mut ranges: Vec<(u32, u32, u32)> = Vec::new();
    let mut t = 0;
    while t < toks.len() {
        match toks[t] {
            Tok::Word(b"beginbfchar") => {
                t += 1;
                loop {
                    match (&toks[t], toks.get(t + 1)) {
                        (Tok::Word(b"endbfchar"), _) => break,
                        (Tok::Hex(src), Some(Tok::Hex(dst))) => {
                            let (code, _) = hex_prefix(src, 8);
                            let (cp, n) = hex_prefix(dst, 4);
                            if n >= 4 {
                                if let Some(ch) = char::from_u32(cp) {
                                    cmap.set(code, ch as u32);
                                }
                            }
                            t += 2;
                        }
                        _ => panic!("bad bfchar entry"),
                    }
                }
            }
            Tok::Word(b"beginbfrange") => {
                t += 1;
                loop {
                    match &toks[t] {
                        Tok::Word(b"endbfrange") => break,
                        Tok::Hex(lo) => {
                            let hi = match &toks[t + 1] {
                                Tok::Hex(h) => *h,
                                _ => panic!("bad bfrange entry"),
                            };
                            let (lo, _) = hex_prefix(lo, 8);
                            let (hi, _) = hex_prefix(hi, 8);
                            assert!(lo <= hi && hi <= 0xffff, "bad bfrange bounds");
                            match &toks[t + 2] {
                                Tok::Hex(dst) => {
                                    let (base, n) = hex_prefix(dst, 4);
                                    assert!(n >= 4, "bad bfrange destination");
                                    ranges.push((lo, hi, base));
                                    t += 3;
                                }
                                Tok::Open => {
                                    // "<lo> <hi> [<d0> <d1> ...]": one destination per code.
                                    t += 3;
                                    let mut code = lo;
                                    while !matches!(toks[t], Tok::Close) {
                                        match &toks[t] {
                                            Tok::Hex(d) => {
                                                let (cp, n) = hex_prefix(d, 4);
                                                assert!(n >= 4 && code <= hi, "bad bfrange array");
                                                ranges.push((code, code, cp));
                                                code += 1;
                                            }
                                            _ => panic!("bad bfrange array"),
                                        }
                                        t += 1;
                                    }
                                    t += 1;
                                }
                                _ => panic!("bad bfrange entry"),
                            }
                        }
                        _ => panic!("bad bfrange entry"),
                    }
                }
            }
            _ => {}
        }
        t += 1;
    }
    for (lo, hi, base) in ranges {
        for off in 0..=(hi - lo) {
            if let Some(ch) = char::from_u32(base + off) {
                cmap.set(lo + off, ch as u32);
            }
        }
    }
    cmap
}

/// Decoded text: one buffer, runs as byte ranges into it.
pub struct Text {
    pub buf: String,
    pub runs: Vec<(u32, u32)>,
}

impl Text {
    pub fn new() -> Text {
        Text { buf: String::with_capacity(8192), runs: Vec::with_capacity(512) }
    }

    pub fn run(&self, k: usize) -> &str {
        let (s, e) = self.runs[k];
        &self.buf[s as usize..e as usize]
    }
}

pub struct Font<'a> {
    pub name: &'a [u8],
    // None: the font has no ToUnicode CMap, so its text decodes to nothing.
    pub cmap: Option<CMap>,
}

/// Decode every text-showing operator (Tj, TJ, ', ") of a content stream into
/// unicode runs through the current font's ToUnicode CMap. Codes are 2 bytes
/// (Identity-H). Strings inside dicts (marked-content property lists) are not
/// shown text and are skipped. Inline images (BI) are rejected.
pub fn decode_content(b: &[u8], fonts: &[Font], text: &mut Text) {
    let n = b.len();
    let mut i = 0;
    let mut dict_depth: u32 = 0;
    let mut last_name: Option<&[u8]> = None;
    let mut cur_font: Option<&CMap> = None;
    let mut have_font = false;
    let mut pending: Vec<u16> = Vec::with_capacity(256);
    let mut pend_byte: Option<u8> = None;
    while i < n {
        let c = b[i];
        // Fast paths for the two dominant byte kinds: whitespace and numbers.
        let cls = CLASS[c as usize];
        if cls == 1 {
            i += 1;
            continue;
        }
        if cls == 0 && (c.wrapping_sub(b'0') < 10 || c == b'.' || c == b'-' || c == b'+') {
            i += 1;
            while i < n && CLASS[b[i] as usize] == 0 {
                i += 1;
            }
            continue;
        }
        match c {
            b'/' => {
                let s = i + 1;
                i = s;
                while i < n && is_regular(b[i]) {
                    i += 1;
                }
                last_name = Some(&b[s..i]);
            }
            b'<' => {
                if i + 1 < n && b[i + 1] == b'<' {
                    dict_depth += 1;
                    i += 2;
                } else {
                    // Hex string: 4 hex digits per 2-byte code.
                    i += 1;
                    let mut acc: u32 = 0;
                    let mut nd = 0u32;
                    // Fast path: four hex digits at a time while no whitespace intervenes.
                    while i + 4 <= n {
                        let v = (HEX[b[i] as usize] as u32) << 12
                            | (HEX[b[i + 1] as usize] as u32) << 8
                            | (HEX[b[i + 2] as usize] as u32) << 4
                            | HEX[b[i + 3] as usize] as u32;
                        // Non-hex bytes map to 0x10, so OR-ing the lookups detects one.
                        let bad = (HEX[b[i] as usize]
                            | HEX[b[i + 1] as usize]
                            | HEX[b[i + 2] as usize]
                            | HEX[b[i + 3] as usize])
                            & 0x10;
                        if bad != 0 {
                            break;
                        }
                        if dict_depth == 0 {
                            pending.push(v as u16);
                        }
                        i += 4;
                    }
                    while b[i] != b'>' {
                        let h = b[i];
                        i += 1;
                        if is_ws(h) {
                            continue;
                        }
                        acc = (acc << 4) | hex_val(h);
                        nd += 1;
                        if nd == 4 {
                            if dict_depth == 0 {
                                pending.push(acc as u16);
                            }
                            acc = 0;
                            nd = 0;
                        }
                    }
                    i += 1;
                    assert!(nd == 0, "hex string is not a whole number of 2-byte codes");
                }
            }
            b'>' => {
                assert!(i + 1 < n && b[i + 1] == b'>' && dict_depth > 0, "stray '>'");
                dict_depth -= 1;
                i += 2;
            }
            b'(' => {
                // Literal string, bytes paired into 2-byte codes.
                i += 1;
                let mut nest = 1;
                loop {
                    let ch = b[i];
                    i += 1;
                    let byte = match ch {
                        b'(' => {
                            nest += 1;
                            ch
                        }
                        b')' => {
                            nest -= 1;
                            if nest == 0 {
                                break;
                            }
                            ch
                        }
                        b'\\' => {
                            let e = b[i];
                            i += 1;
                            match e {
                                b'n' => b'\n',
                                b'r' => b'\r',
                                b't' => b'\t',
                                b'b' => 8,
                                b'f' => 12,
                                b'0'..=b'7' => {
                                    let mut v = (e - b'0') as u32;
                                    for _ in 0..2 {
                                        if matches!(b[i], b'0'..=b'7') {
                                            v = v * 8 + (b[i] - b'0') as u32;
                                            i += 1;
                                        }
                                    }
                                    v as u8
                                }
                                b'\r' => {
                                    if b[i] == b'\n' {
                                        i += 1;
                                    }
                                    continue;
                                }
                                b'\n' => continue,
                                other => other,
                            }
                        }
                        _ => ch,
                    };
                    if dict_depth == 0 {
                        match pend_byte.take() {
                            Some(hi) => pending.push(((hi as u16) << 8) | byte as u16),
                            None => pend_byte = Some(byte),
                        }
                    }
                }
                assert!(pend_byte.is_none(), "literal string is not a whole number of codes");
            }
            b'%' => {
                while i < n && b[i] != b'\n' && b[i] != b'\r' {
                    i += 1;
                }
            }
            b'[' | b']' | b'{' | b'}' => i += 1,
            b')' => panic!("stray ')'"),
            _ => {
                let s = i;
                i += 1;
                while i < n && is_regular(b[i]) {
                    i += 1;
                }
                let first = c;
                if first.is_ascii_digit() || first == b'-' || first == b'+' || first == b'.' {
                    continue;
                }
                if dict_depth > 0 {
                    continue;
                }
                // Operators: compare as (length, bytes) instead of slice equality.
                let l = i - s;
                let k1 = if l >= 2 { b[s + 1] } else { 0 };
                let key = (l, first, k1);
                match key {
                    (2, b'T', b'f') => {
                        let name = last_name.expect("Tf without font name");
                        let f = fonts.iter().find(|f| f.name == name);
                        have_font = f.is_some();
                        cur_font = f.and_then(|f| f.cmap.as_ref());
                    }
                    (2, b'T', b'j') | (2, b'T', b'J') | (1, b'\'', _) | (1, b'"', _) => {
                        if !pending.is_empty() {
                            assert!(have_font, "text shown with no font selected");
                        }
                        if let Some(m) = cur_font {
                            let start = text.buf.len() as u32;
                            for &g in &pending {
                                if let Some(ch) = m.get(g) {
                                    text.buf.push(ch);
                                }
                            }
                            let end = text.buf.len() as u32;
                            if end > start {
                                text.runs.push((start, end));
                            }
                        }
                    }
                    (2, b'B', b'I') | (2, b'I', b'D') | (2, b'E', b'I') => {
                        panic!("inline images not supported")
                    }
                    (4, b't', _) | (5, b'f', _) | (4, b'n', _) => {
                        // true / false / null are operands, not operators.
                        let t = &b[s..i];
                        if t == b"true" || t == b"false" || t == b"null" {
                            continue;
                        }
                    }
                    _ => {}
                }
                pending.clear();
                last_name = None;
            }
        }
    }
    assert!(dict_depth == 0, "unterminated dict in content stream");
}
