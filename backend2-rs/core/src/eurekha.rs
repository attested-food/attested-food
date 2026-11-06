//! Eurekha Labs reports (the `mock-pdfs` template): redaction and key-value
//! extraction over the raw PDF the lab serves from S3.
//!
//! Redaction contract (mock-pdfs/README.md): the lab sets every customer field,
//! and nothing else, in one PII font (`XXXXXX+DejaVuSansMono`), as normalized
//! hex strings (4 hex digits per glyph) in uncompressed page content. Redacting
//! is replacing those hex digits with `0` (glyph 0, `.notdef`): same length,
//! nothing else moves.
//!
//! [`run`] derives the spans from the original itself, so the redaction policy
//! holds by construction: the only bytes that differ between the original and
//! the redacted file are PII-font glyph codes. It commits `sha256(redacted)`
//! and the spans, so anyone holding the published redacted PDF can check it is
//! this exact derivation, plus every non-customer key-value pair and result
//! row, and asserts no customer word reaches them.

use alloc::{string::String, vec::Vec};

use crate::extract::{check_xobjects, page_fonts, page_list_max};
use crate::pdf::{is_regular, is_ws, Dict, Doc, Obj};
use crate::sha::{sha256, sha256_in};
use crate::text::{decode_content, CMap, Text};
use crate::tlsn;

/// Labels of the customer block. Their values are PII-font runs and are never
/// emitted as key-value pairs.
pub const PII_KEYS: [&str; 3] = ["Client Name", "Address", "Contact Person"];

/// Column headers of the dates table, in order; the next four runs are the values.
const DATE_KEYS: [&str; 4] = ["Date of Sampling", "Date of Receipt", "Start Date of Analysis", "End Date of Analysis"];

#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct ResultRow {
    pub discipline: String,
    pub group: String,
    pub parameter: String,
    pub unit: String,
    pub method: String,
    pub result: String,
    pub rda: String,
    pub rda_pct: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Eurekha {
    /// `SHA256(pdf || blinder)`, the TLSNotary body commitment.
    pub body_commitment: [u8; 32],
    pub pdf_len: u32,
    /// `sha256` of the original with every PII-font glyph code set to `0`.
    pub redacted_sha256: [u8; 32],
    /// `[start, end)` byte ranges of the PII-font hex strings, sorted.
    pub spans: Vec<(u32, u32)>,
    /// Every non-customer `key : value` pair, in page order.
    pub kv: Vec<(String, String)>,
    pub results: Vec<ResultRow>,
}

impl Eurekha {
    /// Public-values layout: commitment, pdf length (u32 LE), redacted hash,
    /// spans (u32 count, then u32 LE pairs), kv pairs and result rows (u32
    /// count, then u64-LE-length-prefixed UTF-8 strings).
    pub fn encode(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(2048);
        out.extend_from_slice(&self.body_commitment);
        out.extend_from_slice(&self.pdf_len.to_le_bytes());
        out.extend_from_slice(&self.redacted_sha256);
        out.extend_from_slice(&(self.spans.len() as u32).to_le_bytes());
        for (s, e) in &self.spans {
            out.extend_from_slice(&s.to_le_bytes());
            out.extend_from_slice(&e.to_le_bytes());
        }
        out.extend_from_slice(&(self.kv.len() as u32).to_le_bytes());
        for (k, v) in &self.kv {
            put_str(&mut out, k);
            put_str(&mut out, v);
        }
        out.extend_from_slice(&(self.results.len() as u32).to_le_bytes());
        for r in &self.results {
            for s in [&r.discipline, &r.group, &r.parameter, &r.unit, &r.method, &r.result, &r.rda, &r.rda_pct] {
                put_str(&mut out, s);
            }
        }
        out
    }
}

/// A [`Eurekha`] report served by the lab's S3 bucket under a TLSNotary
/// attestation ([`run_attested`]).
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct EurekhaAttested {
    pub signer: Signer,
    /// The notary-signed server name (the bucket host).
    pub server_name: String,
    /// TLS session time (unix seconds).
    pub session_time: u64,
    /// `sha256` of the S3 object key, never the key itself: it is the
    /// capability to the unredacted original.
    pub key_sha256: [u8; 32],
    pub report: Eurekha,
}

