//! TLSNotary attestation checks that need only SHA-256, so a zkVM guest can
//! verify the attestation next to the PDF and one proof covers both. Mirrors
//! `EquinoxReportRegistry.checkTlsn` in Solidity:
//!
//! - the notary signature over the BCS attestation header (secp256k1, keccak256
//!   prehash, 65 bytes): delegated to a [`NotarySignature`] the guest supplies,
//!   so each zkVM can use its own secp256k1 / keccak precompiles;
//! - the attestation body Merkle root (rs_merkle over SHA-256) rebuilt from all
//!   leaves and compared with the root at the end of the signed header;
//! - the `equinox.server_name` extension leaf opened to one of [`SERVER_NAMES`];
//! - the body commitment leaf opened to `PlaintextHash { Received, one range,
//!   SHA-256 }`, giving the commitment and the body range.
//!
//! [`open_request`] goes further for an [`OnchainRequest`]: it opens the
//! `ConnectionInfo` leaf and the three request commitments against the private
//! request bytes, so the guest learns the request path (and outputs only its
//! hash) and checks the `Host` header names the attested server.
//!
//! The X.509 chain is NOT checked here: like the contract, this trusts the
//! notary's signed server-name extension. The Rust verifier checks the chain.
//!
//! [`run_attested`] is the one-proof entry point: attestation checks, then the
//! PDF extraction, then [`bind`] ties the recomputed `SHA256(pdf || blinder)`
//! and the PDF length to the attested body commitment and range. The guest must
//! pin the notary: either a constant compiled into the program (so the program
//! id binds it) or a value it commits next to the public values.

use alloc::{string::String, vec::Vec};

use crate::extract::Output;
use crate::sha::sha256;

/// `blake3("Extension")[..16]`, the tlsn-attestation leaf domain of extensions.
pub const DOMAIN_EXTENSION: [u8; 16] = hex16("67ed567f312ca482b9f365cc271baa42");
/// `blake3("tlsn_core::transcript::TranscriptCommitment")[..16]`.
pub const DOMAIN_TRANSCRIPT_COMMITMENT: [u8; 16] = hex16("bd0ab9ac6ea93ebda2500e8769e63a9e");
/// Id of the notary-signed extension that carries the verified server name.
pub const SERVER_NAME_EXT_ID: &[u8] = b"equinox.server_name";
/// `blake3("tlsn_core::connection::ConnectionInfo")[..16]`.
pub const DOMAIN_CONNECTION_INFO: [u8; 16] = hex16("6e317487904af460f6bba793610c9961");
/// The Equinox report bucket.
pub const SERVER_NAME: &str = "equinox-labs-latest.s3.amazonaws.com";
/// The Eurekha Labs report bucket (`mock-pdfs`).
pub const EUREKHA_SERVER_NAME: &str = "eurekhalabs.s3.amazonaws.com";
/// Every server the workflow accepts.
pub const SERVER_NAMES: [&str; 2] = [SERVER_NAME, EUREKHA_SERVER_NAME];

pub fn is_allowed_host(host: &str) -> bool {
    SERVER_NAMES.contains(&host)
}

/// The attestation pieces the on-chain and in-guest checks consume. Built from
/// a presentation by `zktls::onchain::export`.
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct OnchainTlsn {
    /// BCS attestation header (the notary signs keccak256 of these bytes).
    pub header: Vec<u8>,
    /// 65-byte recoverable secp256k1 signature (r || s || v).
    pub signature: Vec<u8>,
    /// Every Merkle leaf of the attestation body, sorted by field id.
    pub leaves: Vec<[u8; 32]>,
    pub ext_index: u32,
    /// `bcs(Extension { id: "equinox.server_name", value: server })`.
    pub ext_preimage: Vec<u8>,
    pub body_index: u32,
    /// `bcs(TranscriptCommitment::Hash(..))` of the body commitment.
    pub body_preimage: Vec<u8>,
}

/// Recovers the notary address (last 20 bytes of keccak256(pubkey)) from the
/// header signature. Implemented per zkVM with its own precompiles.
pub trait NotarySignature {
    fn recover(&self, header: &[u8], signature: &[u8]) -> Option<[u8; 20]>;
}

/// The leaves that pin the request: `ConnectionInfo` (transcript lengths,
/// session time) and the three sent commitments `GET `, path, rest of the
/// request, in transcript order. Public, built by `zktls::onchain::export`.
#[derive(Clone, Debug, PartialEq, Eq, Default)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct OnchainRequest {
    pub conn_index: u32,
    /// `bcs(ConnectionInfo)`: `time u64 LE | version | sent u32 LE | received u32 LE`.
    pub conn_preimage: Vec<u8>,
    pub sent_index: Vec<u32>,
    /// `bcs(TranscriptCommitment::Hash(PlaintextHash { Sent, .. }))` per leaf.
    pub sent_preimage: Vec<Vec<u8>>,
}

