# Dory PCS assembly contract

Design notes only. No PCS circuit is implemented. Native boundary values are diagnostics, never proof-verification oracles.

## Exact source

Jolt `ad03c835f5f7e152b625543c488eec446e3206c0` resolves registry `dory-pcs 0.3.0`, SHA256 `b8c58baea9f0ed973489cd1981b0e6a8c91aafddb05e3903b1dd54175ddcb52d`.

The published crate's `.cargo_vcs_info.json` identifies `322875b01866424c91247288c4b58d54b57a3c75`. Do not substitute the repository's `v0.3.0` tag (`78ddee8735abc50e4b95c1620686e57cfd873c59`) without checking every difference. The observations below come from the published crate source, inspected as data.

Sources:

- [Dory evaluation verification](https://docs.rs/crate/dory-pcs/0.3.0/source/src/evaluation_proof.rs)
- [Dory reduce/fold and final check](https://docs.rs/crate/dory-pcs/0.3.0/source/src/reduce_and_fold.rs)
- [Dory arkworks serialization](https://docs.rs/crate/dory-pcs/0.3.0/source/src/backends/arkworks/ark_serde.rs)
- [Dory group operations](https://docs.rs/crate/dory-pcs/0.3.0/source/src/backends/arkworks/ark_group.rs)
- [Jolt adapter](https://github.com/a16z/jolt/blob/ad03c835f5f7e152b625543c488eec446e3206c0/jolt-core/src/poly/commitment/dory/wrappers.rs)
- [Jolt Poseidon transcript](https://github.com/a16z/jolt/blob/ad03c835f5f7e152b625543c488eec446e3206c0/jolt-core/src/transcripts/poseidon.rs)
- [Jolt transcript framing](https://github.com/a16z/jolt/blob/ad03c835f5f7e152b625543c488eec446e3206c0/jolt-core/src/transcripts/transcript.rs)

Dory's crate includes MIT and Apache-2.0 license files. No Dory Rust execution or dependency installation is needed for these notes.

## Boundary ownership

A complete wrapper must receive these values as constrained outputs of the scalar/batching portion, not fresh unbound witness inputs:

| Value | Circuit representation | Required relation |
| --- | --- | --- |
| Poseidon state | one native Fr | Exact previous transcript state |
| Poseidon counter | one bounded u64 | Exact previous counter, no reset |
| Opening point | fixed-length Fr array | Exact final opening point, reversed once at the Jolt-to-Dory call boundary |
| Evaluation | one native Fr | Exact final joint opening evaluation |
| Joint commitment | 12 canonical Fq coefficients in an agreed extension-field basis | Challenge-weighted GT combination of the same commitments absorbed by the scalar transcript |

The fixture exporter provides native versions of these values, full proof/setup, and indexed scalar witness. Exporting a native boundary value does not itself constrain it. The AST needs roots for state/counter, point, evaluation, and every scalar coefficient used by commitment batching. Use the generator's `--exports` node-ID list to expose reachable native values. If those roots do not exist in the current AST arena, change the fixture-side symbolic export rather than inserting host-computed constants.

Proposed wrapper wiring:

- Scalar inputs remain `v<index>`; visibility is an explicit fixed public-index list, not historical `WitnessType` metadata.
- `boundary[]` positions have a shape-specific manifest mapping each position to its AST node ID and semantic role.
- PCS proof messages are private inputs in canonical limb/point representations. No host acceptance Boolean is an input.
- Setup, program identity, dimensions, message counts, and extension-field basis are fixed circuit parameters or bound to an approved public digest. A witness-supplied setup must not select a different verification key.
- A converter may produce limbs, serialized bytes, and arithmetic witnesses, but constraints must check all of their relations.
- Exported compressed bytes must be constrained to the same points/GT elements used in arithmetic. Byte-to-Fr transcript absorption alone loses information and is not a substitute for canonical Fq constraints.

The exporter and PCS converter still need to agree on concrete JSON field names and Fq12 basis order. This document does not claim an already-agreed fixture schema.

## Transcript framing

The Jolt-to-Dory adapter ignores Dory's supplied labels. `append_serde` uses Dory compressed serialization, then calls Jolt `append_bytes` with the fixed label `dory_serde`. It does not use Jolt `append_serializable` and its uncompressed encoding.

For a serialized message of length L:

1. Make a 32-byte frame containing ASCII `dory_serde` at the beginning, zero padding through byte 23, then L as an 8-byte big-endian integer in bytes 24 through 31.
2. Absorb that frame as one raw byte append.
3. Absorb the serialized message as one raw byte append.

For each raw byte append, split into consecutive chunks of at most 32 bytes. Interpret each chunk little-endian and reduce modulo Fr. Hash the first chunk as `Poseidon3(state, counter, chunk)`; hash subsequent chunks as `Poseidon3(previous, 0, chunk)`. Update the stored state only after the chain and increment the stored counter exactly once for the whole raw append. An empty raw append hashes zero once. Thus each `append_serde` increments the counter by two regardless of its byte length.

A Dory scalar challenge ignores its supplied label. It computes `Poseidon3(state, counter, 0)`, stores that full Fr as the new state, increments the counter once, and returns that same full Fr. There is no byte reversal, 128-bit truncation, added challenge label, or fresh transcript initialization at this boundary.

Compressed G1/G2 encodings must match arkworks 0.5, including sign/infinity flags. `ArkGT` wraps Fq12 directly and serializes that field element, not an elliptic-curve point. The exact coefficient ordering must be cross-checked against native serialized fixtures before implementation. GT group addition in Rust means Fq12 multiplication; scalar action means exponentiation, not coefficient-wise multiplication.

## Transparent proof schedule

Reject all ZK-only optional fields, matching Jolt's non-ZK verifier. Fix nu and sigma for the selected shape, require point length `nu + sigma`, require exactly sigma first and second messages, and enforce the setup capacity bound. The supported non-square layout has nu no greater than sigma.

Absorption/challenge order:

1. VMV `c`, `d2`, `e1`.
2. For each of sigma rounds, first-message `d1_left`, `d1_right`, `d2_left`, `d2_right`, `e1_beta`, `e2_beta`, then beta.
3. In that same round, second-message `c_plus`, `c_minus`, `e1_plus`, `e1_minus`, `e2_plus`, `e2_minus`, then alpha.
4. Gamma.
5. Final-message `e1`, `e2`, then d.

All message entries use the framed `append_serde` above. Alpha and beta are inverted during each round; gamma and d are inverted in the final transparent check. Constrain these inverses to reject zero.

Initialize C from VMV c, D1 from the joint commitment, D2 from VMV d2, E1 from VMV e1, and E2 from evaluation times setup g2_0. Save E1_init and D2_init for the deferred VMV equation.

Coordinates are `s1 = point[..sigma]` and `s2 = point[sigma..sigma+nu]` padded with trailing zeros to length sigma. Fold MSB-first: round zero consumes coordinate index sigma minus one. Start both scalar accumulators at one. At each round multiply the first accumulator by `alpha*(1-s1_coord)+s1_coord`, the second by `alpha_inverse*(1-s2_coord)+s2_coord`.

The C, D1, D2, E1, and E2 updates must follow `process_round` exactly, using setup entries indexed by the remaining-round count before decrement, not by the forward round number. These updates require real G1/G2 arithmetic and GT exponentiation/multiplication.

## Final PCS equation

The transparent verifier compares a four-pair multi-pairing against the accumulated GT right-hand side. A generic pairing-product-equals-one wrapper with no arbitrary GT accumulator input is insufficient by itself.

The four pair inputs are:

1. `final_e1 + d*g1_0`, `final_e2 + d_inverse*g2_0`.
2. `h1`, `-gamma*(E2_acc + d_inverse*s1_acc*g2_0)`.
3. `-gamma_inverse*(E1_acc + d*s2_acc*g1_0)`, `h2`.
4. `d_squared*E1_init`, `g2_0`.

The GT right-hand side, written in Dory's additive group notation, is `C_acc + (s1_acc*s2_acc)*ht + chi[0] + d*D2_acc + d_inverse*D1_acc + d_squared*D2_init`. In Fq12 this is a product of GT powers. The final exponentiation result of the four Miller loops must equal that complete value.

Do not omit pair four or the `d_squared*D2_init` term: together they implement the deferred VMV check. Do not substitute the exported native joint commitment or native Boolean result for the constrained boundary and final equation.