/// Who checked the notary signature.
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Signer {
    /// The guest recovered this notary address from the header signature; a
    /// verifier checks it is the notary it trusts.
    Notary([u8; 20]),
    /// The guest did not: a verifier must check a notary signature over
    /// `keccak256(header)` (the BCS attestation header, which pins every leaf).
    Header(Vec<u8>),
}

impl EurekhaAttested {
    /// `0x00 | notary` or `0x01 | header (u64-LE-length-prefixed)`, then
    /// `session_time u64 LE | server_name (u64-LE-length-prefixed) |
    /// key_sha256 |` [`Eurekha::encode`].
    pub fn encode(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(2048);
        match &self.signer {
            Signer::Notary(a) => {
                out.push(0);
                out.extend_from_slice(a);
            }
            Signer::Header(h) => {
                out.push(1);
                out.extend_from_slice(&(h.len() as u64).to_le_bytes());
                out.extend_from_slice(h);
            }
        }
        out.extend_from_slice(&self.session_time.to_le_bytes());
        put_str(&mut out, &self.server_name);
        out.extend_from_slice(&self.key_sha256);
        out.extend_from_slice(&self.report.encode());
        out
    }
}

fn put_str(out: &mut Vec<u8>, s: &str) {
    out.extend_from_slice(&(s.len() as u64).to_le_bytes());
    out.extend_from_slice(s.as_bytes());
}

/// `XXXXXX+DejaVuSansMono`: a 6-letter subset tag, then the PII font.
fn is_pii_basefont(n: &[u8]) -> bool {
    n.len() == 21 && n[6] == b'+' && n[..6].iter().all(|c| c.is_ascii_uppercase()) && &n[7..] == b"DejaVuSansMono"
}

/// Resource names of the page's PII fonts.
fn pii_font_names<'a>(doc: &Doc<'a>, res: &Dict<'a>) -> Vec<&'a [u8]> {
    let mut out = Vec::new();
    if let Some(f) = res.get(b"Font") {
        for (name, r) in &doc.resolve(f).dict().0 {
            if doc.resolve(r).dict().name(b"BaseFont").is_some_and(is_pii_basefont) {
                out.push(*name);
            }
        }
    }
    out
}

/// The page's single content stream, uncompressed: its bytes and its offset in
/// the PDF (normalize writes one unfiltered stream per page).
fn raw_content<'a>(doc: &Doc<'a>, page: &Dict<'a>) -> (&'a [u8], usize) {
    let (n, g) = match page.get(b"Contents") {
        Some(Obj::Ref(n, g)) => (*n, *g),
        _ => panic!("/Contents must be one stream reference"),
    };
    let l = doc.load(n, g);
    assert!(l.obj.dict().get(b"Filter").is_none(), "content stream must be uncompressed");
    let s = l.stream.expect("/Contents is not a stream");
    (s, s.as_ptr() as usize - doc.pdf.as_ptr() as usize)
}