/// The private opening of the request commitments: the whole sent transcript
/// (it holds the object key) and one blinder per [`OnchainRequest`] leaf.
#[derive(Clone, Debug, PartialEq, Eq, Default)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct RequestSecret {
    pub request: Vec<u8>,
    pub blinders: Vec<[u8; 16]>,
}

/// What an opened request establishes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AttestedRequest {
    /// TLS session time (unix seconds) the notary attested.
    pub session_time: u64,
    /// `sha256` of the object key (the request path without its leading `/`).
    pub key_sha256: [u8; 32],
}

/// What a verified attestation says about the body.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AttestedBody {
    /// The notary-signed server name, one of [`SERVER_NAMES`].
    pub server_name: &'static str,
    pub body_commitment: [u8; 32],
    /// Byte range of the body in the received transcript.
    pub body_start: u64,
    pub body_end: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TlsnError {
    BadHeader,
    BadNotarySignature,
    BadMerkleRoot,
    BadServerName,
    BadBodyCommitment,
    BadConnectionInfo,
    /// A request leaf, its opening, or the request shape (`GET /path HTTP/1.1`,
    /// one `Host` header naming the attested server) does not check out.
    BadRequest,
    /// The PDF's recomputed commitment or length differs from the attested body.
    BodyMismatch,
}

/// Full check of an exported attestation against a pinned notary address.
pub fn check(t: &OnchainTlsn, notary: &[u8; 20], sig: &impl NotarySignature) -> Result<AttestedBody, TlsnError> {
    let root = header_root(&t.header).ok_or(TlsnError::BadHeader)?;
    if sig.recover(&t.header, &t.signature) != Some(*notary) {
        return Err(TlsnError::BadNotarySignature);
    }
    if t.leaves.is_empty() || merkle_root(&t.leaves) != root {
        return Err(TlsnError::BadMerkleRoot);
    }
    let leaf = |i: u32| t.leaves.get(i as usize).copied();
    let server_name = SERVER_NAMES
        .into_iter()
        .find(|s| t.ext_preimage == server_name_ext_preimage(s))
        .ok_or(TlsnError::BadServerName)?;
    if leaf(t.ext_index) != Some(leaf_hash(&DOMAIN_EXTENSION, &t.ext_preimage)) {
        return Err(TlsnError::BadServerName);
    }
    let (body_start, body_end, body_commitment) =
        parse_hash_preimage(&t.body_preimage, RECEIVED).ok_or(TlsnError::BadBodyCommitment)?;
    if leaf(t.body_index) != Some(leaf_hash(&DOMAIN_TRANSCRIPT_COMMITMENT, &t.body_preimage)) {
        return Err(TlsnError::BadBodyCommitment);
    }
    Ok(AttestedBody { server_name, body_commitment, body_start, body_end })
}

