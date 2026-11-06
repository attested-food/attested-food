//! The report's own S3 URL, read from the QR code the lab prints on it, so a
//! user only uploads the PDF: the server then fetches that URL under
//! TLSNotary ([`crate::zktls`]) and proves the attested copy.
//!
//! The Eurekha template draws the QR as one filled vector path of module
//! squares (`m`/`l`/`h`, then `f`). The largest such fill on any page is
//! rasterised onto its module grid with an even-odd test at every module
//! centre and decoded with `rqrr`. Only URLs under [`ALLOWED_PREFIXES`] are
//! accepted. The URL is private (its key is the link to the unredacted
//! original): never log or return it.

/// Report objects the server will fetch.
pub const ALLOWED_PREFIXES: [&str; 1] = ["https://eurekhalabs.s3.amazonaws.com/reports/"];

/// A filled path: closed polygons in user space.
type Fill = Vec<Vec<(f64, f64)>>;

/// Every non-trivial filled path in a content stream, in order.
fn fills(content: &[u8]) -> Vec<Fill> {
    let mut out = Vec::new();
    let mut nums: Vec<f64> = Vec::new();
    let mut path: Fill = Vec::new();
    for tok in content.split(|c| c.is_ascii_whitespace()).filter(|t| !t.is_empty()) {
        if let Some(n) = std::str::from_utf8(tok).ok().and_then(|t| t.parse::<f64>().ok()) {
            nums.push(n);
            continue;
        }
        match tok {
            b"m" if nums.len() >= 2 => path.push(vec![(nums[nums.len() - 2], nums[nums.len() - 1])]),
            b"l" if nums.len() >= 2 => {
                if let Some(p) = path.last_mut() {
                    p.push((nums[nums.len() - 2], nums[nums.len() - 1]));
                }
            }
            b"re" if nums.len() >= 4 => {
                let [x, y, w, h] =
                    [nums[nums.len() - 4], nums[nums.len() - 3], nums[nums.len() - 2], nums[nums.len() - 1]];
                path.push(vec![(x, y), (x + w, y), (x + w, y + h), (x, y + h)]);
            }
            b"f" | b"F" | b"f*" => {
                if path.len() > 1 {
                    out.push(std::mem::take(&mut path));
                }
                path.clear();
            }
            b"n" | b"S" | b"s" | b"B" | b"B*" | b"b" | b"b*" | b"BT" => path.clear(),
            _ => {}
        }
        nums.clear();
    }
    out
}

/// Even-odd point-in-path test.
fn inside(fill: &Fill, (px, py): (f64, f64)) -> bool {
    let mut odd = false;
    for poly in fill {
        for i in 0..poly.len() {
            let (a, b) = (poly[i], poly[(i + 1) % poly.len()]);
            if (a.1 > py) != (b.1 > py) && px < a.0 + (py - a.1) * (b.0 - a.0) / (b.1 - a.1) {
                odd = !odd;
            }
        }
    }
    odd
}

/// Decode a vector QR code; `None` if `fill` is not one.
fn decode(fill: &Fill) -> Option<String> {
    let pts = fill.iter().flatten();
    let (mut x0, mut y0, mut x1, mut y1) = (f64::MAX, f64::MAX, f64::MIN, f64::MIN);
    for &(x, y) in pts {
        (x0, y0, x1, y1) = (x0.min(x), y0.min(y), x1.max(x), y1.max(y));
    }
    // Module size: the shortest edge (every edge is a whole number of modules).
    let module = fill
        .iter()
        .flat_map(|p| (0..p.len()).map(move |i| (p[i], p[(i + 1) % p.len()])))
        .map(|(a, b)| (a.0 - b.0).abs().max((a.1 - b.1).abs()))
        .filter(|d| *d > 1e-6)
        .fold(f64::MAX, f64::min);
    let n = ((x1 - x0) / module).round() as usize;
    if !(21..=177).contains(&n) || ((y1 - y0) / module).round() as usize != n {
        return None;
    }
    let dark: Vec<bool> = (0..n * n)
        .map(|i| inside(fill, (x0 + ((i % n) as f64 + 0.5) * module, y0 + ((i / n) as f64 + 0.5) * module)))
        .collect();
    // 4-module quiet zone, 4 px per module; PDF y may point up or down.
    let (q, px) = (4, 4);
    let side = (n + 2 * q) * px;
    for flip in [true, false] {
        let mut img = rqrr::PreparedImage::prepare_from_greyscale(side, side, |x, y| {
            let (mx, my) = ((x / px) as isize - q as isize, (y / px) as isize - q as isize);
            if mx < 0 || my < 0 || mx >= n as isize || my >= n as isize {
                return 255;
            }
            let row = if flip { n - 1 - my as usize } else { my as usize };
            if dark[row * n + mx as usize] {
                0
            } else {
                255
            }
        });
        for grid in img.detect_grids() {
            if let Ok((_, text)) = grid.decode() {
                return Some(text);
            }
        }
    }
    None
}

/// The allowlisted report URL in the PDF's QR code.
pub fn report_url(pdf: &[u8]) -> Result<String, String> {
    let pages = std::panic::catch_unwind(|| equinox_core::extract::page_contents(pdf))
        .map_err(|_| "could not read the PDF pages".to_string())?;
    let mut fills: Vec<Fill> = pages.iter().flat_map(|c| fills(c)).filter(|f| f.len() >= 20).collect();
    fills.sort_by_key(|f| std::cmp::Reverse(f.len()));
    let url = fills.iter().find_map(decode).ok_or("no QR code with the report link found in the PDF")?;
    let ok = ALLOWED_PREFIXES.iter().any(|p| {
        url.strip_prefix(p)
            .is_some_and(|key| key.ends_with(".pdf") && !key.contains("..") && !key.contains(['?', '#', ' ']))
    });
    if !ok {
        return Err("the PDF's QR code does not link to a report on an allowlisted lab bucket".into());
    }
    Ok(url)
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    /// The `mock-pdfs` reports carry their S3 URL in the QR (`template/eurekha-report.typ`).
    #[test]
    fn mock_reports() {
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../mock-pdfs");
        if !dir.join("out/raw").is_dir() {
            return;
        }
        for id in ["choco-millet-muesli", "multigrain-atta", "peanut-butter-crunchy"] {
            let pdf = std::fs::read(dir.join(format!("out/raw/{id}.pdf"))).unwrap();
            let d: serde_json::Value =
                serde_json::from_slice(&std::fs::read(dir.join(format!("data/{id}.json"))).unwrap()).unwrap();
            let want = format!(
                "https://{}.s3.amazonaws.com/{}",
                d["s3"]["bucket"].as_str().unwrap(),
                d["s3"]["key"].as_str().unwrap()
            );
            assert_eq!(super::report_url(&pdf).unwrap(), want, "{id}");
        }
        assert!(super::report_url(b"%PDF-1.4 nothing").is_err());
    }
}
