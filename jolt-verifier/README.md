# Jolt verifier

Work in progress: genuine Jolt proof fixtures and a complete Circom verifier for a pinned protocol. This directory is not an onchain-ready wrapper.

## Active target: the website `/prove` page

Only the website's in-browser Jolt mode is in scope. Its implementation was found on the separate `jolt-webgpu-prove` worktree at page revision `7335214`, not the SP1-only page on the original `main` checkout.

- Prover fork: `0xAndoroid/jolt-wasm-prover`, revision `6d3bdeb4e3f42f1480f50220f546d64e9adb0058`, with the website guest/build patch.
- Build source: `webgpu-zkvm-poc`, revision `c5d5b16c1fe55328b6148d16a56e44e272160fc1`.
- Protocol: Jolt/Akita over the Solinas field `p = 2^128 - 2^32 + 22537`, with the fork's exact transcript and trimmed schedule catalogs.
- Guest: `equinox`, with the compiled website program and its IO/memory configuration, at most `2^21` padded cycles.
- Supported tier IDs: `20` SHA chunk, `21` SHA finish, `31` Eurekha extraction, `33` TLS attestation segment.

[website-target.json](website-target.json) records SHA-256 hashes of the committed page sources, guest/build sources and local prover assets, including the ELF, program preprocessing, schedule catalog and wasm. It is an inventory, not evidence that the binary was rebuilt from those sources or that any proof was verified. Those checks remain explicit in its verification fields.

The target is the individual Jolt segment proof and its approved guest/statement. Browser-side reassembly and equality checks are not themselves proof constraints and must not be mistaken for an aggregate report proof.

## Historical prototype (not the active target)

The initial tools under `tools/fixtures`, `tools/circuits` and the top-level scalar/Poseidon Circom files target historical Jolt `ad03c835f5f7e152b625543c488eec446e3206c0`, BN254 Fr, Poseidon and Dory 0.3.0. They remain separate component experiments. Their stages 1 to 7 export does not verify PCS and cannot verify the website's Akita proofs.

## Layout

- `fixtures/browser/`, `tools/browser-fixtures/`: website-compatible proof fixtures and native generation/verification tooling.
- `circuits/browser/`, `tools/browser-circuits/`: canonical Fp128 arithmetic, Blake2b and raw outer Jolt digest-step components.
- `circuits/browser-statement/`, `tools/browser-statement/`: constrained website postcard IO framing.
- `website-target.json`, `tools/pin_website.py`: source and asset inventory.
- `tests/`: circuit compilation, witness generation, R1CS checks and integration tests.
- `tools/fixtures/`, `tools/circuits/`, top-level scalar/Poseidon circuits: historical Dory prototype, not the website verifier.

## Verified status (2026-11-07)

- 28 harness, source-inventory, website IO codec and historical scalar-input schema tests passed.
- 22 website Fp128, Blake2b and outer digest-step circuit tests passed, with no skips.
- 7 website IO framing circuit tests passed, with no skips, including tier, length, empty-label and byte-range checks.
- 18 historical scalar-generator, transcript and Poseidon component tests passed, with no skips.
- 6 historical upstream source-patcher tests passed inside the disposable Linux VM.
- The website's committed source and local asset inventory has been recorded; source-to-asset rebuild matching is not yet checked.

**No genuine website Jolt fixtures or complete Akita Circom verifier have been validated yet.** Component tests and source inventories do not establish full Jolt proof validity.

Building and required dependency downloads inside the disposable VM were authorized on 2026-11-07. The previous Dory build/dependency problem and proposed pairing-library license conflict are not blockers for the new Akita target. No external pairing code was vendored or executed.

## Component tests

With the already installed Circom, Node and snarkjs, run from the project root:

```bash
python3 -m unittest discover -s jolt-verifier/tests -v
python3 -m unittest discover -s jolt-verifier/tools/browser-circuits -p 'test_*.py' -v
python3 -m unittest discover -s jolt-verifier/tools/browser-statement -p 'test_*.py' -v
python3 -m unittest discover -s jolt-verifier/tools/circuits -p test_ast_to_circom.py -v
```

These tests validate the harness, input schema and circuit components. They are not Jolt verification tests. Successful circuit cases generate witnesses and explicitly run `snarkjs wtns check`; witness generation alone does not count as success.

`tools/website_statement.py` is a strict reference codec for the website guest's postcard input/output bytes, supported tiers, empty labels list and serialized IO bounds. `BrowserWebsiteStatement(TIER, INPUT_LENGTH, OUTPUT_LENGTH)` constrains the same encoding for a fixed shape. Its payload and result inputs must be public or bound to an application statement, and its serialized outputs must feed the complete Jolt verifier. It does not enforce guest execution, guest identity or proof validity by itself.

For historical upstream source-patcher tests, see [fixture tooling](tools/fixtures/README.md). `tools/scalar_inputs.py` maps that experiment's indexed scalar witness format to its scalar generator's named inputs, with strict field/schema validation and an explicit scalar-only acknowledgement.

## Completion checks

- Generate at least two genuine proofs for the same program/configuration and validate them with the complete native Jolt verifier.
- Export all data needed for both scalar and polynomial-commitment verification.
- Constrain the exact website transcript, Solinas-field sumchecks, stage-8 claim assembly and Akita verification in Circom.
- Bind the approved program/configuration and application statement.
- Accept both genuine proofs in the same circuit, without regenerating witness-dependent constants.
- Reject modified statements, proof messages, commitments and PCS claims.
- Check generated witnesses against the R1CS.

A host-side verification result, an unchecked witness hint or a stages-1-to-7-only circuit does not satisfy these checks.
