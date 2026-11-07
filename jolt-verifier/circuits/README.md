# Circuit components

Partial implementation only. There is no complete Jolt verifier here. In particular, scalar AST acceptance does not verify the Dory polynomial commitment opening.

## Implemented

- `transcript.circom`: canonical Fr decomposition and the four historical AST byte transforms. The decomposition constrains bits and the strict modulus bound, not only reconstruction modulo Fr.
- `poseidon.circom`: our generated width-4 Poseidon permutation, 8 full rounds, 56 partial rounds. Numeric parameters come from historical Jolt. No external Circom library is needed by these components.
- `../tools/circuits/ast_to_circom.py`: standard-library-only AST compiler. Emits `JoltScalarStages`, not a full-verifier template. Arithmetic, nonzero inverses, Poseidon, transcript transforms, all three assertion variants, and selected boundary node outputs are supported. Fq inputs and unsupported nodes fail rather than becoming unconstrained hints.

The generator requires a JSON list of public variable indices. Historical Jolt assigns `ProofData` to all inputs, so its metadata cannot determine statement visibility. Inputs are named `v<index>`, matching the exporter's indexed witness. The manifest maps these names to upstream names and reports unused inputs. Unused values still need review and binding in the PCS wrapper.

The default output is a component without `main`. `--standalone-scalar` emits a test-only main. Its manifest always says `pcs_verified: false` and `complete_jolt_verifier: false`.

`--exports` takes a JSON list of AST node IDs and connects their constrained values to `boundary[]`. This permits transcript state/counter and opening-point/evaluation values to feed PCS without accepting host-computed boundary values as authoritative.

## Verification

From the repository root:

```sh
python3 -m unittest discover -s jolt-verifier/tools/circuits -p 'test_*.py' -v
```

Tests use installed Circom, Node, and snarkjs, without installing packages. Circuits are compiled once per test and checked with `snarkjs wtns check`; witness generation must reject modified inputs. These are component tests, not genuine Jolt proofs or Groth16 same-key proof tests.

Set `JOLT_POSEIDON_CONSTANTS` to an inspected historical `constants.go` file to additionally test reproducible regeneration and a near-modulus vector. Without it, the committed circuit is still tested against the two independently published historical Rust output vectors.

## Parameter provenance

Jolt pin: `ad03c835f5f7e152b625543c488eec446e3206c0`.

- [AST definitions](https://github.com/a16z/jolt/blob/ad03c835f5f7e152b625543c488eec446e3206c0/zklean-extractor/src/mle_ast.rs)
- [AST bundle](https://github.com/a16z/jolt/blob/ad03c835f5f7e152b625543c488eec446e3206c0/zklean-extractor/src/ast_bundle.rs)
- [Numeric Poseidon parameters](https://github.com/a16z/jolt/blob/ad03c835f5f7e152b625543c488eec446e3206c0/transpiler/go/poseidon/constants.go)
- [Independent test vectors](https://github.com/a16z/jolt/blob/ad03c835f5f7e152b625543c488eec446e3206c0/transpiler/go/poseidon/poseidon_test.go)

`constants.go` SHA256: `cef07e858736e4e97c90165d28c911c8c6194410144be08db563829feb61cdce`.

`poseidon_constants.py` parses numeric assignments as text, never executes Go, and requires an expected SHA256 when used through its CLI. It implements the permutation in our own generator. The generated circuit records the source digest.

## Remaining complete-verifier work

1. Reproduce a single shape with at least two genuine proofs, indexed scalar witnesses, complete Dory proof/setup, and native boundary diagnostics.
2. Export constrained AST roots for the PCS boundary. Compare them to native diagnostics for debugging, but never use diagnostics as an acceptance oracle.
3. Constrain original commitment encodings and the joint commitment's challenge-weighted GT combination. Constrain point order, evaluation, and transcript state/counter continuity.
4. Implement canonical nonnative BN254 Fq limbs, Fq2/Fq6/Fq12 arithmetic, complete G1/G2 operations with infinity handling, subgroup checks, GT membership, and exact arkworks compressed serialization constraints.
5. Implement Dory 0.3.0 transcript and reduce/fold operations, including nonzero challenges, all GT scalar actions, and the final four-pairing equation with final exponentiation.
6. Reject malformed dimensions and any ZK-only fields for the selected transparent protocol. Keep setup/program/shape circuit constants or bind them to a fixed public digest.
7. Run at least two genuine proofs under one outer circuit key and negative statement, sumcheck, commitment, point, evaluation, transcript, and PCS cases.

## Dependency approval request

No external pairing sources have been vendored or executed.

Candidate: [yi-sun/circom-pairing](https://github.com/yi-sun/circom-pairing/tree/107c316223a08ac577522c54edd81f0fc4c03130), pinned at `107c316223a08ac577522c54edd81f0fc4c03130`.

Required source subset includes common bigint/field arithmetic and helpers; curve and Fp2 curve operations; BN254 curve constants, Fp12 arithmetic, subgroup checks, Miller-loop product, and final exponentiation. Its bigint circuit imports circomlib `comparators.circom`, `bitify.circom`, and `gates.circom`, plus their transitive circuit includes. A candidate circomlib source pin is `35e54ea21da3e8762557234298dbb553c175ea8d` (package 2.0.5, LGPL-3.0). The pairing package requests circomlib `^2.0.2`; compatibility with that newer source pin must be tested, not assumed.

Important license conflict: the pairing repository's `LICENSE.md` contains GPL version 3, while its `package.json` says ISC. Treat this as unresolved and do not rely on the permissive package metadata. Circomlib's package metadata says LGPL-3.0. Any copied subtree's own notices also need review. Approval needs to cover source vendoring, license choice/review, and isolated compilation/testing. No npm install, upstream scripts, or upstream test runner is needed for the proposed source-only integration.

The pairing README explicitly describes its circuits as unaudited demonstration code. Adopting it still requires adversarial arithmetic, serialization, subgroup, and pairing tests. It does not supply Dory or the Jolt-to-Dory boundary binding.
