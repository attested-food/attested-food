//! Eurekha redaction + extraction against the mock-pdfs build outputs: the
//! spans and redacted hash must equal what mock-pdfs/scripts/redact.mjs wrote,
//! and the redacted bytes must equal its redacted PDF.
//!
//! `MOCK_PDFS=<dir>` (default `../../../mock-pdfs`); skipped when absent.

use std::path::PathBuf;

use equinox_core::{eurekha, sha::sha256};

fn mock_dir() -> Option<PathBuf> {
    let d = std::env::var_os("MOCK_PDFS")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../mock-pdfs"));
    d.join("out/raw").is_dir().then_some(d)
}

#[test]
fn matches_redact_mjs() {
    let Some(dir) = mock_dir() else { return };
    for id in ["choco-millet-muesli", "multigrain-atta", "peanut-butter-crunchy"] {
        let raw = std::fs::read(dir.join(format!("out/raw/{id}.pdf"))).unwrap();
        let redacted = std::fs::read(dir.join(format!("out/redacted/{id}.pdf"))).unwrap();
        let manifest: serde_json::Value =
            serde_json::from_slice(&std::fs::read(dir.join(format!("out/redacted/{id}.manifest.json"))).unwrap())
                .unwrap();

        let mut buf = raw.clone();
        buf.extend_from_slice(&[7u8; 16]);
        let out = eurekha::run(&buf);

        let spans: Vec<(u32, u32)> = manifest["spans"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| (s[0].as_u64().unwrap() as u32, s[1].as_u64().unwrap() as u32))
            .collect();
        assert_eq!(out.spans, spans, "{id}: spans");
        assert_eq!(hex::encode(out.redacted_sha256), manifest["redacted"]["sha256"].as_str().unwrap(), "{id}: hash");
        assert_eq!(out.redacted_sha256, sha256(&redacted), "{id}: redacted file");
        assert_eq!(out.pdf_len as usize, raw.len());

        let data: serde_json::Value =
            serde_json::from_slice(&std::fs::read(dir.join(format!("data/{id}.json"))).unwrap()).unwrap();
        let kv = |k: &str| out.kv.iter().find(|(key, _)| key == k).map(|(_, v)| v.as_str());
        assert_eq!(kv("Report Number"), data["report"]["number"].as_str(), "{id}");
        assert_eq!(kv("ULR"), data["report"]["ulr"].as_str(), "{id}");
        assert_eq!(kv("Sample Name"), data["sample"]["name"].as_str(), "{id}");
        assert_eq!(kv("Date of Receipt"), data["dates"]["receipt"].as_str(), "{id}");
        let want: usize = data["results"].as_array().unwrap().iter().map(|g| g["rows"].as_array().unwrap().len()).sum();
        assert_eq!(out.results.len(), want, "{id}: result rows");
        for (k, _) in &out.kv {
            assert!(!eurekha::PII_KEYS.contains(&k.as_str()), "{id}: PII key {k} emitted");
        }
        println!(
            "{id}: {} spans, {} kv, {} rows, public values {} B",
            out.spans.len(),
            out.kv.len(),
            out.results.len(),
            out.encode().len()
        );
        if id == "choco-millet-muesli" {
            for (k, v) in &out.kv {
                println!("  {k} = {v}");
            }
            for r in &out.results {
                println!(
                    "  [{}/{}] {} {} {} {} {} {}",
                    r.discipline, r.group, r.parameter, r.result, r.unit, r.method, r.rda, r.rda_pct
                );
            }
        }
    }
}
