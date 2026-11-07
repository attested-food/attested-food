# Website compressed sumcheck scalar components

Partial clear Boolean-hypercube components for the website `/prove` equinox guest (tiers 20, 21, 31, 33). Not historical Dory. External challenges, weights and stage relation values are not full proof verification. No transcript, stage relation, opening authentication or Akita PCS verification is implemented here.

## Sources

Inspected read-only native source at Jolt `d39bd518a65ea89401de63c3343e98fbad5f1b80`:

- [`crates/jolt-poly/src/compressed_univariate.rs`](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-poly/src/compressed_univariate.rs): `CompressedPoly` (the current name, not `CompressedUniPoly`) stores `[c0,c2,c3,...]`. Stored length is the declared degree, including trailing zero coefficients. `c1 = claim - 2*c0 - sum(c2,...)`. Empty vectors are rejected by the verifier.
- [`crates/jolt-sumcheck/src/verifier.rs`](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-sumcheck/src/verifier.rs): `verify_compressed` checks round count, degree bound and nonempty vectors, appends `LabelWithCount(round_label, stored_len)` and the stored coefficients, draws a challenge, then evaluates with the running claim as hint. Reconstruction enforces the Boolean round-sum identity; no separate round-sum proof element is serialized.
- [`crates/jolt-sumcheck/src/batch.rs`](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-sumcheck/src/batch.rs): `BatchPrelude::try_new` combines input claims with `sum(weight_i * claim_i * 2^(R-member_rounds_i))`. Padding is independent of member activation offset.
- [`crates/jolt-verifier-derive/src/lib.rs`](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-verifier-derive/src/lib.rs): generated `begin_batch`, `verify_clear` and `expected_final_claim` absorb input claims, draw one coefficient per present member, reduce the sumcheck, then compare its final value with `sum(weight_i * member_expected_output_i)`. Weights are independent draws, not powers of a single challenge.

Website source provenance: wasm fork `6d3bdeb4e3f42f1480f50220f546d64e9adb0058`, Akita `252abb895046cc1d5b9955a26a2ad2318148ac26`, Spongefish `0.7.4`. See `../browser/README.md` and `../../website-target.json` for patches and asset provenance. Native proof differential tests remain a later integration check.

## Typed interface

Compile over BN254 Fr with Circom 2.2.3. Every scalar below is `Fp128 = signal[2]`, canonical little-endian u64 limbs, modulus `2^128 - 2^32 + 22537`. Arithmetic and range constraints come from `../browser/fp128.circom`. These templates introduce no witness hints or verification booleans.

| Template | Inputs | Outputs / relation |
| --- | --- | --- |
| `BrowserCompressedUniPoly(D)` | `compressed[D]: Fp128`, `claim: Fp128`, `challenge: Fp128` | `coefficients[D+1]: Fp128` in ascending power order; `out: Fp128` is the evaluation. `1 <= D <= 32`. |
| `BrowserCompressedSumcheck(R,D,degrees)` | `initialClaim: Fp128`, `compressed[R][D]: Fp128`, `challenges[R]: Fp128`, `expectedFinal: Fp128` | `claims[R+1]: Fp128`; adjacent rounds share the running claim; last claim equals `expectedFinal`. `0 <= R <= 255`, `1 <= degrees[r] <= D <= 32`. |
| `BrowserSumcheckBatchInitial(N,R,memberRounds)` | `inputClaims[N]: Fp128`, `weights[N]: Fp128` | `out: Fp128`, padded initial fold. `0 <= memberRounds[i] <= R <= 255`. |
| `BrowserSumcheckWeightedSum(N)` | `values[N]: Fp128`, `weights[N]: Fp128` | `out: Fp128`, unpadded weighted fold for the final relation. |

`R`, `D`, `degrees`, `N` and `memberRounds` are compile-time shape parameters, never private proof-selected selectors. Each round uses exactly `degrees[r]` stored coefficients; unused rectangular slots are constrained to zero. Serialized lengths must match this shape; do not silently pad a shorter serialized vector into a longer declared degree because its transcript count differs. For zero rounds, pass an ignored dummy degrees array such as `[0]`; the circuit checks canonical `initialClaim == expectedFinal`. Zero-round reduction alone proves no oracle relation.

## Later wiring contract

- Fix shape and present-member order from the approved guest/configuration. Validate member activation windows and derive the correct challenge slices for each stage relation outside these primitives.
- Constrain the native transcript's input-claim absorption, per-member weight draws, counted round messages and challenges. Connect its canonical Fp128 challenges directly, without host-generated acceptance flags.
- Connect `BrowserSumcheckBatchInitial.out` to `BrowserCompressedSumcheck.initialClaim`.
- Compute each member's actual `expected_output` relation in constraints, including aliases and opening-point derivation. Connect those results to `BrowserSumcheckWeightedSum.values`, reuse the same weights, and connect its output to `expectedFinal`.
- Authenticate the consumed claims through the full statement/stage/PCS chain. Supplying arbitrary `expectedFinal` or `values` does not authenticate them.

## Tests

From the repository root, using installed tools only:

```sh
python3 -m unittest discover -s jolt-verifier/tools/browser-scalar -v
```

Tests copy authored components into temporary scratch space and use the merged core by default. `BROWSER_FP128_SOURCE` optionally selects a core snapshot for lane-local testing. Successful witnesses must pass `snarkjs wtns check`. Coverage includes degree 1/2/3 circuit shapes, independent integer reconstruction through degree 32, zero rounds, zero and field/limb boundaries, exponent-255 batch padding, final folding, input mutations, nonzero padding rejection and direct binary witness mutation. These deterministic authored fixtures are not genuine website Jolt proofs.
