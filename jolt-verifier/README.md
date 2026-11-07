# Jolt verifier

Work in progress: genuine Jolt proof fixtures and a complete Circom verifier for a pinned protocol. This directory is not an onchain-ready wrapper.

## Protocol target

- Jolt: `ad03c835f5f7e152b625543c488eec446e3206c0`.
- Scalar field: BN254 Fr.
- Commitment scheme: Dory, `dory-pcs` 0.3.0 from the pinned Jolt lockfile.
- Transcript: the pinned Jolt Poseidon implementation.
- Initial guest: Fibonacci, with a fixed verifier shape.

This historical revision retains Jolt's symbolic verifier exporter. Its stages 1 to 7 export is only a starting point: full acceptance also requires constrained stage-8 assembly and Dory verification. It does not support the current browser Akita proofs.

## Layout

- `fixtures/`: genuine proofs, statements and their provenance.
- `tools/fixtures/`: native proof generation, verification and export.
- `circuits/`: Circom verifier components.
- `tools/circuits/`: circuit generation tools.
- `tests/`: circuit compilation, witness generation, R1CS checks and integration tests.

## Verified status (2026-11-07)

- 13 harness and scalar-input schema tests passed.
- 18 scalar-generator, transcript and Poseidon component tests passed, with no skips.
- 6 upstream source-patcher tests passed inside the disposable Linux VM.
- The source patch applied and Rust formatting parsed the exporter, but Rust type-checking has not completed.
- Offline locked Cargo resolution stopped at a missing crates.io `ark-bn254` dependency through `dory-pcs` 0.3.0.

**No genuine Jolt fixtures have been generated yet. Full Dory PCS constraints and full Jolt acceptance tests are not implemented.** The generated scalar manifest explicitly records `pcs_verified: false` and `complete_jolt_verifier: false`.

Dependency downloads require approval. The proposed external pairing code also has an unresolved GPL-v3 license file versus ISC package-metadata conflict. It has not been vendored or executed. See [the circuit notes](circuits/README.md) and [the PCS boundary contract](circuits/pcs-boundary.md).

## Component tests

With the already installed Circom, Node and snarkjs, run from the project root:

```bash
python3 -m unittest discover -s jolt-verifier/tests -v
python3 -m unittest discover -s jolt-verifier/tools/circuits -p test_ast_to_circom.py -v
```

These tests validate the harness, input schema and circuit components. They are not Jolt verification tests. Successful circuit cases generate witnesses and explicitly run `snarkjs wtns check`; witness generation alone does not count as success.

For upstream source-patcher tests and the pending two-proof generation workflow, see [fixture tooling](tools/fixtures/README.md). `tools/scalar_inputs.py` maps its indexed scalar witness format to the scalar generator's named inputs, with strict field/schema validation and an explicit scalar-only acknowledgement.

## Completion checks

- Generate at least two genuine proofs for the same program/configuration and validate them with the complete native Jolt verifier.
- Export all data needed for both scalar and polynomial-commitment verification.
- Constrain the exact transcript, sumchecks, stage-8 claim assembly and Dory verification in Circom.
- Bind the approved program/configuration and application statement.
- Accept both genuine proofs in the same circuit, without regenerating witness-dependent constants.
- Reject modified statements, proof messages, commitments and PCS claims.
- Check generated witnesses against the R1CS.

A host-side verification result, an unchecked witness hint or a stages-1-to-7-only circuit does not satisfy these checks.
