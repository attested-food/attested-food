//! SP1 guest for the TLSNotary-attested Eurekha statement
//! (`equinox_core::eurekha::run_attested_unsigned`), the same statement as
//! format 2 of the OpenVM guest.
//!
//! Private input: `OnchainTlsn`, `OnchainRequest`, `RequestSecret`, then one
//! buffer `pdf || blinder`. Commits `EurekhaAttested::encode()`: the
//! attestation header (the verifier checks the notary signature over
//! `keccak256(header)`), bucket host, session time, `sha256(object key)` and
//! the Eurekha values.

#![no_main]
sp1_zkvm::entrypoint!(main);

use equinox_core::tlsn::{OnchainRequest, OnchainTlsn, RequestSecret};

pub fn main() {
    let t = sp1_zkvm::io::read::<OnchainTlsn>();
    let req = sp1_zkvm::io::read::<OnchainRequest>();
    let secret = sp1_zkvm::io::read::<RequestSecret>();
    let buf = sp1_zkvm::io::read_vec();

    let out = equinox_core::eurekha::run_attested_unsigned(&buf, &t, &req, &secret)
        .unwrap_or_else(|e| panic!("attestation: {e:?}"));

    sp1_zkvm::io::commit_slice(&out.encode());
}
