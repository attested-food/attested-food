# Akita Spongefish components

Partial components toward website Jolt verification. These are not a complete transcript replay, scalar verifier, or Akita PCS verifier. No offchain acceptance flags are inputs. Existing browser field/hash sources are imported without modification.

## Inspected identity

- Akita `252abb895046cc1d5b9955a26a2ad2318148ac26`, `crates/akita-transcript/src/sponge.rs`.
- Spongefish registry `0.7.4`, lockfile checksum `9500412294eeadb2c7eb513714b37c79670b55ee718f84408bb68d7b3e0c69aa`.
- Source was read from the fixture lane's VM, without writes, installs, or builds. No second VM was started.
- Actual VM Akita `sponge.rs` SHA256: `7d2372e88ff0e37a37af88bcc065eed05e626d8baa0803170ff4511f8f87f4ca`.
- Spongefish `instantiations/hash.rs` SHA256: `33fc9763178f2586abafc7148f4a7c9573f8792377b3abaa6b4dc5f61d1dd8ac`.
- Spongefish `domain_separator.rs` SHA256: `d06026e4a0bfe8ac2c340b474cd8e2dd2e4aa6fbf2157eace1dc5c4df8673718`.

Sources: [Akita substrate](https://github.com/LayerZero-Labs/akita/blob/252abb895046cc1d5b9955a26a2ad2318148ac26/crates/akita-transcript/src/sponge.rs), [Spongefish hash implementation](https://docs.rs/crate/spongefish/0.7.4/source/src/instantiations/hash.rs), [domain separator](https://docs.rs/crate/spongefish/0.7.4/source/src/domain_separator.rs), [Jolt bridge](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-akita/src/adapters.rs).

## Exact byte contract

H is unkeyed sequential BLAKE2b-512. `mask(t)` is 127 zero bytes followed by byte t. CV is 64 bytes, initially zero.

- Start absorbing: open a hash stream containing `mask(0) || CV`; concatenate all subsequent absorbs without extra separators.
- Absorb to squeeze: set CV to `H(H(mask(0) || CV || all_absorbed_bytes))`, then start squeezing.
- Squeeze digest i: `H(mask(1) || CV || u64_be(i))`, starting at zero. Each digest has 64 bytes. Repeated squeeze calls consume a continuous byte stream, including leftovers from the preceding digest.
- Squeeze to absorb: set CV to `H(mask(2) || CV || u64_be(consumed_bytes))`, discard leftovers, then start the new absorb stream with `mask(0) || CV`. The count is bytes actually consumed, not the number of generated digest blocks.

`SpongefishFinishAbsorb(n)` constrains the double-hash transition for an active absorb phase. `SpongefishCounterHash(1)` constrains a squeeze digest; parameter 2 constrains squeeze termination. Its counter is constrained to u64 and serialized big-endian. `SpongefishCVHash` is the underlying mask/CV/suffix hash, not a complete state machine.

Do not finish between consecutive absorbs. In particular, do not ratchet the initial domain/instance frame before absorbing later messages that precede the first challenge. The enclosing fixed-shape replay must bind each CV, counter, phase, and byte slice to its predecessor; allowing callers to choose them independently is not transcript verification.

## Akita framing and Jolt bridge

Domain construction calls `to_prover/to_verifier` with a default zero-CV sponge. It absorbs, in order:

1. ASCII `akita-pcs/transcript/v1/blake2b`, padded to 64 bytes.
2. ASCII `akita-pcs/session-label/v1`, padded to 64 bytes.
3. `u64_le(session_length) || session || u64_le(instance_length) || instance`.

Jolt's bridged session is `base_session_label || canonical_outer_challenge_16_le`. The current grouped trace-opening path's base label is `jolt-akita/precommitted-group-batch/v3`; the direct batch path uses `jolt-akita/batch`. The supported wrapper must select the exact source path, not accept an unconstrained label.

`AkitaBridgedPreamble(label_length, instance_length)` checks canonical fp128 bridge limbs and emits that initial absorb stream. The wrapper must bind its base-label bytes and the canonical instance descriptor to the actual PCS statement. It must not substitute the provisional `akita/default-instance` used by the constructor before instance rebinding.

Each Akita public-message absorb uses `u64_le(payload_length) || payload`. `AkitaAbsorbFrame` constrains this relation and every payload byte. Field payloads are 16 canonical little-endian bytes; serializable messages use Akita compressed serialization. Labels are ignored by the production sponge.

Each Akita verifier-message request consumes 32 bytes, even when the caller asks `squeeze_bytes(n)` for fewer than 32. Unreturned bytes of that 32-byte request are discarded, not reused by Akita. For n greater than 32, it repeatedly requests 32-byte messages and truncates only the final message. For n zero, it makes no sponge request. Thus two successive scalar challenges consume the two halves of the same 64-byte digest; the third uses the first half of digest index one.

`AkitaDecode32` constrains 32-byte little-endian reduction into the website field. It splits the 256-bit integer into lo/hi 128-bit halves and folds `lo + hi*(2^32-22537)`. The folded value and the quotient-times-modulus are below 2^161; a bounded 32-bit quotient and canonical remainder prove exact reduction without native Fr overflow. This does not replace the hash relation that produced those bytes.

## PCS operation API still needed

A full replay must supply a fixed event schedule, not host acceptance decisions:

- Bind the exact session base label, canonical outer challenge and instance descriptor; reset to zero CV only at the source's instance-rebinding call.
- Append canonical serialized messages through `AkitaAbsorbFrame`, buffering consecutive absorbs.
- At the first squeeze after absorbs, constrain `SpongefishFinishAbsorb` on the complete buffered bytes.
- Track total consumed bytes. Generate a new counter-1 hash only when its 64-byte block index changes, and select the exact 32-byte slices, including dropped suffixes of short requests.
- Before absorbing after a squeeze, constrain counter-2 hash with the consumed-byte count. Reset counters only then, as required by the inspected source.
- Constrain grinding nonce encoding/preview state clones and predicates, sparse ring challenge decoding/rejection and challenge reduction as selected by the fixed PCS schedule.

This unit does not implement that event planner/state machine, PCS serialization, rejection sampling, grinding, ring arithmetic, commitment binding, sumchecks, folds, or terminal opening checks. It also does not provide genuine website proof acceptance or same-outer-key integration tests.

## Verification

```sh
python3 -m unittest discover -s jolt-verifier/tools/browser-spongefish -p 'test_*.py' -v
```

The Python reference independently replays byte operations with `hashlib`. Circom tests check satisfying witnesses with `snarkjs wtns check` and reject mutated hashes, counts, encodings, and noncanonical bridge challenges. Tests cover direction changes, streaming leftovers, 64-bit counter encoding, short-request consumption, domain/length framing and full-width challenge reduction.

The fixed source assertion uses Akita's test field `Prime128Offset275`, not the website field. For session `backend-test` and instance `instance`, the source expects first scalar `313598626200370843239849985198023824966` in that test field. Our hashlib replay reproduces this assertion. The accompanying raw-byte vector is derived by our reference, not captured from a native execution. No synthetic value is labelled a native website vector.
