//! OpenVM guest for lab-report proofs, a thin wrapper over `equinox-core`.
//!
//! Private input: a format byte, then per format:
//! - `0` Equinox: the chosen analyte labels (OpenVM serde), then `pdf || blinder`.
//!   Commits `PublicValues::encode()` (`equinox_core::run`).
//! - `1` Eurekha: `pdf || blinder`. Commits `Eurekha::encode()`
//!   (`equinox_core::eurekha::run`): body commitment, redacted-PDF hash and
//!   spans, every non-customer key-value pair and result row.
//!
//! OpenVM user public values are a fixed 32 bytes, so the guest reveals the
//! sha256 of the encoded public values; the server returns the bytes.

#![no_std]
#![no_main]

extern crate alloc;

use alloc::{string::String, vec::Vec};

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
        _ => panic!("unknown report format"),
    };
    openvm::io::reveal_bytes32(equinox_core::sha::sha256(&pv));
}
