//! Strict PDF object access through the cross-reference table, the way a
//! conforming reader resolves objects: last `startxref` -> classic `xref` table
//! -> `trailer`. Anything outside the subset this report uses (incremental
//! updates via /Prev, xref streams, encryption, '#' escapes in names, duplicate
//! dict keys, non-Flate filters, predictors) panics instead of guessing.

use alloc::vec::Vec;

use crate::inflate;

#[derive(Clone, Debug)]
pub enum Obj<'a> {
    Null,
    Bool(bool),
    Int(i64),
    Real,
    Name(&'a [u8]),
    Str,
    Arr(Vec<Obj<'a>>),
    Dict(Dict<'a>),
    Ref(u32, u16),
}

#[derive(Clone, Debug)]
pub struct Dict<'a>(pub Vec<(&'a [u8], Obj<'a>)>);

impl<'a> Dict<'a> {
    pub fn get(&self, key: &[u8]) -> Option<&Obj<'a>> {
        self.0.iter().find(|(k, _)| *k == key).map(|(_, v)| v)
    }

    pub fn name(&self, key: &[u8]) -> Option<&'a [u8]> {
        match self.get(key) {
            Some(Obj::Name(n)) => Some(n),
            _ => None,
        }
    }
}

impl<'a> Obj<'a> {
    pub fn dict(self) -> Dict<'a> {
        match self {
            Obj::Dict(d) => d,
            _ => panic!("expected dict"),
        }
    }
}

// Byte classes: 0 regular, 1 whitespace, 2 delimiter.
pub static CLASS: [u8; 256] = {
    let mut t = [0u8; 256];
    let ws = [0u8, 9, 10, 12, 13, 32];
    let mut k = 0;
    while k < ws.len() {
        t[ws[k] as usize] = 1;
        k += 1;
    }
    let dl = *b"()<>[]{}/%";
    k = 0;
    while k < dl.len() {
        t[dl[k] as usize] = 2;
        k += 1;
    }
    t
};

#[inline(always)]
pub fn is_ws(c: u8) -> bool {
    CLASS[c as usize] == 1
}

#[inline(always)]
pub fn is_regular(c: u8) -> bool {
    CLASS[c as usize] == 0
}

struct P<'a> {
    b: &'a [u8],
    i: usize,
}

impl<'a> P<'a> {
    fn skip_ws(&mut self) {
        while self.i < self.b.len() {
            let c = self.b[self.i];
            if is_ws(c) {
                self.i += 1;
            } else if c == b'%' {
                while self.i < self.b.len() && self.b[self.i] != b'\n' && self.b[self.i] != b'\r' {
                    self.i += 1;
                }
            } else {
                break;
            }
        }
    }

    fn peek(&self) -> u8 {
        assert!(self.i < self.b.len(), "unexpected end of pdf");
        self.b[self.i]
    }

