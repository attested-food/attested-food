//! OpenVM guest: the Equinox report statement, a thin wrapper over
//! `equinox_core::run`.
//!
//! Private input: the chosen analyte labels (OpenVM serde), then one buffer
//! `pdf || blinder` as a length-prefixed byte stream. The guest recomputes
//! `SHA256(pdf || blinder)`, extracts the chosen rows, report number, product,
//! ULR and issue date, and asserts no customer PII reaches them. OpenVM user
//! public values are a fixed 32 bytes, so it reveals
//! `sha256(PublicValues::encode())`; the server returns the encoded bytes.

#![no_std]
#![no_main]

extern crate alloc;

use alloc::{string::String, vec::Vec};

openvm::entry!(main);

fn main() {
    let chosen: Vec<String> = openvm::io::read();
    let buf = openvm::io::read_vec();

    let out = equinox_core::run(&buf, &chosen);

    let pv = equinox_core::PublicValues::from(out).encode();
    openvm::io::reveal_bytes32(equinox_core::sha::sha256(&pv));
}
