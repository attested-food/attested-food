//! The TLSNotary side of the workflow (tlsn `alpha.16-pre`, rev 24b10ba),
//! server-side prover only. Copied from the Equinox backend's `zktls`; the
//! browser protocol, WebSocket adapters and presentation verifier are not.
//!
//! Session shape (same in every mode): `GET` of an S3 report object over TLS
//! 1.2 from one of [`SERVER_NAMES`], every commitment a SHA-256 plaintext hash
//! `SHA256(bytes || blinder16)`, the request path committed alone and never
//! revealed, the status line, Content-Type, Content-Length and header
//! terminator revealed, the body one private commitment ([`policy`]). The
//! notary signs with secp256k1 in Ethereum form (keccak256 prehash, 65-byte
//! recoverable signature) over a SHA-256 Merkle tree and adds two extensions:
//! the verified server name (`equinox.server_name`) and the session kind
//! (`equinox.session`, e.g. `proxy/server`).
//!
//! - [`notary`]: the verifier/notary half of a session over any byte stream,
//!   MPC or proxy mode ([`notary::notarize`]).
//! - [`prover`]: the server-side prover, MPC and proxy mode.
//! - [`proxy`]: URL policy and the TCP side of the WebSocket -> TCP bridge.
//! - [`onchain`]: turn a presentation into the attestation pieces the
//!   contract and the in-guest verifier check, plus the request opening.

pub mod notary;
pub mod onchain;
pub mod policy;
pub mod prover;
pub mod proxy;

pub use equinox_core::tlsn::{
    is_allowed_host, K256Recover, OnchainRequest, OnchainTlsn, RequestSecret, SERVER_NAMES, SERVER_NAME_EXT_ID,
};

/// Id of the notary-signed extension naming the session kind:
/// `<mpc|proxy>/<server|browser>`.
pub const SESSION_EXT_ID: &[u8] = b"equinox.session";

/// The fixed PoC notary key. PUBLIC, so anyone can forge attestations with it;
/// a real deploy sets `EQUINOX_NOTARY_KEY` (hex, 32 bytes) or uses a third-party notary.
pub const DEV_NOTARY_KEY: [u8; 32] = [1u8; 32];

/// TLS commit protocol the prover and notary run.
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TlsMode {
    /// MPC-TLS: the notary holds key shares, never sees plaintext.
    Mpc,
    /// Proxy-TLS: the notary relays the TLS bytes and the prover proves the
    /// plaintext in ZK (tlsn `VerifierCommitStart::Proxy`).
    Proxy,
}

impl TlsMode {
    pub fn as_str(self) -> &'static str {
        match self {
            TlsMode::Mpc => "mpc",
            TlsMode::Proxy => "proxy",
        }
    }
}

impl std::str::FromStr for TlsMode {
    type Err = anyhow::Error;

    fn from_str(s: &str) -> anyhow::Result<Self> {
        match s.trim().to_ascii_lowercase().as_str() {
            "mpc" => Ok(TlsMode::Mpc),
            "proxy" => Ok(TlsMode::Proxy),
            o => anyhow::bail!("unknown TLS mode {o:?} (mpc | proxy)"),
        }
    }
}

impl std::fmt::Display for TlsMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

/// The notary signing key: `EQUINOX_NOTARY_KEY` (hex) or [`DEV_NOTARY_KEY`].
#[derive(Clone)]
pub struct NotaryKey(pub [u8; 32]);

impl NotaryKey {
    pub fn from_env() -> anyhow::Result<Self> {
        match std::env::var("EQUINOX_NOTARY_KEY") {
            Ok(h) => {
                let b = hex::decode(h.trim().trim_start_matches("0x"))?;
                Ok(NotaryKey(b.try_into().map_err(|_| anyhow::anyhow!("EQUINOX_NOTARY_KEY is not 32 bytes"))?))
            }
            Err(_) => Ok(NotaryKey(DEV_NOTARY_KEY)),
        }
    }

    pub fn is_dev(&self) -> bool {
        self.0 == DEV_NOTARY_KEY
    }

    /// Compressed SEC1 public key, as tlsn reports it in a presentation.
    pub fn public_key(&self) -> Vec<u8> {
        let sk = k256::ecdsa::SigningKey::from_bytes(&self.0.into()).expect("valid notary key");
        sk.verifying_key().to_encoded_point(true).as_bytes().to_vec()
    }

    /// Ethereum address (what the contract's `ecrecover` returns).
    pub fn address(&self) -> [u8; 20] {
        let sk = k256::ecdsa::SigningKey::from_bytes(&self.0.into()).expect("valid notary key");
        address_of(sk.verifying_key())
    }
}

pub fn address_of(vk: &k256::ecdsa::VerifyingKey) -> [u8; 20] {
    use sha3::Digest;
    let pt = vk.to_encoded_point(false);
    let h = sha3::Keccak256::digest(&pt.as_bytes()[1..]);
    h[12..].try_into().expect("20 bytes")
}
