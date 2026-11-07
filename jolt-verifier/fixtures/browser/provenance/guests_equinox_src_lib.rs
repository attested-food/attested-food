//! Jolt guest for the Equinox and Eurekha report statements, as tiers (see README).
//!
//! Must agree with `GUEST` in preprocessing/generate.rs: heap, stack, input
//! size and max trace length are baked into the program preprocessing.

#![cfg_attr(feature = "guest", no_std)]

extern crate alloc;

use alloc::{string::String, vec::Vec};

use serde_bytes::ByteBuf;

/// `tier`: 0 = full (commitment + extraction), 1 = extraction only,
/// 2 = SHA-256 of `pdf || blinder` only, 10..=13 = extraction prefixes
/// (12 = parse + inflate page 1, the page's "inflate" tier). Returns the committed bytes, equal to
/// the extractor's `expected_output` (Equinox) or `eurekha_*expected`
/// (Eurekha, 30..=44) for the same tier.
#[jolt::provable(
    heap_size = 8388608,
    stack_size = 262144,
    max_input_size = 500000,
    max_output_size = 4096,
    max_trace_length = 2097152
)]
fn equinox(tier: u8, buf: ByteBuf, chosen: Vec<String>) -> Vec<u8> {
    let buf = buf.into_vec();
    match tier {
        0 => equinox_core::PublicValues::from(equinox_core::run_tier(&buf, &chosen, true)).encode(),
        1 => equinox_core::PublicValues::from(equinox_core::run_tier(&buf, &chosen, false)).encode(),
        2 => equinox_core::sha::sha256_in(&buf, 0, buf.len()).to_vec(),
        // 20..=22: the full statement split into proofs under 2^21 cycles.
        // 20: `state || blocks` -> midstate after the blocks.
        20 => {
            let mut st = equinox_core::sha::state_from_bytes(&buf[..32]);
            equinox_core::sha::compress_blocks(&mut st, &buf[32..]);
            equinox_core::sha::state_bytes(&st).to_vec()
        }
        // 21: `state || total_len (u64 LE) || rest` -> final digest.
        21 => {
            let st = equinox_core::sha::state_from_bytes(&buf[..32]);
            let total = u64::from_le_bytes(buf[32..40].try_into().unwrap());
            equinox_core::sha::finish(st, &buf[40..], total).to_vec()
        }
        // 22: `content_len (u32 LE) || page-1 content || pdf || blinder` ->
        // the extraction tier's public values, without inflating.
        22 => {
            let n = u32::from_le_bytes(buf[..4].try_into().unwrap()) as usize;
            let (content, doc) = buf[4..].split_at(n);
            equinox_core::PublicValues::from(equinox_core::run_with_content(doc, content, &chosen)).encode()
        }
        // 30: Eurekha format 1 (`eurekha::run`, backend2-rs format 1).
        30 => equinox_core::eurekha::run(&buf).encode(),
        // 31: format 1 without either SHA-256 pass (both hashes zero).
        31 => equinox_core::eurekha::run_tier(&buf, false).encode(),
        // 32: format 2, `aux_len (u32 LE) || aux || pdf || blinder`, aux the
        // postcard (OnchainTlsn, OnchainRequest, RequestSecret).
        32 => {
            let (t, req, secret, doc) = attested_inputs(&buf);
            equinox_core::eurekha::run_attested_unsigned(doc, &t, &req, &secret)
                .unwrap_or_else(|e| panic!("attestation: {e:?}"))
                .encode()
        }
        // 33: format 2's attestation segment, `aux_len || aux || commitment ||
        // pdf_len (u64 LE)` -> the encoding before the report.
        33 => {
            let (t, req, secret, rest) = attested_inputs(&buf);
            let c: [u8; 32] = rest[..32].try_into().unwrap();
            let len = u64::from_le_bytes(rest[32..40].try_into().unwrap());
            equinox_core::eurekha::attested_prefix(&t, &req, &secret, &c, len)
                .unwrap_or_else(|e| panic!("attestation: {e:?}"))
        }
        // 40..=44: diagnostic prefixes of the Eurekha extraction.
        s @ 40..=44 => equinox_core::eurekha::run_prefix(&buf, s - 40).to_le_bytes().to_vec(),
        // 10..=13: diagnostic prefixes of the extraction (see run_prefix).
        s => equinox_core::run_prefix(&buf, s - 10).to_le_bytes().to_vec(),
    }
}

type Attested<'a> =
    (equinox_core::tlsn::OnchainTlsn, equinox_core::tlsn::OnchainRequest, equinox_core::tlsn::RequestSecret, &'a [u8]);

/// Split `aux_len (u32 LE) || aux || rest` and decode aux.
fn attested_inputs(buf: &[u8]) -> Attested<'_> {
    let n = u32::from_le_bytes(buf[..4].try_into().unwrap()) as usize;
    let (aux, rest) = buf[4..].split_at(n);
    let (t, req, secret) = postcard::from_bytes(aux).expect("attested inputs");
    (t, req, secret, rest)
}
