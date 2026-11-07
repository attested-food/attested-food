//! TLSNotary fetch of a report URL by the server, for uploads that come
//! without their own zktls session: runs `equinox-tls-prove` (`../zktls`, its
//! own workspace, so tlsn stays out of this server's lock) in proxy mode with
//! its in-process notary, and reads back the run dir.
//!
//! Trust: here the server is both the TLS prover and the notary (key
//! `EQUINOX_NOTARY_KEY`, default the public dev key), so the attestation says
//! "this server fetched these bytes from the bucket"; an independent notary
//! is what makes it evidence against the server operator.
//!
//! One session at a time ([`slot`]): a proxy-mode session is 15-30 s, an MPC
//! one up to 22 GB.

use std::path::PathBuf;

use tokio::sync::{Semaphore, SemaphorePermit};

use crate::jobs::Progress;

/// Every server-side session (`/prove` and `/tls/session`) holds this.
static SLOT: Semaphore = Semaphore::const_new(1);

/// Waits for the session slot; the job's stage says so while it waits.
pub async fn slot(progress: &Progress) -> SemaphorePermit<'static> {
    if let Ok(p) = SLOT.try_acquire() {
        return p;
    }
    progress.stage("waiting for zktls slot");
    SLOT.acquire().await.expect("zktls slot never closes")
}

/// What one session yields: the attested body and the files `/prove` takes.
pub struct Session {
    pub body: Vec<u8>,
    pub blinder: [u8; 16],
    /// `onchain.json` (public leaves).
    pub onchain: String,
    /// `request.json` (private: the request, whose path is the object key).
    pub request: String,
}

fn bin() -> String {
    std::env::var("EUREKHA_TLS_BIN")
        .unwrap_or_else(|_| concat!(env!("CARGO_MANIFEST_DIR"), "/../zktls/target/release/equinox-tls-prove").into())
}

/// Fetch `url` under TLSNotary. Blocking (a proxy-mode session is ~15-30 s).
pub fn fetch(url: &str) -> Result<Session, String> {
    let mut id = [0u8; 8];
    getrandom::getrandom(&mut id).map_err(|e| e.to_string())?;
    let dir = std::env::temp_dir().join(format!("eurekha-tls-{}", hex::encode(id)));
    let res = fetch_in(&dir, url);
    let _ = std::fs::remove_dir_all(&dir);
    res.map_err(|e| scrub(e, url))
}

/// `e` without `url` or its object key: the URL is private, errors get logged.
pub fn scrub(e: String, url: &str) -> String {
    let e = if url.is_empty() { e } else { e.replace(url, "<report url>") };
    match crate::report_url::ALLOWED_PREFIXES.iter().find_map(|p| url.strip_prefix(p)) {
        Some(key) if !key.is_empty() => e.replace(key, "<key>"),
        _ => e,
    }
}

fn fetch_in(dir: &PathBuf, url: &str) -> Result<Session, String> {
    std::fs::create_dir(dir).map_err(|e| format!("tls dir: {e}"))?;
    // The URL goes through a file so the private key never shows up in argv.
    std::fs::write(dir.join("url.txt"), url).map_err(|e| format!("url file: {e}"))?;
    let out = dir.join("run");
    let bin = bin();
    let res = std::process::Command::new(&bin)
        .arg("--url-file")
        .arg(dir.join("url.txt"))
        .arg("--out-dir")
        .arg(&out)
        .args(["--mode", "proxy"])
        .output()
        .map_err(|e| format!("run {bin}: {e}"))?;
    if !res.status.success() {
        let err = String::from_utf8_lossy(&res.stderr);
        let tail: Vec<&str> = err.lines().rev().take(3).collect();
        return Err(format!("zktls session failed: {}", tail.join(" | ")));
    }
    let read = |f: &str| std::fs::read(out.join(f)).map_err(|e| format!("zktls {f}: {e}"));
    let blinder = hex::decode(String::from_utf8_lossy(&read("blinder.hex")?).trim())
        .ok()
        .and_then(|b| b.try_into().ok())
        .ok_or("zktls blinder.hex is not 16 bytes")?;
    Ok(Session {
        body: read("body.pdf")?,
        blinder,
        onchain: String::from_utf8(read("onchain.json")?).map_err(|e| e.to_string())?,
        request: String::from_utf8(read("request.json")?).map_err(|e| e.to_string())?,
    })
}
