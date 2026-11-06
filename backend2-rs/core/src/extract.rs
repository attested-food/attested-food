//! The extraction pipeline, target independent: the same code runs in every
//! zkVM guest and in the native tests.

use alloc::{string::String, string::ToString, vec, vec::Vec};

use crate::pdf::{Dict, Doc, Obj};
use crate::sha::sha256_in;
use crate::text::{decode_content, parse_cmap, Font, Text};

// SP1 cycle-tracker markers (`track` feature, guest builds only).
#[cfg(feature = "track")]
macro_rules! track {
    ($s:literal) => {
        std::println!($s)
    };
}
#[cfg(not(feature = "track"))]
macro_rules! track {
    ($s:literal) => {};
}

#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Row {
    pub label: String,
    pub units: String,
    pub method: String,
    pub value: String,
    pub rda: String,
    pub pct: String,
}

pub struct Output {
    pub body_commitment: [u8; 32],
    pub pdf_len: u32,
    pub report_no: String,
    pub product: String,
    pub ulr: String,
    pub issue_date: String,
    pub rows: Vec<Row>,
    /// Every decoded page-1 text run (`std` builds only; never committed).
    pub runs: Vec<String>,
    /// The customer-block words the PII assert checked against (`std` builds
    /// only; never committed). Lets a host re-check its public values.
    pub pii: Vec<String>,
}

/// The whole guest computation. `chosen` are analyte labels, matched
/// case-insensitively against the table's parameter names.
///
/// `buf` is the attested response body (the PDF) followed by the 16-byte
/// TLSNotary blinder, so the commitment `SHA256(body || blinder)` is hashed in
/// place over one allocation.
///
/// `#[inline]` so the body is optimized inside the guest crate: across the
/// crate boundary the SP1 guest measured ~36k more cycles (+1.7%).
#[inline]
pub fn run(buf: &[u8], chosen: &[String]) -> Output {
    assert!(buf.len() > 16, "input too short");
    let pdf_len = buf.len() - 16;
    let pdf = &buf[..pdf_len];
    assert!(pdf.starts_with(b"%PDF-"), "body is not a PDF");

    track!("cycle-tracker-report-start: sha");
    let body_commitment = sha256_in(buf, 0, buf.len());
    track!("cycle-tracker-report-end: sha");

    track!("cycle-tracker-report-start: layout");
    let doc = Doc::open(pdf);
    let pages = page_list(&doc);
    track!("cycle-tracker-report-end: layout");
    let mut text = Text::new();
    for (page, inherited) in &pages {
        track!("cycle-tracker-report-start: fonts");
        let res = match page.get(b"Resources") {
            Some(r) => doc.resolve(r).dict(),
            None => inherited.clone().expect("page has no /Resources"),
        };
        let fonts = page_fonts(&doc, &res);
        track!("cycle-tracker-report-start: f_xobj");
        check_xobjects(&doc, &res);
        track!("cycle-tracker-report-end: f_xobj");
        track!("cycle-tracker-report-end: fonts");

        track!("cycle-tracker-report-start: inflate");
        let content = page_content(&doc, page);
        track!("cycle-tracker-report-end: inflate");

        track!("cycle-tracker-report-start: decode");
        decode_content(&content, &fonts, &mut text);
        track!("cycle-tracker-report-end: decode");
    }

    track!("cycle-tracker-report-start: extract");
    let runs: Vec<&str> = (0..text.runs.len()).map(|k| text.run(k)).collect();
    let ulr = runs.iter().find(|r| r.starts_with("ULR-")).map(|s| s.to_string()).unwrap_or_default();
    let issue_date = find_issue_date(&runs);
    let chosen_lc: Vec<String> = chosen.iter().map(|s| s.trim().to_lowercase()).collect();
    let rows = extract_rows(&runs, &chosen_lc);

    let report_no = find_after(&runs, "Report Number", is_report_no);
    let product = find_after(&runs, "Sample Name", |r| !r.trim().is_empty() && r.trim() != ":");
    let pii = pii_words(&runs);
    assert!(!pii.is_empty(), "customer block not found");
    let mut public: Vec<&str> = vec![&report_no, &product, &ulr, &issue_date];
    for r in &rows {
        public.extend([&r.label[..], &r.units, &r.method, &r.value, &r.rda, &r.pct]);
    }
    for p in &public {
        let p = p.to_lowercase();
        for w in &pii {
            assert!(!p.contains(w.as_str()), "PII would be committed");
        }
    }
    track!("cycle-tracker-report-end: extract");

    #[cfg(not(feature = "std"))]
    let (all, pii) = (Vec::new(), Vec::new());
    #[cfg(feature = "std")]
    let all = runs.iter().map(|s| s.to_string()).collect();

    Output { body_commitment, pdf_len: pdf_len as u32, report_no, product, ulr, issue_date, rows, runs: all, pii }
}