/// Open the request against a [`check`]ed attestation `t`: the
/// `ConnectionInfo` leaf gives both transcript lengths; the three sent leaves
/// must cover `[0, 4)`, `[4, p)`, `[p, sent_len)` and open (SHA-256 with their
/// blinders) to `GET `, a path, and ` HTTP/1.1\r\n` + headers + `\r\n` with
/// exactly one `Host` header equal to `body.server_name`; the body must end the
/// received transcript. The path must be `/` + a non-empty key with no space,
/// `?` or `#`; only its hash leaves the guest.
pub fn open_request(
    t: &OnchainTlsn,
    body: &AttestedBody,
    r: &OnchainRequest,
    s: &RequestSecret,
) -> Result<AttestedRequest, TlsnError> {
    let leaf = |i: u32| t.leaves.get(i as usize).copied();
    let c = &r.conn_preimage;
    if c.len() != 17 || leaf(r.conn_index) != Some(leaf_hash(&DOMAIN_CONNECTION_INFO, c)) {
        return Err(TlsnError::BadConnectionInfo);
    }
    let session_time = u64::from_le_bytes(c[..8].try_into().unwrap());
    let sent_len = u32::from_le_bytes(c[9..13].try_into().unwrap()) as u64;
    let recv_len = u32::from_le_bytes(c[13..17].try_into().unwrap()) as u64;
    if body.body_end != recv_len {
        return Err(TlsnError::BodyMismatch);
    }

    let req = &s.request;
    if req.len() as u64 != sent_len || r.sent_index.len() != 3 || r.sent_preimage.len() != 3 || s.blinders.len() != 3 {
        return Err(TlsnError::BadRequest);
    }
    let mut at = 0u64;
    let mut parts: [&[u8]; 3] = [&[]; 3];
    for i in 0..3 {
        let pre = &r.sent_preimage[i];
        let (start, end, hash) = parse_hash_preimage(pre, SENT).ok_or(TlsnError::BadRequest)?;
        if start != at || leaf(r.sent_index[i]) != Some(leaf_hash(&DOMAIN_TRANSCRIPT_COMMITMENT, pre)) {
            return Err(TlsnError::BadRequest);
        }
        let part = &req[start as usize..end as usize];
        let mut b = Vec::with_capacity(part.len() + 16);
        b.extend_from_slice(part);
        b.extend_from_slice(&s.blinders[i]);
        if sha256(&b) != hash {
            return Err(TlsnError::BadRequest);
        }
        parts[i] = part;
        at = end;
    }
    let [get, path, rest] = parts;
    if at != sent_len || get != b"GET " || !request_tail_ok(rest, body.server_name) {
        return Err(TlsnError::BadRequest);
    }
    let key = match path {
        [b'/', key @ ..] if !key.is_empty() && !key.iter().any(|c| matches!(c, b' ' | b'?' | b'#')) => key,
        _ => return Err(TlsnError::BadRequest),
    };
    Ok(AttestedRequest { session_time, key_sha256: sha256(key) })
}

/// ` HTTP/1.1\r\n`, header lines, `\r\n`; exactly one `Host` header (name case
/// insensitive) whose value is `host`.
fn request_tail_ok(rest: &[u8], host: &str) -> bool {
    let Some(headers) = rest.strip_prefix(b" HTTP/1.1\r\n").and_then(|h| h.strip_suffix(b"\r\n")) else {
        return false;
    };
    let mut hosts = 0;
    let mut line_start = 0;
    while line_start < headers.len() {
        let Some(n) = headers[line_start..].windows(2).position(|w| w == b"\r\n") else { return false };
        let line = &headers[line_start..line_start + n];
        if line.len() >= 5 && line[..5].eq_ignore_ascii_case(b"host:") {
            hosts += 1;
            if line[5..].trim_ascii() != host.as_bytes() {
                return false;
            }
        }
        line_start += n + 2;
    }
    hosts == 1
}

/// The recomputed `SHA256(pdf || blinder)` and the PDF length must be exactly
/// the attested commitment and body range.
pub fn bind(body: &AttestedBody, out: &Output) -> Result<(), TlsnError> {
    bind_body(body, &out.body_commitment, out.pdf_len as u64)
}

/// [`bind`] for any report format.
pub fn bind_body(body: &AttestedBody, commitment: &[u8; 32], pdf_len: u64) -> Result<(), TlsnError> {
    if *commitment != body.body_commitment || pdf_len != body.body_end - body.body_start {
        return Err(TlsnError::BodyMismatch);
    }
    Ok(())
}

/// TLS + PDF in one computation: [`check`] the attestation against the pinned
/// notary, run the extraction over `buf = pdf || blinder`, then [`bind`].
#[inline]
pub fn run_attested(
    buf: &[u8],
    chosen: &[String],
    t: &OnchainTlsn,
    notary: &[u8; 20],
    sig: &impl NotarySignature,
) -> Result<Output, TlsnError> {
    let body = check(t, notary, sig)?;
    let out = crate::extract::run(buf, chosen);
    bind(&body, &out)?;
    Ok(out)
}

/// [`NotarySignature`] with the `k256` crate (`k256` feature), `no_std`. A zkVM
/// guest patches `k256` / `sha3` to its precompile forks.
#[cfg(feature = "k256")]
pub struct K256Recover;

#[cfg(feature = "k256")]
impl NotarySignature for K256Recover {
    fn recover(&self, header: &[u8], sig: &[u8]) -> Option<[u8; 20]> {
        use k256::ecdsa::{RecoveryId, Signature, VerifyingKey};
        use sha3::{Digest, Keccak256};
        if sig.len() != 65 {
            return None;
        }
        let s = Signature::from_slice(&sig[..64]).ok()?;
        let v = sig[64];
        let id = RecoveryId::from_byte(if v >= 27 { v - 27 } else { v })?;
        let vk = VerifyingKey::recover_from_prehash(&Keccak256::digest(header), &s, id).ok()?;
        let pt = vk.to_encoded_point(false);
        Keccak256::digest(&pt.as_bytes()[1..])[12..].try_into().ok()
    }
}