/// Hex strings shown (Tj, TJ, ', ") while a PII font is selected, as absolute
/// `[start, end)` ranges of their digits, with the font that showed them.
fn pii_spans<'a>(b: &[u8], base: usize, pii: &[&'a [u8]], out: &mut Vec<(u32, u32, &'a [u8])>) {
    let n = b.len();
    let (mut i, mut depth) = (0usize, 0u32);
    let mut last_name: Option<&[u8]> = None;
    let mut font: Option<&'a [u8]> = None;
    // Strings since the last operator: (start, end, is_hex), and inside [ ].
    let mut last: Option<(usize, usize, bool)> = None;
    let mut arr: Vec<(usize, usize, bool)> = Vec::new();
    let mut in_arr = false;
    while i < n {
        let c = b[i];
        if is_ws(c) {
            i += 1;
        } else if c == b'%' {
            while i < n && b[i] != b'\n' && b[i] != b'\r' {
                i += 1;
            }
        } else if c == b'/' {
            let s = i + 1;
            i = s;
            while i < n && is_regular(b[i]) {
                i += 1;
            }
            last_name = Some(&b[s..i]);
        } else if c == b'<' && b.get(i + 1) == Some(&b'<') {
            depth += 1;
            i += 2;
        } else if c == b'>' && b.get(i + 1) == Some(&b'>') {
            depth = depth.checked_sub(1).expect("unbalanced >>");
            i += 2;
        } else if c == b'<' {
            let s = i + 1;
            i = s;
            while i < n && b[i] != b'>' {
                i += 1;
            }
            assert!(i < n, "unterminated hex string");
            if depth == 0 {
                let t = (s, i, true);
                if in_arr {
                    arr.push(t)
                } else {
                    last = Some(t)
                }
            }
            i += 1;
        } else if c == b'(' {
            let s = i + 1;
            let mut lvl = 1u32;
            i = s;
            while i < n && lvl > 0 {
                match b[i] {
                    b'\\' => i += 1,
                    b'(' => lvl += 1,
                    b')' => lvl -= 1,
                    _ => {}
                }
                i += 1;
            }
            assert!(lvl == 0, "unterminated literal string");
            if depth == 0 {
                let t = (s, i - 1, false);
                if in_arr {
                    arr.push(t)
                } else {
                    last = Some(t)
                }
            }
        } else if c == b'[' {
            in_arr = true;
            arr.clear();
            i += 1;
        } else if c == b']' {
            in_arr = false;
            i += 1;
        } else if c == b'{' || c == b'}' {
            i += 1;
        } else {
            let s = i;
            while i < n && is_regular(b[i]) {
                i += 1;
            }
            assert!(i > s, "unexpected byte in content stream");
            let w = &b[s..i];
            if w[0].is_ascii_digit() || w[0] == b'-' || w[0] == b'+' || w[0] == b'.' || depth > 0 {
                continue;
            }
            match w {
                b"Tf" => font = last_name.and_then(|f| pii.iter().copied().find(|p| *p == f)).or(None),
                b"BI" => panic!("inline images not supported"),
                b"Tj" | b"'" | b"\"" | b"TJ" => {
                    if let Some(f) = font {
                        let shown: &[(usize, usize, bool)] = if w == b"TJ" { &arr } else { last.as_slice() };
                        for &(s, e, hex) in shown {
                            assert!(hex, "PII text must be a hex string");
                            assert!((e - s) % 4 == 0 && e > s, "PII string is not 2-byte glyph codes");
                            assert!(b[s..e].iter().all(u8::is_ascii_hexdigit), "PII string is not normalized hex");
                            out.push(((base + s) as u32, (base + e) as u32, f));
                        }
                    }
                }
                _ => {}
            }
            if w != b"Tf" {
                last = None;
            }
        }
    }
}

fn hex_val(c: u8) -> u16 {
    match c {
        b'0'..=b'9' => (c - b'0') as u16,
        b'a'..=b'f' => (c - b'a' + 10) as u16,
        _ => (c - b'A' + 10) as u16,
    }
}

/// Each PII string decoded and trimmed (padding is U+00A0), lowercased, 4+
/// chars. The leak check asserts no emitted value contains one: a whole
/// customer line, not single words, since e.g. the customer's state can also
/// appear in the lab's public address.
fn pii_lines(pdf: &[u8], spans: &[(u32, u32, &[u8])], cmaps: &[(&[u8], &CMap)]) -> Vec<String> {
    let mut lines = Vec::new();
    for &(s, e, f) in spans {
        let cmap = match cmaps.iter().find(|(n, _)| *n == f) {
            Some((_, m)) => *m,
            None => continue,
        };
        let mut text = String::new();
        for g in pdf[s as usize..e as usize].chunks(4) {
            let code = g.iter().fold(0u16, |a, &c| a << 4 | hex_val(c));
            text.push(cmap.get(code).unwrap_or(' '));
        }
        let line = text.trim_matches(|c: char| c.is_whitespace()).to_lowercase();
        if line.chars().count() >= 4 {
            lines.push(line);
        }
    }
    lines
}