// ---- page tree ----

#[cfg(not(feature = "all-pages"))]
const MAX_PAGES: usize = 1;
#[cfg(feature = "all-pages")]
const MAX_PAGES: usize = usize::MAX;

// Leaf pages in document order (depth-first over /Kids), up to MAX_PAGES, each
// with the nearest inherited /Resources.
fn page_list<'a>(doc: &Doc<'a>) -> Vec<(Dict<'a>, Option<Dict<'a>>)> {
    page_list_max(doc, MAX_PAGES)
}

pub(crate) fn page_list_max<'a>(doc: &Doc<'a>, max: usize) -> Vec<(Dict<'a>, Option<Dict<'a>>)> {
    let cat = doc.resolve(&Obj::Ref(doc.root.0, doc.root.1)).dict();
    assert!(cat.name(b"Type") == Some(b"Catalog"), "root is not a /Catalog");
    let root = doc.resolve(cat.get(b"Pages").expect("/Pages")).dict();
    let mut out = Vec::new();
    walk(doc, root, None, 0, max, &mut out);
    assert!(!out.is_empty(), "no pages");
    out
}

fn walk<'a>(
    doc: &Doc<'a>,
    node: Dict<'a>,
    inherited: Option<Dict<'a>>,
    depth: u32,
    max: usize,
    out: &mut Vec<(Dict<'a>, Option<Dict<'a>>)>,
) {
    assert!(depth < 16, "page tree too deep");
    match node.name(b"Type") {
        Some(b"Page") => out.push((node, inherited)),
        Some(b"Pages") => {
            let inh = match node.get(b"Resources") {
                Some(r) => Some(doc.resolve(r).dict()),
                None => inherited,
            };
            let kids = match doc.resolve(node.get(b"Kids").expect("/Kids")) {
                Obj::Arr(a) => a,
                _ => panic!("/Kids is not an array"),
            };
            assert!(!kids.is_empty(), "empty /Kids");
            for k in &kids {
                if out.len() >= max {
                    return;
                }
                assert!(matches!(k, Obj::Ref(..)), "page tree kid must be a reference");
                let kid = doc.resolve(k).dict();
                walk(doc, kid, inh.clone(), depth + 1, max, out);
            }
        }
        _ => panic!("page tree node has no /Type /Page(s)"),
    }
}

pub(crate) fn page_fonts<'a>(doc: &Doc<'a>, res: &Dict<'a>) -> Vec<Font<'a>> {
    let mut fonts = Vec::new();
    let fd = match res.get(b"Font") {
        Some(f) => doc.resolve(f).dict(),
        None => return fonts,
    };
    for (name, r) in &fd.0 {
        let font = doc.resolve(r).dict();
        assert!(font.name(b"Type") == Some(b"Font"), "font resource is not a /Font");
        assert!(font.name(b"Subtype") == Some(b"Type0"), "only Type0 fonts supported");
        assert!(font.name(b"Encoding") == Some(b"Identity-H"), "only Identity-H supported");
        let cmap = font.get(b"ToUnicode").map(|tu| {
            track!("cycle-tracker-report-start: f_inflate");
            let s = doc.stream(tu, 4096);
            track!("cycle-tracker-report-end: f_inflate");
            track!("cycle-tracker-report-start: f_parse");
            let m = parse_cmap(&s);
            track!("cycle-tracker-report-end: f_parse");
            m
        });
        fonts.push(Font { name, cmap });
    }
    fonts
}

// Text inside a Form XObject would be invisible to the content-stream decoder,
// so only image XObjects are allowed on a decoded page.
pub(crate) fn check_xobjects<'a>(doc: &Doc<'a>, res: &Dict<'a>) {
    if let Some(x) = res.get(b"XObject") {
        for (_, r) in &doc.resolve(x).dict().0 {
            let (n, g) = match r {
                Obj::Ref(n, g) => (*n, *g),
                _ => panic!("XObject must be a reference"),
            };
            let l = doc.load(n, g);
            assert!(l.stream.is_some(), "XObject is not a stream");
            assert!(l.obj.dict().name(b"Subtype") == Some(b"Image"), "only image XObjects allowed");
        }
    }
}