/// The Merkle root at the end of the BCS header: `.. | 0x01 (SHA-256) | 0x20 | root`.
pub fn header_root(header: &[u8]) -> Option<[u8; 32]> {
    let n = header.len();
    if n < 34 || header[n - 34] != 0x01 || header[n - 33] != 0x20 {
        return None;
    }
    header[n - 32..].try_into().ok()
}

/// `SHA256(domain || bcs(field))`.
pub fn leaf_hash(domain: &[u8; 16], preimage: &[u8]) -> [u8; 32] {
    let mut b = Vec::with_capacity(16 + preimage.len());
    b.extend_from_slice(domain);
    b.extend_from_slice(preimage);
    sha256(&b)
}

/// rs_merkle layout: parent = SHA256(left || right), a lone last node is promoted.
pub fn merkle_root(leaves: &[[u8; 32]]) -> [u8; 32] {
    let mut level: Vec<[u8; 32]> = leaves.to_vec();
    while level.len() > 1 {
        let mut next = Vec::with_capacity(level.len().div_ceil(2));
        for pair in level.chunks(2) {
            next.push(match pair {
                [l, r] => {
                    let mut b = [0u8; 64];
                    b[..32].copy_from_slice(l);
                    b[32..].copy_from_slice(r);
                    sha256(&b)
                }
                [l] => *l,
                _ => unreachable!(),
            });
        }
        level = next;
    }
    level[0]
}

/// `bcs(Extension { id: "equinox.server_name", value: server })`.
pub fn server_name_ext_preimage(server: &str) -> Vec<u8> {
    let mut b = Vec::new();
    for part in [SERVER_NAME_EXT_ID, server.as_bytes()] {
        uleb128(&mut b, part.len() as u64);
        b.extend_from_slice(part);
    }
    b
}

const SENT: u8 = 0x00;
const RECEIVED: u8 = 0x01;

/// `bcs(TranscriptCommitment::Hash(PlaintextHash { direction, [start..end), SHA-256 }))`:
/// `0x00 | direction (0 Sent, 1 Received) | 0x01 (one range) | start u64 LE |
/// end u64 LE | 0x01 | 0x20 | hash`. Returns `(start, end, hash)`.
pub fn parse_hash_preimage(b: &[u8], direction: u8) -> Option<(u64, u64, [u8; 32])> {
    if b.len() != 53 || b[0] != 0x00 || b[1] != direction || b[2] != 0x01 || b[19] != 0x01 || b[20] != 0x20 {
        return None;
    }
    let start = u64::from_le_bytes(b[3..11].try_into().ok()?);
    let end = u64::from_le_bytes(b[11..19].try_into().ok()?);
    if end <= start {
        return None;
    }
    Some((start, end, b[21..53].try_into().ok()?))
}

fn uleb128(out: &mut Vec<u8>, mut v: u64) {
    loop {
        let byte = (v & 0x7f) as u8;
        v >>= 7;
        if v == 0 {
            out.push(byte);
            return;
        }
        out.push(byte | 0x80);
    }
}

const fn hex16(s: &str) -> [u8; 16] {
    let b = s.as_bytes();
    let mut out = [0u8; 16];
    let mut i = 0;
    while i < 16 {
        out[i] = (nib(b[2 * i]) << 4) | nib(b[2 * i + 1]);
        i += 1;
    }
    out
}

const fn nib(c: u8) -> u8 {
    match c {
        b'0'..=b'9' => c - b'0',
        b'a'..=b'f' => c - b'a' + 10,
        _ => panic!("bad hex"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn request_tail() {
        let h = EUREKHA_SERVER_NAME;
        let ok = alloc::format!(" HTTP/1.1\r\nhost: {h}\r\naccept: */*\r\n\r\n");
        assert!(request_tail_ok(ok.as_bytes(), h));
        assert!(request_tail_ok(alloc::format!(" HTTP/1.1\r\nHost:  {h} \r\n\r\n").as_bytes(), h));
        for bad in [
            alloc::format!(" HTTP/1.1\r\nhost: {SERVER_NAME}\r\n\r\n"),
            alloc::format!(" HTTP/1.1\r\nhost: {h}\r\nhost: {h}\r\n\r\n"),
            alloc::format!(" HTTP/1.1\r\nhost: {h}\r\n"),
            alloc::format!(" HTTP/1.0\r\nhost: {h}\r\n\r\n"),
            " HTTP/1.1\r\naccept: */*\r\n\r\n".into(),
        ] {
            assert!(!request_tail_ok(bad.as_bytes(), h), "{bad:?}");
        }
    }
}
