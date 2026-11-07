# Outer Jolt transcript replay

Partial components for the website's pinned Jolt/Akita format. This is not a complete Jolt verifier, stage relation or Akita PCS verifier.

## Source contract

Jolt `d39bd518a65ea89401de63c3343e98fbad5f1b80`:

- [digest.rs](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-transcript/src/digest.rs): initial label padding, append/squeeze hashes and counter increments.
- [legacy.rs](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-transcript/src/legacy.rs): canonical field absorption, labels, labeled counts and u64 words.
- [verifier.rs](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-verifier/src/verifier.rs): the verifier initializes with label `Jolt`.
- [fp128.rs](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-field/src/solinas/fp128.rs): scalar challenges reduce little-endian bytes in the website field. The default optimized decoding in `algebra.rs` is also little-endian.

The actual pinned sources were read in the fixture VM. The newer cached Jolt checkout is not the target.

## Interface

`BrowserJoltReplay(N, SIZES, SQUEEZES)` fixes the entire operation schedule at compilation. `SIZES[i]` is the number of appended bytes. `SQUEEZES[i]` is zero for append and one for scalar squeeze; a squeeze must have size zero. An empty append and a scalar squeeze produce the same next digest, but only the latter emits a challenge. For an empty schedule, pass `[0]` as the unused array parameter because Circom does not parse an empty array literal.

The `payload` input concatenates all append messages without introducing length prefixes. The transcript starts from BLAKE2b-256 of `Jolt` right-padded to 32 bytes, not from a caller-supplied state. Every operation constrains the next hash and uses its fixed zero-based u32 round number. `states` contains the initial and all subsequent states. `challenges` contains only squeeze results as two canonical LE64 limbs.

`BrowserJoltFieldMessage` emits a canonical field value as 16 big-endian bytes. This is deliberately different from scalar challenge decoding.

`BrowserJoltLabelMessage(LENGTH, LABEL, HAS_COUNT)` binds a constant label. Without a count, it right-pads to 32 bytes and requires its `count` input to be zero. With a count, the label must fit 24 bytes and its constrained u64 count occupies the last eight bytes in big-endian order. Length zero with count enabled gives the deployed `U64Word` encoding.

## Remaining binding

The full verifier must bind every payload slice to its approved preprocessing, public IO, commitments or canonical proof message and fix the exact protocol operation order. A caller-chosen sequence of unconstrained messages is not proof verification. The current tests use synthetic messages and an independent hashlib reference, not complete native proof transcript vectors.

The nested Akita Spongefish transcript is separate and must not use this engine. Its session bridge consumes the canonical little-endian encoding of the appropriate outer challenge.

Public IO normalization must match native `validate_inputs`: it removes all trailing zero output bytes before absorbing the preamble. This also removes zero-valued suffix bytes of the postcard result, not just runtime word padding. The complete relation must retain the execution/statement binding to those zero bytes rather than treating the normalized slice as an arbitrary shorter output.

## Tests

```sh
python3 -m unittest discover -s jolt-verifier/tools/browser-transcript -p 'test_*.py' -v
```

Tests check initialized replay, repeated squeezes, two different messages in the same fixed circuit, canonical field framing, label/count/u64 encoding, byte and count bounds, malformed schedules, and state/challenge mutations. Positive witnesses are explicitly checked against R1CS.
