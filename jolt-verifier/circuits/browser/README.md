# Website Jolt browser circuit lane

Partial components only. No complete browser Jolt verifier or Akita PCS verifier is implemented yet. The historical Dory components outside this directory are not the website protocol.

## Source identity

Read-only website source: sibling `attested-food-jolt-prove`, `jolt-webgpu-prove` commit `7335214`, with another session's uncommitted `frontend/src/lib/jolt.ts` tuning left untouched. The page calls guest tiers 20 (SHA chunk), 21 (SHA finish), 31 (extraction), and 33 (TLS). Even a small tier-20 fixture must use this guest and verifier configuration, not an unrelated Fibonacci guest.

The assets originate from `webgpu-zkvm-poc`. Its `guests/jolt/FORK_REV` is `6d3bdeb4e3f42f1480f50220f546d64e9adb0058` of `0xAndoroid/jolt-wasm-prover`, with `guests/jolt/fork.patch`. Its `core/UPSTREAM_REV` is `2320a68`, with `core/UPSTREAM_PATCH` and the tier/SHA additions described in that project's README.

The fork's manifest and setup script pin:

- Jolt `d39bd518a65ea89401de63c3343e98fbad5f1b80`.
- Akita `252abb895046cc1d5b9955a26a2ad2318148ac26`.
- Spongefish registry `0.7.4`, deliberately replacing the earlier pointer-width-dependent counter encoding. The exact resolved lockfile is part of fixture provenance.
- Jolt `akita` features and `jolt-field/solinas`. Transparent packed commitments, little-endian scalar challenges, not BN254/Dory.

The setup script also applies numbered patches 0001, 0003 through 0009. Their full bytes and the outer fork patch must be included in reproducible build provenance. GPU patch names alone are not evidence that they cannot change proof bytes. Fixture lane owns the existing disposable VM and must confirm the actual patched checkout/configuration and emitted schema.

Sources inspected as data:

- [Fork manifest](https://github.com/0xAndoroid/jolt-wasm-prover/blob/6d3bdeb4e3f42f1480f50220f546d64e9adb0058/Cargo.toml)
- [Fork setup script](https://github.com/0xAndoroid/jolt-wasm-prover/blob/6d3bdeb4e3f42f1480f50220f546d64e9adb0058/setup-wasm-deps.sh)
- [Akita fp128 preset](https://github.com/LayerZero-Labs/akita/blob/252abb895046cc1d5b9955a26a2ad2318148ac26/crates/akita-config/src/proof_optimized/fp128.rs)
- [Jolt fp128 encoding and arithmetic](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-field/src/solinas/fp128.rs)
- [Jolt protocol selection](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-verifier/src/config.rs)

## Implemented field relation

`fp128.circom` fixes p to `2^128 - 2^32 + 22537`, decimal `340282366920938463463374607427473266697`. Inputs and outputs are two little-endian u64 limbs. Compile over BN254 Fr with Circom 2.2.3.

- `BrowserFp128Canonical`: each limb is 64 bits. A 128-bit nonnegative slack proves packed value is strictly below p. Both sides of the bound are less than 2^129, so the outer field cannot wrap.
- `BrowserFp128Add`, `BrowserFp128Sub`: canonical operands/result and a Boolean reduction quotient. The integer equations fit in 129 bits.
- `BrowserFp128Mul`: canonical operands/result, a 128-bit quotient, four 64-by-64 products, and four coefficient equations prove `a*b = q*p + r`. Interior signed carries lie in `[-2^66, 2^66)` via shifted 67-bit decompositions; endpoint carries are zero. Each local equality has absolute integer discrepancy below 2^132, far below Fr, so an outer-field congruence implies the integer equation. The complete 256-bit product is never formed as one Fr value.
- The product witness function uses bounded schoolbook coefficients and 256-step binary long division. No intermediate exceeds 130 bits. Its output is a witness calculation only; the quotient/remainder identity and bounds are constrained separately.
- `BrowserFp128InverseCheck`: verifies a canonical caller-supplied inverse by the full multiplication relation and requires product one. Zero is rejected.

These templates do not accept any offchain verification Boolean. They are field components, not scalar-stage or PCS verification.

## Component tests

```sh
python3 -m unittest discover -s jolt-verifier/tools/browser-circuits -p 'test_*.py' -v
```

Uses only installed Circom, Node, snarkjs and Python's standard library. Tests compile our authored circuits and require successful witnesses to pass `snarkjs wtns check`. Includes maximal/carry boundary values, deterministic random values, wrong results, invalid field/limb encodings, and invalid inverses. A regression test rejects the wrong result obtained by reducing a 256-bit product modulo outer Fr before reducing modulo p.

No external packages are installed, built, or executed on the host.

## Transcript boundary findings

Do not use one generic Blake2b transcript for both layers:

1. Jolt's deployed `DigestTranscript` has a 32-byte state and u32 round counter. An append hashes `state || 32-byte-round-word || payload`; the round is big-endian in the last four bytes of that word. A squeeze hashes only state and round word, updates to the full 32-byte digest, and scalar challenge extraction consumes the first 16 bytes. Fp128 scalar decoding is little-endian reduction. The exact digest instantiation and typed append framing must be checked at the actual fork verifier call site.
2. `bridged_akita_transcript` in Jolt's adapters derives a statement-bound outer scalar challenge and incorporates it into the nested session label. The full session-label bytes must be constrained, not selected by a host hint.
3. Akita's `AkitaTranscript` uses Spongefish Blake2b512, with a 64-byte protocol tag, a session domain, and an instance-bound encoding. Absorbed byte payloads are framed with a u64 little-endian length. Scalar challenge extraction squeezes 32 bytes and reduces them into Fp128. Labels do not enter this production sponge. This is not the same engine, framing, or challenge width as Jolt's deployed digest transcript.

Sources: [Jolt digest](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-transcript/src/digest.rs), [bridge adapter](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-akita/src/adapters.rs), [Akita substrate](https://github.com/LayerZero-Labs/akita/blob/252abb895046cc1d5b9955a26a2ad2318148ac26/crates/akita-transcript/src/sponge.rs).

## Full-verifier work still required

- Exact fixture, patched-source and schedule identity; fixed guest/program preprocessing and shape; genuine same-shape positive/tamper cases.
- Current modular Rust scalar stages, input/output/program binding, all sumchecks, and point/evaluation batching. The historical AST does not cover this revision.
- Constrained Blake2b hashes and both transcript engines, serialization, counter updates, scalar reduction, session/instance framing and bridge.
- Akita configuration/schedule validation, commitment/setup binding, ring operations and sparse challenges, grinding checks where selected, digit/range and relation sumchecks, extension reductions, folds, terminal checks, and the final PCS opening relation.
- A shared circuit key accepting at least two genuine website proofs and rejecting statement and proof mutations.

A sound operation export needs explicit SSA IDs and typed operations, constraints for every verifier comparison, canonical byte/limb relations, and fixed structural choices. Never reconstruct dependencies from a map keyed by concrete field value: unrelated witness values can coincide. Never replace an unsupported Rust branch, PCS check, hash, or comparison with its native result. Because field aliases and PCS code use concrete layouts/SIMD as well as generic traits, a tracked-field build is not automatically a drop-in replacement. First export exact replay events and inventory concrete call sites in the VM; then implement a typed trace backend or port the fixed-shape verifier. Native acceptance and boundary dumps remain diagnostic only.