fn is_int(s: &str) -> bool {
    !s.is_empty() && s.bytes().all(|c| c.is_ascii_digit())
}

/// Key-value pairs and result rows from the decoded runs, in page order.
fn extract(runs: &[&str]) -> (Vec<(String, String)>, Vec<ResultRow>) {
    let mut kv = Vec::new();
    let mut rows = Vec::new();
    let (mut discipline, mut group) = (String::new(), String::new());
    let mut i = 0;
    while i < runs.len() {
        let r = runs[i].trim();
        // `Key : Value` in one run.
        if let Some((k, v)) = r.split_once(" : ") {
            let (k, v) = (k.trim(), v.trim());
            match k {
                "Discipline" => discipline = v.into(),
                "Group" => group = v.into(),
                _ => kv.push((k.into(), v.into())),
            }
            i += 1;
        } else if r.starts_with("ULR-") {
            kv.push(("ULR".into(), r.into()));
            i += 1;
        } else if i == 0 {
            kv.push(("Lab".into(), r.into()));
            i += 1;
        } else if let Some(v) = r.strip_prefix("Accreditation No. ") {
            kv.push(("Accreditation No.".into(), v.trim().into()));
            i += 1;
        } else if r == "(Reviewed & Authorised By)" && i >= 2 {
            kv.push(("Signatory".into(), runs[i - 2].trim().into()));
            kv.push(("Signatory Title".into(), runs[i - 1].trim().into()));
            i += 1;
        // Grid row: `Key`, `:`, `Value`.
        } else if runs.get(i + 1).map(|s| s.trim()) == Some(":") && i + 2 < runs.len() {
            if !PII_KEYS.contains(&r) {
                kv.push((r.into(), runs[i + 2].trim().into()));
            }
            i += 3;
        } else if r == DATE_KEYS[0] && runs.len() >= i + 8 && (0..4).all(|j| runs[i + j].trim() == DATE_KEYS[j]) {
            for j in 0..4 {
                kv.push((DATE_KEYS[j].into(), runs[i + 4 + j].trim().into()));
            }
            i += 8;
        // Results table header ends with `% RDA`; rows are 7 runs from `1`.
        } else if r == "% RDA" {
            i += 1;
            let mut next = 1u32;
            while i + 6 < runs.len() && is_int(runs[i].trim()) && runs[i].trim().parse() == Ok(next) {
                let c = |k: usize| String::from(runs[i + k].trim());
                rows.push(ResultRow {
                    discipline: discipline.clone(),
                    group: group.clone(),
                    parameter: c(1),
                    unit: c(2),
                    method: c(3),
                    result: c(4),
                    rda: c(5),
                    rda_pct: c(6),
                });
                next += 1;
                i += 7;
            }
        } else {
            i += 1;
        }
    }
    // The page header repeats on every page: keep one copy of each pair, and
    // refuse a key that shows two different values.
    let mut dedup: Vec<(String, String)> = Vec::with_capacity(kv.len());
    for (k, v) in kv {
        match dedup.iter().find(|(dk, _)| *dk == k) {
            Some((_, dv)) => assert!(*dv == v, "conflicting values for a report field"),
            None => dedup.push((k, v)),
        }
    }
    (dedup, rows)
}

