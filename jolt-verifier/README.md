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

## Test harness

With the already installed Circom, Node and snarkjs:

```bash
python3 -m unittest discover -s jolt-verifier/tests -p test_circom_runner.py -v
```

These tests validate the harness using a multiplication circuit. They are not Jolt verification tests. The harness compiles circuits, generates witnesses and explicitly runs `snarkjs wtns check`; witness generation alone does not count as success.

## Completion checks

- Generate at least two genuine proofs for the same program/configuration and validate them with the complete native Jolt verifier.
- Export all data needed for both scalar and polynomial-commitment verification.
- Constrain the exact transcript, sumchecks, stage-8 claim assembly and Dory verification in Circom.
- Bind the approved program/configuration and application statement.
- Accept both genuine proofs in the same circuit, without regenerating witness-dependent constants.
- Reject modified statements, proof messages, commitments and PCS claims.
- Check generated witnesses against the R1CS.

A host-side verification result, an unchecked witness hint or a stages-1-to-7-only circuit does not satisfy these checks.