    fn regular_token(&mut self) -> &'a [u8] {
        let s = self.i;
        while self.i < self.b.len() && is_regular(self.b[self.i]) {
            self.i += 1;
        }
        &self.b[s..self.i]
    }

    fn keyword(&mut self, kw: &[u8]) -> bool {
        let s = self.i;
        if self.regular_token() == kw {
            true
        } else {
            self.i = s;
            false
        }
    }

    fn uint(&mut self) -> Option<u64> {
        let s = self.i;
        let t = self.regular_token();
        if !t.is_empty() && t.len() <= 18 && t.iter().all(|c| c.is_ascii_digit()) {
            Some(t.iter().fold(0u64, |a, &c| a * 10 + (c - b'0') as u64))
        } else {
            self.i = s;
            None
        }
    }

    fn obj(&mut self, depth: u32) -> Obj<'a> {
        assert!(depth < 32, "pdf object nesting too deep");
        self.skip_ws();
        let c = self.peek();
        match c {
            b'/' => {
                self.i += 1;
                let n = self.regular_token();
                assert!(!n.contains(&b'#'), "escaped pdf names not supported");
                Obj::Name(n)
            }
            b'<' if self.b.get(self.i + 1) == Some(&b'<') => {
                self.i += 2;
                let mut d: Vec<(&'a [u8], Obj<'a>)> = Vec::new();
                loop {
                    self.skip_ws();
                    if self.peek() == b'>' {
                        assert!(self.b.get(self.i + 1) == Some(&b'>'), "bad dict end");
                        self.i += 2;
                        break;
                    }
                    let k = match self.obj(depth + 1) {
                        Obj::Name(n) => n,
                        _ => panic!("dict key is not a name"),
                    };
                    assert!(d.iter().all(|(e, _)| *e != k), "duplicate dict key");
                    let v = self.obj(depth + 1);
                    d.push((k, v));
                }
                Obj::Dict(Dict(d))
            }
            b'<' => {
                self.i += 1;
                while self.peek() != b'>' {
                    let h = self.b[self.i];
                    assert!(h.is_ascii_hexdigit() || is_ws(h), "bad hex string");
                    self.i += 1;
                }
                self.i += 1;
                Obj::Str
            }
            b'[' => {
                self.i += 1;
                let mut a = Vec::new();
                loop {
                    self.skip_ws();
                    if self.peek() == b']' {
                        self.i += 1;
                        break;
                    }
                    a.push(self.obj(depth + 1));
                }
                Obj::Arr(a)
            }
            b'(' => {
                self.i += 1;
                let mut nest = 1;
                while nest > 0 {
                    let ch = self.peek();
                    self.i += 1;
                    match ch {
                        b'\\' => self.i += 1,
                        b'(' => nest += 1,
                        b')' => nest -= 1,
                        _ => {}
                    }
                }
                Obj::Str
            }
            b'0'..=b'9' => {
                // Integer, or "num gen R".
                let s = self.i;
                let t = self.regular_token();
                if t.iter().all(|c| c.is_ascii_digit()) {
                    let n = parse_u(t);
                    let after = self.i;
                    self.skip_ws();
                    if let Some(g) = self.uint() {
                        self.skip_ws();
                        if self.keyword(b"R") {
                            assert!(n <= u32::MAX as u64 && g <= u16::MAX as u64, "bad ref");
                            return Obj::Ref(n as u32, g as u16);
                        }
                    }
                    self.i = after;
                    Obj::Int(n as i64)
                } else {
                    self.i = s;
                    self.number()
                }
            }
            b'+' | b'-' | b'.' => self.number(),
            _ => {
                let t = self.regular_token();
                match t {
                    b"true" => Obj::Bool(true),
                    b"false" => Obj::Bool(false),
                    b"null" => Obj::Null,
                    _ => panic!("unexpected pdf token"),
                }
            }
        }
    }

    fn number(&mut self) -> Obj<'a> {
        let t = self.regular_token();
        let (neg, digits) = match t.first() {
            Some(b'-') => (true, &t[1..]),
            Some(b'+') => (false, &t[1..]),
            _ => (false, t),
        };
        let dots = digits.iter().filter(|&&c| c == b'.').count();
        assert!(
            !digits.is_empty()
                && dots <= 1
                && digits.iter().all(|&c| c.is_ascii_digit() || c == b'.')
                && digits.iter().any(|c| c.is_ascii_digit()),
            "bad pdf number"
        );
        if dots == 0 {
            let v = parse_u(digits) as i64;
            Obj::Int(if neg { -v } else { v })
        } else {
            Obj::Real
        }
    }
}

fn parse_u(t: &[u8]) -> u64 {
    assert!(!t.is_empty() && t.len() <= 18, "bad integer");
    t.iter().fold(0u64, |a, &c| {
        assert!(c.is_ascii_digit(), "bad integer");
        a * 10 + (c - b'0') as u64
    })
}

pub struct Doc<'a> {
    pub pdf: &'a [u8],
    // (first object number, count, byte offset of the first 20-byte entry)
    sections: Vec<(u32, u32, usize)>,
    pub root: (u32, u16),
}

pub struct Loaded<'a> {
    pub obj: Obj<'a>,
    pub stream: Option<&'a [u8]>,
}