/// The whole Eurekha statement over `buf = pdf || blinder`.
pub fn run(buf: &[u8]) -> Eurekha {
    assert!(buf.len() > 16, "input too short");
    let pdf_len = buf.len() - 16;
    let pdf = &buf[..pdf_len];
    assert!(pdf.starts_with(b"%PDF-"), "body is not a PDF");
    let body_commitment = sha256_in(buf, 0, buf.len());

    let doc = Doc::open(pdf);
    let pages = page_list_max(&doc, usize::MAX);
    let mut spans: Vec<(u32, u32, &[u8])> = Vec::new();
    let mut text = Text::new();
    let mut fonts_all = Vec::new();
    for (page, inherited) in &pages {
        let res = match page.get(b"Resources") {
            Some(r) => doc.resolve(r).dict(),
            None => inherited.clone().expect("page has no /Resources"),
        };
        check_xobjects(&doc, &res);
        let pii = pii_font_names(&doc, &res);
        let (content, base) = raw_content(&doc, page);
        pii_spans(content, base, &pii, &mut spans);
        let fonts = page_fonts(&doc, &res);
        decode_content(content, &fonts, &mut text);
        fonts_all.extend(fonts.into_iter().filter(|f| pii.contains(&f.name)));
    }
    assert!(!spans.is_empty(), "no PII-font text: not a Eurekha report");
    spans.sort_unstable_by_key(|s| s.0);

    let mut redacted = pdf.to_vec();
    for &(s, e, _) in &spans {
        redacted[s as usize..e as usize].fill(b'0');
    }
    let redacted_sha256 = sha256(&redacted);

    let runs: Vec<&str> = (0..text.runs.len()).map(|k| text.run(k)).collect();
    let (kv, results) = extract(&runs);
    assert!(kv.iter().any(|(k, _)| k == "Report Number"), "no Report Number");
    assert!(!results.is_empty(), "no result rows");

    let cmaps: Vec<(&[u8], &CMap)> = fonts_all.iter().filter_map(|f| f.cmap.as_ref().map(|m| (f.name, m))).collect();
    let lines = pii_lines(pdf, &spans, &cmaps);
    assert!(lines.len() > 1, "customer block not found");
    let mut public: Vec<&str> = Vec::new();
    for (k, v) in &kv {
        public.extend([k.as_str(), v.as_str()]);
    }
    for r in &results {
        public.extend([&r.discipline[..], &r.group, &r.parameter, &r.unit, &r.method, &r.result, &r.rda, &r.rda_pct]);
    }
    for p in &public {
        let p = p.to_lowercase();
        for l in &lines {
            assert!(!p.contains(l.as_str()), "PII would be committed");
        }
    }

    Eurekha {
        body_commitment,
        pdf_len: pdf_len as u32,
        redacted_sha256,
        spans: spans.iter().map(|&(s, e, _)| (s, e)).collect(),
        kv,
        results,
    }
}

/// TLS + redaction in one computation: [`tlsn::check`] the attestation against
/// the pinned notary, [`tlsn::open_request`] for the object key, [`run`] over
/// `buf = pdf || blinder`, then bind its commitment and length to the
/// attested body.
pub fn run_attested(
    buf: &[u8],
    t: &tlsn::OnchainTlsn,
    req: &tlsn::OnchainRequest,
    secret: &tlsn::RequestSecret,
    notary: &[u8; 20],
    sig: &impl tlsn::NotarySignature,
) -> Result<EurekhaAttested, tlsn::TlsnError> {
    let body = tlsn::check(t, notary, sig)?;
    attested(buf, t, req, secret, body, Signer::Notary(*notary))
}

/// [`run_attested`] with the notary signature left to the verifier
/// ([`tlsn::check_unsigned`], [`Signer::Header`]).
pub fn run_attested_unsigned(
    buf: &[u8],
    t: &tlsn::OnchainTlsn,
    req: &tlsn::OnchainRequest,
    secret: &tlsn::RequestSecret,
) -> Result<EurekhaAttested, tlsn::TlsnError> {
    let body = tlsn::check_unsigned(t)?;
    attested(buf, t, req, secret, body, Signer::Header(t.header.clone()))
}

fn attested(
    buf: &[u8],
    t: &tlsn::OnchainTlsn,
    req: &tlsn::OnchainRequest,
    secret: &tlsn::RequestSecret,
    body: tlsn::AttestedBody,
    signer: Signer,
) -> Result<EurekhaAttested, tlsn::TlsnError> {
    let request = tlsn::open_request(t, &body, req, secret)?;
    let report = run(buf);
    tlsn::bind_body(&body, &report.body_commitment, report.pdf_len as u64)?;
    Ok(EurekhaAttested {
        signer,
        server_name: body.server_name.into(),
        session_time: request.session_time,
        key_sha256: request.key_sha256,
        report,
    })
}
