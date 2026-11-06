//! OpenVM guest for lab-report proofs, a thin wrapper over `equinox-core`.
//!
//! Private input: a format byte, then per format:
//! - `0` Equinox: the chosen analyte labels (OpenVM serde), then `pdf || blinder`.
//!   Commits `PublicValues::encode()` (`equinox_core::run`).
//! - `1` Eurekha: `pdf || blinder`. Commits `Eurekha::encode()`
//!   (`equinox_core::eurekha::run`): body commitment, redacted-PDF hash and
//!   spans, every non-customer key-value pair and result row.
//! - `2` Eurekha, TLSNotary-attested: `OnchainTlsn`, `OnchainRequest`,
//!   `RequestSecret` (OpenVM serde), then `pdf || blinder`. Commits
//!   `EurekhaAttested::encode()` (`eurekha::run_attested_unsigned`): the
//!   attestation header, bucket host, session time, `sha256(object key)` and
//!   the Eurekha values. The verifier checks the notary signature over
//!   `keccak256(header)` (secp256k1 in the guest costs about 4x the rest).
//! - `3` as `2`, with the notary address first and the signature checked in
//!   the guest (`eurekha::run_attested`); commits the address.
//!
//! OpenVM user public values are a fixed 32 bytes, so the guest reveals the
//! sha256 of the encoded public values; the server returns the bytes.

#![no_std]
#![no_main]

extern crate alloc;

use alloc::{string::String, vec::Vec};

use equinox_core::tlsn;

openvm::entry!(main);

fn main() {
    let format: u8 = openvm::io::read();
    let pv = match format {
        0 => {
            let chosen: Vec<String> = openvm::io::read();
            let buf = openvm::io::read_vec();
            equinox_core::PublicValues::from(equinox_core::run(&buf, &chosen)).encode()
        }
        1 => equinox_core::eurekha::run(&openvm::io::read_vec()).encode(),
        2 | 3 => {
            let notary: Option<[u8; 20]> = (format == 3).then(openvm::io::read);
            let t: tlsn::OnchainTlsn = openvm::io::read();
            let req: tlsn::OnchainRequest = openvm::io::read();
            let secret: tlsn::RequestSecret = openvm::io::read();
            let buf = openvm::io::read_vec();
            match notary {
                Some(n) => equinox_core::eurekha::run_attested(&buf, &t, &req, &secret, &n, &tlsn::K256Recover),
                None => equinox_core::eurekha::run_attested_unsigned(&buf, &t, &req, &secret),
            }
            .unwrap_or_else(|e| panic!("attestation: {e:?}"))
            .encode()
        }
        _ => panic!("unknown report format"),
    };
    openvm::io::reveal_bytes32(equinox_core::sha::sha256(&pv));
}
