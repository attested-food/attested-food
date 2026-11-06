//! The attested Eurekha statement against a real TLSNotary session of a
//! `mock-pdfs` report on the Eurekha S3 bucket (`zktls/runs/<id>/<mode>`, written
//! by `equinox-tls-prove`; private, gitignored).
//!
//! `EUREKHA_TLS_RUN=<dir>` (default `../zktls/runs/choco/proxy`); skipped when absent.

use std::path::PathBuf;

use equinox_core::{
    eurekha,
    sha::sha256,
    tlsn::{self, K256Recover as K256, OnchainRequest, OnchainTlsn, RequestSecret, TlsnError},
};

// Address of the dev notary key [1u8; 32] (public, insecure by design).
const NOTARY: &str = "1a642f0e3c3af545e7acbd38b07251b3990914f1";

fn unhex(s: &str) -> Vec<u8> {
    hex::decode(s.trim_start_matches("0x")).unwrap()
}

struct Run {
    t: OnchainTlsn,
    req: OnchainRequest,
    secret: RequestSecret,
    buf: Vec<u8>,
    key: String,
}

fn load() -> Option<Run> {
    let dir = std::env::var_os("EUREKHA_TLS_RUN")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../zktls/runs/choco/proxy"));
    if !dir.join("onchain.json").exists() {
        return None;
    }
    let read = |f: &str| std::fs::read(dir.join(f)).unwrap();
    let d: serde_json::Value = serde_json::from_slice(&read("onchain.json")).unwrap();
    let h = |k: &str| unhex(d[k].as_str().unwrap());
    let t = OnchainTlsn {
        header: h("header"),
        signature: h("signature"),
        leaves: d["leaves"]
            .as_array()
            .unwrap()
            .iter()
            .map(|l| unhex(l.as_str().unwrap()).try_into().unwrap())
            .collect(),
        ext_index: d["extIndex"].as_u64().unwrap() as u32,
        ext_preimage: h("extPreimage"),
        body_index: d["bodyIndex"].as_u64().unwrap() as u32,
        body_preimage: h("bodyPreimage"),
    };
    let req = OnchainRequest {
        conn_index: d["connIndex"].as_u64().unwrap() as u32,
        conn_preimage: h("connPreimage"),
        sent_index: d["sentIndices"].as_array().unwrap().iter().map(|i| i.as_u64().unwrap() as u32).collect(),
        sent_preimage: d["sentPreimages"].as_array().unwrap().iter().map(|p| unhex(p.as_str().unwrap())).collect(),
    };
    let secret: RequestSecret = serde_json::from_slice(&read("request.json")).unwrap();
    let mut buf = read("body.pdf");
    buf.extend_from_slice(&unhex(std::str::from_utf8(&read("blinder.hex")).unwrap().trim()));
    let url = std::fs::read_to_string(dir.join("../url.txt")).unwrap();
    let key = url.trim().strip_prefix("https://eurekhalabs.s3.amazonaws.com/").unwrap().to_string();
    Some(Run { t, req, secret, buf, key })
}

fn notary() -> [u8; 20] {
    unhex(NOTARY).try_into().unwrap()
}

#[test]
fn attested_eurekha() {
    let Some(r) = load() else { return };
    let out = eurekha::run_attested(&r.buf, &r.t, &r.req, &r.secret, &notary(), &K256).expect("attested");
    assert_eq!(out.server_name, tlsn::EUREKHA_SERVER_NAME);
    assert_eq!(out.key_sha256, sha256(r.key.as_bytes()));
    assert!(out.session_time > 1_700_000_000);
    assert_eq!(out.report, eurekha::run(&r.buf));
    assert_eq!(out.signer, eurekha::Signer::Notary(notary()));

    // Signature left to the verifier: same values, the header committed instead.
    let u = eurekha::run_attested_unsigned(&r.buf, &r.t, &r.req, &r.secret).expect("unsigned");
    assert_eq!(u.signer, eurekha::Signer::Header(r.t.header.clone()));
    assert_eq!((u.key_sha256, u.session_time, &u.report), (out.key_sha256, out.session_time, &out.report));
    // ... and what that verifier checks: the header signature recovers the notary.
    assert_eq!(tlsn::NotarySignature::recover(&K256, &r.t.header, &r.t.signature), Some(notary()));
    // A leaf that is not under the header's root is still rejected in the guest.
    let mut t = r.t.clone();
    t.leaves[0][0] ^= 1;
    assert_eq!(eurekha::run_attested_unsigned(&r.buf, &t, &r.req, &r.secret).err(), Some(TlsnError::BadMerkleRoot));
}

#[test]
fn tampering_is_rejected() {
    let Some(r) = load() else { return };
    let n = notary();
    let run = |buf: &[u8], t: &OnchainTlsn, req: &OnchainRequest, s: &RequestSecret, n: &[u8; 20]| {
        eurekha::run_attested(buf, t, req, s, n, &K256).err()
    };

    let mut wrong = n;
    wrong[0] ^= 1;
    assert_eq!(run(&r.buf, &r.t, &r.req, &r.secret, &wrong), Some(TlsnError::BadNotarySignature));

    // A different PDF (one byte of a glyph code changed) or blinder.
    let mut buf = r.buf.clone();
    let i = buf.windows(2).position(|w| w == b"<0").unwrap() + 1;
    buf[i] = b'1';
    assert_eq!(run(&buf, &r.t, &r.req, &r.secret, &n), Some(TlsnError::BodyMismatch));
    let mut buf = r.buf.clone();
    *buf.last_mut().unwrap() ^= 1;
    assert_eq!(run(&buf, &r.t, &r.req, &r.secret, &n), Some(TlsnError::BodyMismatch));

    // Another object key with the real path blinder, or the right key with a wrong blinder.
    let mut s = r.secret.clone();
    let p = s.request.iter().position(|&c| c == b'.').unwrap() - 1;
    s.request[p] ^= 1;
    assert_eq!(run(&r.buf, &r.t, &r.req, &s, &n), Some(TlsnError::BadRequest));
    let mut s = r.secret.clone();
    s.blinders[1][0] ^= 1;
    assert_eq!(run(&r.buf, &r.t, &r.req, &s, &n), Some(TlsnError::BadRequest));

    // Leaves out of order, a leaf from the wrong slot, a forged ConnectionInfo.
    let mut req = r.req.clone();
    req.sent_index.swap(0, 1);
    req.sent_preimage.swap(0, 1);
    assert_eq!(run(&r.buf, &r.t, &req, &r.secret, &n), Some(TlsnError::BadRequest));
    let mut req = r.req.clone();
    req.sent_index[1] = req.sent_index[2];
    assert_eq!(run(&r.buf, &r.t, &req, &r.secret, &n), Some(TlsnError::BadRequest));
    let mut req = r.req.clone();
    req.conn_preimage[9] ^= 1;
    assert_eq!(run(&r.buf, &r.t, &req, &r.secret, &n), Some(TlsnError::BadConnectionInfo));

    // The server name extension of another host.
    let mut t = r.t.clone();
    t.ext_preimage = tlsn::server_name_ext_preimage(tlsn::SERVER_NAME);
    assert_eq!(run(&r.buf, &t, &r.req, &r.secret, &n), Some(TlsnError::BadServerName));
}
