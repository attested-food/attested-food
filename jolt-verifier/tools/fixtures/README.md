# Jolt fixture exporter

Source-only tooling for pinned historical Jolt. See `../../fixtures/STATUS.md`
for observed results and limits. Run upstream code only inside an approved
throwaway VM. These scripts install nothing. Do not fetch dependencies before
approval.

## Prepare and test

Copy this directory into the VM. `UPSTREAM` must be a pristine checkout of
`ad03c835f5f7e152b625543c488eec446e3206c0`.

```sh
python3 /home/admin/jolt-fixture-tools/test_prepare_upstream.py --upstream "$UPSTREAM" -v
python3 /home/admin/jolt-fixture-tools/prepare_upstream.py "$UPSTREAM"
```

The patcher checks HEAD and exact source hashes before writing anything. It
rejects changed source, existing exporter modules and repeated application.
Run tests before applying the patch, because they require pristine source.

Changes to upstream source:

- Parameterize Fibonacci's proving, tracing and verifying calls with
  `JOLT_FIXTURE_FIB_N` (upstream ignores the positional argument).
- Require native SDK verification to return true.
- Run the full native verifier again before exporting.
- Require native rejection after separately changing a PCS message, scalar
  opening claim and public input.
- Capture actual stage-8 inputs immediately before native PCS verification.
- Export scalar witness values for the `ast-bundle` target, keyed by AST ID.
- Export all non-ZK Dory messages and the full verifier setup.

## Generate, only after dependencies are available

These commands have not completed here. Run from `$UPSTREAM` in the VM using
an already installed toolchain. Do not run two Fibonacci jobs concurrently:
upstream writes fixed paths in `/tmp`.

```sh
export RUSTUP_TOOLCHAIN=1.95
export JOLT_FIXTURE_FIB_N=50
cargo run --offline --locked -p fibonacci --release --features transcript-poseidon -- --save
cargo run --offline --locked -p transpiler --bin transpiler --release --features transcript-poseidon -- \
  --proof /tmp/fib_proof.bin --io-device /tmp/fib_io_device.bin \
  --preprocessing /tmp/jolt_verifier_preprocessing.dat -t ast-bundle -o /home/admin/fixtures/fib-50

export JOLT_FIXTURE_FIB_N=51
cargo run --offline --locked -p fibonacci --release --features transcript-poseidon -- --save
cargo run --offline --locked -p transpiler --bin transpiler --release --features transcript-poseidon -- \
  --proof /tmp/fib_proof.bin --io-device /tmp/fib_io_device.bin \
  --preprocessing /tmp/jolt_verifier_preprocessing.dat -t ast-bundle -o /home/admin/fixtures/fib-51
python3 /home/admin/jolt-fixture-tools/check_pair.py /home/admin/fixtures/fib-50 /home/admin/fixtures/fib-51
```

Inputs 50 and 51 are candidates, not an observed fixed-shape pair. If trace,
configuration, preprocessing or scalar AST differs, the pair checker rejects
it. Select a different pair rather than weakening its checks. Each output
directory must be fresh. Preserve logs and toolchain versions with real runs.

## Artifact schema

`full-proof.json`, schema `jolt-dory-fixture-v1`:

- Protocol pin, native check results, explicit absence of circuit verification.
- Trace length, RAM size, canonical read/write and one-hot configuration,
  Dory layout, number of commitments, `nu` and `sigma`.
- Public input/output bytes and panic flag.
- All GT commitments and scalar opening claims keyed by canonical opening ID.
- Full joint opening proof: VMV message, first and second reduce messages,
  final scalar-product message, dimensions and canonical proof bytes.
- Full verifier setup: all four delta vectors, chi, first generators,
  blinding generators, pairing, supported size and canonical bytes.
- Native PCS boundary: opening point in Jolt variable order, scalar claim,
  joint commitment, Poseidon state and counter before Dory consumes messages.
- BN254 base and scalar field moduli.

All field values are canonical decimal strings. GT/Fq12 arrays have index
order `[c0/c1][c0/c1/c2][c0/c1]`. G1 and G2 use projective `x`, `y`, `z`;
G2 coordinates are Fq2 arrays `[c0, c1]`. These are not affine coordinates.
The circuit must enforce appropriate curve, subgroup, normalization and field
relations. Dory uses reversed variable order from Jolt. Dory 0.3 permits
`nu <= sigma` and uses `sigma` reduce rounds.

The Dory dependency has its ZK feature enabled by the workspace, even when
Jolt runs non-ZK. The exporter requires every optional ZK proof component to
be absent. Trusted and untrusted advice are unsupported by this exporter.

Other artifacts:

- `proof.bin`, `io_device.bin`, `preprocessing.bin`: original canonical inputs.
- `native-pcs-boundary/*.bin`: captured native boundary in canonical encoding;
  transcript is 32 state bytes followed by a little-endian u32 counter.
- `stages_bundle.json`: upstream scalar AST for stages 1 through 7 only.
- `scalar-witness.json`: decimal values keyed by variable ID, with original
  name and target field. Missing values abort export.

`check_pair.py` checks export consistency only. Native-check booleans are
provenance records, never circuit inputs that stand in for cryptographic
verification. The scalar AST omits PCS. The circuit must independently bind
its derived transcript, claims and joint commitment to PCS and verify Dory,
including the terminal pairing relation. Nothing here claims it does so.
