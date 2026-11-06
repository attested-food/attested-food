//! Shared, target-independent logic of the Equinox report proof. `no_std` +
//! `alloc`, so every zkVM guest is a thin wrapper over this crate.
//!
//! - [`extract::run`]: recompute the TLSNotary body commitment over
//!   `pdf || blinder`, walk the PDF through its xref table, inflate page 1 and
//!   its ToUnicode CMaps, extract the chosen rows, report number, product,
//!   ULR and issue date, and assert no customer PII reaches them.
//! - [`public::PublicValues`]: the one public-values byte layout every backend
//!   commits and every verifier (Rust and Solidity) decodes.
//! - [`tlsn`]: the TLSNotary attestation checks that need only SHA-256 (Merkle
//!   root, leaf openings, body commitment preimage), for in-guest use.
//!
//! Features: `std` (native builds: keeps the decoded runs and PII words on
//! [`extract::Output`] for tests and host-side re-checks), `sp1` (SHA-256 via
//! the SP1 precompile on the SP1 target), `risc0` (SHA-256 via the RISC Zero
//! accelerator on the RISC Zero target), `track` (SP1 cycle-tracker markers),
//! `all-pages` (decode every page instead of page 1), `serde`.

#![cfg_attr(not(feature = "std"), no_std)]
// The extraction code is the PoC guest kept as is: rewrites shift guest cycles.
#![allow(
    clippy::manual_is_multiple_of,
    clippy::manual_div_ceil,
    clippy::let_unit_value,
    clippy::if_same_then_else,
    clippy::manual_contains,
    clippy::new_without_default
)]

extern crate alloc;
#[cfg(all(feature = "track", not(feature = "std")))]
extern crate std;

pub mod eurekha;
pub mod extract;
pub mod inflate;
pub mod pdf;
pub mod public;
pub mod sha;
pub mod text;
pub mod tlsn;

pub use extract::{run, Output, Row};
pub use public::PublicValues;

/// Length of the TLSNotary plaintext-hash blinder appended to the body.
pub const BLINDER_LEN: usize = 16;

/// Labels revealed when a caller does not choose any.
pub const DEFAULT_LABELS: [&str; 2] = ["Energy", "Protein"];

/// The guest input buffer: the attested response body followed by its blinder,
/// so `SHA256(body || blinder)` is hashed in place over one allocation.
pub fn input_buffer(pdf: &[u8], blinder: &[u8; BLINDER_LEN]) -> alloc::vec::Vec<u8> {
    let mut buf = alloc::vec::Vec::with_capacity(pdf.len() + BLINDER_LEN);
    buf.extend_from_slice(pdf);
    buf.extend_from_slice(blinder);
    buf
}