impl<'a> Doc<'a> {
    pub fn open(pdf: &'a [u8]) -> Doc<'a> {
        assert!(pdf.starts_with(b"%PDF-"), "not a pdf");
        // The LAST startxref in the file, followed by %%EOF and only whitespace.
        let kw = b"startxref";
        let mut k = pdf.len().checked_sub(kw.len()).expect("pdf too short");
        while &pdf[k..k + kw.len()] != kw {
            k = k.checked_sub(1).expect("no startxref");
        }
        let mut p = P { b: pdf, i: k + kw.len() };
        p.skip_ws();
        let xref_off = p.uint().expect("startxref offset") as usize;
        // Plain whitespace only: skip_ws would treat "%%EOF" as a comment.
        while p.i < pdf.len() && is_ws(pdf[p.i]) {
            p.i += 1;
        }
        assert!(p.b[p.i..].starts_with(b"%%EOF"), "missing %%EOF");
        assert!(pdf[p.i + 5..].iter().all(|&c| is_ws(c)), "data after %%EOF");

        let mut p = P { b: pdf, i: xref_off };
        assert!(p.keyword(b"xref"), "startxref does not point at an xref table");
        let mut sections: Vec<(u32, u32, usize)> = Vec::new();
        loop {
            p.skip_ws();
            if p.keyword(b"trailer") {
                break;
            }
            let start = p.uint().expect("xref subsection start");
            p.skip_ws();
            let count = p.uint().expect("xref subsection count");
            assert!(start + count <= u32::MAX as u64, "bad xref subsection");
            // Exactly one EOL (or space+EOL) before the fixed-size entries.
            while p.i < pdf.len() && (pdf[p.i] == b' ' || pdf[p.i] == b'\r' || pdf[p.i] == b'\n') {
                if pdf[p.i] == b'\n' {
                    p.i += 1;
                    break;
                }
                p.i += 1;
            }
            let (s, c) = (start as u32, count as u32);
            for &(s2, c2, _) in &sections {
                assert!(s + c <= s2 || s2 + c2 <= s, "overlapping xref subsections");
            }
            sections.push((s, c, p.i));
            p.i += 20 * c as usize;
            assert!(p.i <= pdf.len(), "xref overrun");
        }
        let trailer = p.obj(0).dict();
        for bad in [&b"Prev"[..], b"XRefStm", b"Encrypt"] {
            assert!(trailer.get(bad).is_none(), "unsupported trailer key");
        }
        let root = match trailer.get(b"Root") {
            Some(Obj::Ref(n, g)) => (*n, *g),
            _ => panic!("trailer /Root"),
        };
        Doc { pdf, sections, root }
    }

    fn offset_of(&self, num: u32, gen: u16) -> usize {
        let &(s, _, off) =
            self.sections.iter().find(|&&(s, c, _)| num >= s && num < s + c).expect("object not in xref");
        let e = &self.pdf[off + 20 * (num - s) as usize..][..20];
        assert!(e[..10].iter().all(|c| c.is_ascii_digit()) && e[10] == b' ', "bad xref entry");
        assert!(e[11..16].iter().all(|c| c.is_ascii_digit()) && e[16] == b' ', "bad xref entry");
        assert!(e[17] == b'n', "object is free");
        assert!(matches!(&e[18..20], b" \r" | b" \n" | b"\r\n"), "bad xref entry eol");
        assert!(parse_u(&e[11..16]) == gen as u64, "xref generation mismatch");
        parse_u(&e[..10]) as usize
    }

    pub fn load(&self, num: u32, gen: u16) -> Loaded<'a> {
        let off = self.offset_of(num, gen);
        let mut p = P { b: self.pdf, i: off };
        assert!(p.uint() == Some(num as u64), "object number mismatch at xref offset");
        p.skip_ws();
        assert!(p.uint() == Some(gen as u64), "generation mismatch at xref offset");
        p.skip_ws();
        assert!(p.keyword(b"obj"), "missing obj keyword");
        let obj = p.obj(0);
        p.skip_ws();
        if p.keyword(b"stream") {
            let d = match &obj {
                Obj::Dict(d) => d,
                _ => panic!("stream without dict"),
            };
            // "stream" is followed by CRLF or LF, then exactly /Length bytes.
            if self.pdf.get(p.i) == Some(&b'\r') {
                p.i += 1;
            }
            assert!(self.pdf.get(p.i) == Some(&b'\n'), "stream keyword not followed by EOL");
            p.i += 1;
            let len = match d.get(b"Length") {
                Some(Obj::Int(n)) => *n,
                Some(Obj::Ref(n, g)) => match self.load(*n, *g) {
                    Loaded { obj: Obj::Int(v), stream: None } => v,
                    _ => panic!("indirect /Length is not an integer"),
                },
                _ => panic!("stream /Length"),
            };
            assert!(len >= 0, "negative /Length");
            let data_start = p.i;
            let data_end = data_start + len as usize;
            assert!(data_end <= self.pdf.len(), "stream overrun");
            p.i = data_end;
            p.skip_ws();
            assert!(p.keyword(b"endstream"), "stream /Length does not end at endstream");
            p.skip_ws();
            assert!(p.keyword(b"endobj"), "missing endobj");
            Loaded { obj, stream: Some(&self.pdf[data_start..data_end]) }
        } else {
            assert!(p.keyword(b"endobj"), "missing endobj");
            Loaded { obj, stream: None }
        }
    }

    // Follow a reference (non-stream objects only); direct objects pass through.
    pub fn resolve(&self, o: &Obj<'a>) -> Obj<'a> {
        match o {
            Obj::Ref(n, g) => {
                let l = self.load(*n, *g);
                assert!(l.stream.is_none(), "expected a non-stream object");
                l.obj
            }
            other => other.clone(),
        }
    }

    // Follow a reference that may be a stream: None when it is one.
    pub fn resolve_any(&self, o: &Obj<'a>) -> Option<Obj<'a>> {
        match o {
            Obj::Ref(n, g) => {
                let l = self.load(*n, *g);
                if l.stream.is_some() {
                    None
                } else {
                    Some(l.obj)
                }
            }
            other => Some(other.clone()),
        }
    }

    // Load a stream object by reference and return its decoded bytes.
    pub fn stream(&self, o: &Obj<'a>, size_hint: usize) -> Vec<u8> {
        let (n, g) = match o {
            Obj::Ref(n, g) => (*n, *g),
            _ => panic!("stream must be an indirect object"),
        };
        let l = self.load(n, g);
        let d = l.obj.dict();
        let raw = l.stream.expect("not a stream");
        match d.get(b"DecodeParms") {
            None | Some(Obj::Null) => {}
            _ => panic!("/DecodeParms not supported"),
        }
        let flate = match d.get(b"Filter") {
            None => false,
            Some(Obj::Name(b"FlateDecode")) => true,
            Some(Obj::Arr(a)) if a.is_empty() => false,
            Some(Obj::Arr(a)) if a.len() == 1 && matches!(a[0], Obj::Name(b"FlateDecode")) => true,
            _ => panic!("unsupported stream filter"),
        };
        if flate {
            inflate::zlib_decompress(raw, size_hint)
        } else {
            raw.to_vec()
        }
    }
}
