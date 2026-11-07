# Outer transcript capture and VM output framing

## Observed protocol

The compiled source is `.wasm-deps/jolt/crates/jolt-transcript/src/digest.rs`.
`lib.rs` aliases `LegacyBlake2bTranscript<F>` to
`DigestTranscript<Blake2b<U32>, F>`. This is Blake2b with a 32-byte digest,
not Blake2b-512 truncated to 32 bytes. `provenance/jolt.patch` preserves the
exact compiled instrumentation and `provenance/build.json` fingerprints it.

Instrumentation observes the original values after the native operations.
It does not introduce challenge values, replace verification, or alter the
transcript state. Capture is enabled only for the original full verification;
negative verification tests are not mixed into the positive transcript.

Each abc/def capture contains 3,179 events, 1,868 absorbs, 334 squeezes and
334 decoded field challenges. Independent replay reproduces all 2,202 state
transitions and checks the final field challenge against the nested Akita
session-label suffix. Both regenerated proofs, program IO, verifier setup,
inputs, outputs and nested transcript remain byte-identical to the preceding
fixture landing. Native verification still accepts, and all three native
PCS/input/output mutation checks still reject.

## Raw JSONL event schema

`jolt-transcript.jsonl` is the ordered native observation stream. The zero-based
line index is the stable event identifier. Each line is one JSON object.
Hex strings encode bytes in the order consumed or produced, without `0x`.

Metadata events:

- `session`: `label_hex` is the unpadded constructor label; `count` is null.
- `label`: `label_hex` is a semantic label, `count` is null. The next absorb
  contains that label right-padded with zero bytes to 32 bytes.
- `label_count`: `label_hex` occupies at most 24 bytes, followed by zero padding
  to 24 bytes and an 8-byte big-endian unsigned `count` in the next absorb.
- `u64`: empty `label_hex`, unsigned `count`; next absorb is 24 zero bytes and
  the big-endian 8-byte count. The count is at most `2^64 - 1`.

All other events have these fields:

| Field | Type and meaning |
|---|---|
| `op` | `init`, `absorb`, `squeeze`, `decode_challenge`, `decode_scalar`, `state`, or `raw_bytes` |
| `round_before`, `round_after` | Observed u32 counters, represented as JSON integers |
| `state_before_hex`, `state_after_hex` | Exactly 32 bytes each |
| `payload_hex` | Constructor padded label or exact absorbed bytes; empty for other operations |
| `raw_hex` | Full 32-byte squeeze result, or actual raw bytes supplied to a decoder |
| `field_le_hex` | Canonical decoded field representative as exactly 16 little-endian bytes; empty otherwise |

`init` hashes the constructor label right-padded to 32 bytes, starts at round
zero, and records the initial state. For every absorb or squeeze, the hash
prefix is the previous 32-byte state followed by the round counter as a
32-byte big-endian word (28 zero bytes plus u32 big-endian). An absorb then
hashes its entire payload. A squeeze adds no payload. Both update the state
to the digest and increment the counter once.

The two decode operations consume the first 16 bytes of the preceding squeeze.
Both native decoders reduce the little-endian integer modulo
`340282366920938463463374607427473266697` (`2^128 - 2^32 + 22537`). Decode events
are observations, not extra state transitions. `state` and `raw_bytes` are
supported observations, but neither occurs in this pair. No event sorting or
label coalescing is allowed.

## Replayed typed consumer view

`jolt-transcript-replay.json`, schema `website-jolt-outer-replay-v1`, contains:

- Event counts, final state, total rounds, field modulus, and successful replay
  and nested-bridge checks.
- `fields`: ordered objects with original `event_index`, `kind`, `round`,
  `raw_hex`, `field_le_hex`, and canonical `value_decimal` as a decimal string.
- `transitions`: ordered objects with original `event_index`, operation,
  `round_before`, exact `counter_word_be_hex`, and `state_after_hex`.

The nested session is exactly ASCII
`jolt-akita/precommitted-group-batch/v3` followed by the last decoded canonical
16-byte little-endian field value. The original nested `akita-transcript.tsv`
remains available. These observations are witness data and test vectors, not
an acceptance oracle for a circuit.

## Exact padded VM output

For both fixtures, `JoltDevice.outputs` and `outputs-postcard.bin` contain 40
bytes: byte 0 is `0x20` (postcard Vec length 32), bytes `[1,33)` are the SHA-256
digest, and bytes `[33,40)` are seven zeros. `outputs.bin` retains only the
32 digest bytes. All original artifacts and names are preserved.

This is a VM memory-write effect, not a second postcard length prefix or
bincode padding. Relevant source at Jolt commit
`d39bd518a65ea89401de63c3343e98fbad5f1b80`:

1. `jolt-sdk/macros/src/lib.rs`, generated `handle_return`, serializes the
   returned Vec with `postcard::to_slice` into the mapped output region. It
   does not truncate the device output vector to the returned slice length.
2. `crates/jolt-program/src/expand/memory/sb.rs` lowers byte stores through
   `expand_narrow_store` in `memory/shared.rs`. That helper aligns the address
   down with `-8`, loads the containing doubleword, replaces only the selected
   lane, and emits `SD` to write the full doubleword back.
3. `tracer/src/instruction/sb.rs` traces the expanded sequence. `sd.rs` executes
   its full-width store through `Mmu::store_doubleword`. The device path in
   `emulator/mmu.rs::store_doubleword_raw` writes all eight bytes.
4. `common/src/jolt_device.rs::store` grows `outputs` to the highest written
   byte plus one, preserving zeros in the other lanes. The last meaningful
   postcard byte is index 32, so its containing word covers indices 32 to 39.

Consequently this exact guest/run exposes five 64-bit words. Consumers must
bind the full 40-byte VM output, validate its meaningful postcard prefix and
zero tail, and only then expose the 32-byte application digest. This is not a
claim that arbitrary guest output lengths or contents can be freely trimmed.

## Verification limits

Seven regression tests pass, including rejection of a changed absorb payload
and a changed decoded field value. Full native proof acceptance and mutations
were executed again inside the disposable VM. No browser, WebGPU or Circom
verification is claimed by this diagnostic capture landing.