// /Contents: one stream, or an array of streams concatenated with whitespace.
fn page_content<'a>(doc: &Doc<'a>, page: &Dict<'a>) -> Vec<u8> {
    let c = page.get(b"Contents").expect("page has no /Contents");
    match c {
        Obj::Ref(..) => match doc.resolve_any(c) {
            Some(Obj::Arr(a)) => concat_streams(doc, &a),
            None => doc.stream(c, 65536),
            _ => panic!("bad /Contents"),
        },
        Obj::Arr(a) => concat_streams(doc, a),
        _ => panic!("bad /Contents"),
    }
}

fn concat_streams<'a>(doc: &Doc<'a>, parts: &[Obj<'a>]) -> Vec<u8> {
    let mut out = Vec::new();
    for p in parts {
        out.extend_from_slice(&doc.stream(p, 65536));
        out.push(b'\n');
    }
    out
}

// ---- table extraction (anchored on the units run) ----

fn extract_rows(runs: &[&str], chosen_lc: &[String]) -> Vec<Row> {
    let mut rows = Vec::new();
    for (u, run) in runs.iter().enumerate() {
        if !is_units(run) {
            continue;
        }
        // Walk back over the parameter-name runs until the row-number integer.
        let mut k = u;
        while k > 0 {
            k -= 1;
            if is_pure_int(runs[k]) {
                k += 1;
                break;
            }
        }
        let label = runs[k..u].concat().trim().to_string();
        if label.is_empty() {
            continue;
        }
        let lc = label.to_lowercase();
        if !chosen_lc.iter().any(|c| *c == lc) {
            continue;
        }
        let get = |idx: usize| runs.get(idx).map(|s| s.to_string()).unwrap_or_default();
        rows.push(Row {
            label,
            units: run.to_string(),
            method: get(u + 1),
            value: get(u + 2),
            rda: get(u + 3),
            pct: get(u + 4),
        });
    }
    rows
}

fn is_units(s: &str) -> bool {
    let t = s.trim();
    t.ends_with("/100g") && t.len() <= 12 && !t.contains(' ')
}

fn is_pure_int(s: &str) -> bool {
    let t = s.trim();
    !t.is_empty() && t.bytes().all(|c| c.is_ascii_digit())
}

fn find_issue_date(runs: &[&str]) -> String {
    if let Some(pos) = runs.iter().position(|r| r.contains("Report Issue Date")) {
        for r in runs.iter().skip(pos + 1).take(4) {
            if is_date(r) {
                return r.trim().to_string();
            }
        }
    }
    String::new()
}

fn is_date(s: &str) -> bool {
    let t = s.trim();
    let b = t.as_bytes();
    b.len() == 11
        && b[0].is_ascii_digit()
        && b[1].is_ascii_digit()
        && b[2] == b'-'
        && b[6] == b'-'
        && b[7..].iter().all(|c| c.is_ascii_digit())
}

// First run after the one containing `label` (within 4 runs) that `ok` accepts.
fn find_after(runs: &[&str], label: &str, ok: impl Fn(&str) -> bool) -> String {
    if let Some(pos) = runs.iter().position(|r| r.contains(label)) {
        for r in runs.iter().skip(pos + 1).take(4) {
            if ok(r) {
                return r.trim().to_string();
            }
        }
    }
    String::new()
}

fn is_report_no(s: &str) -> bool {
    let t = s.trim();
    t.len() >= 8 && t.bytes().all(|c| c.is_ascii_alphanumeric() || c == b':' || c == b'_' || c == b'/' || c == b'-')
}

// Lower-cased words (>= 4 chars) of the customer name, contact person and
// address fields. They are decoded in the guest only to assert that none of
// them reaches the public values.
fn pii_words(runs: &[&str]) -> Vec<String> {
    let mut vals: Vec<&str> = Vec::new();
    for label in ["Client Name", "Contact Person"] {
        if let Some(p) = runs.iter().position(|r| r.trim() == label) {
            vals.extend(runs.get(p + 2));
        }
    }
    if let Some(p) = runs.iter().position(|r| r.trim() == "Address") {
        vals.extend(runs.iter().skip(p + 2).take_while(|r| r.trim() != "Sample Sub Group"));
    }
    let mut words = Vec::new();
    for v in vals {
        for w in v.split(|c: char| !c.is_alphanumeric()) {
            if w.len() >= 4 {
                words.push(w.to_lowercase());
            }
        }
    }
    words
}
