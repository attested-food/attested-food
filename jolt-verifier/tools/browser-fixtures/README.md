# Website Jolt fixture tools

Use only with the pinned browser fork and patches documented in
`../../fixtures/browser/README.md`. Upstream source must compile and execute
inside an approved disposable VM, never on the host. No installer is included.

The native driver is compiled inside the browser fork because it imports that
fork's exact `src/engine.rs`, the same implementation used by wasm exports.
Copy `export.rs` to `preprocessing/browser_fixture.rs` and register a binary
named `browser-fixture` at that path in the fork's Cargo.toml with required
feature `native`. Do not alter its existing dependency graph or lockfile.

`instrument.py /home/admin/jwp` adds passive native logging. It reads all three
source files before writing, requires unique source anchors and refuses a
second application. The nested Akita capture works; the outer legacy hook is
not the live outer transcript implementation for this target. That diagnostic
limit is intentional in this bounded fixture landing, not full witness coverage.

Inside the VM, with the source and build dependencies already prepared:

```sh
export RUSTUP_TOOLCHAIN=1.95
cargo build --locked --release --features native --bin browser-fixture -j 4
python3 /home/admin/browser-fixture-tools/make_inputs.py /home/admin/browser-inputs-corrected
RAYON_NUM_THREADS=4 ./target/release/browser-fixture frontend/public 21 \
  /home/admin/browser-inputs-corrected/tier21-abc.bin /home/admin/browser-fixtures/tier21-abc
RAYON_NUM_THREADS=4 ./target/release/browser-fixture frontend/public 21 \
  /home/admin/browser-inputs-corrected/tier21-def.bin /home/admin/browser-fixtures/tier21-def
python3 /home/admin/browser-fixture-tools/provenance.py /home/admin/jwp /home/admin/browser-fixtures/provenance
python3 /home/admin/browser-fixture-tools/package.py /home/admin/browser-fixtures/tier21-abc
python3 /home/admin/browser-fixture-tools/package.py /home/admin/browser-fixtures/tier21-def
```

Each proof output directory must be fresh. Packaging preserves all original
binary bytes, compresses the full preprocessing JSON with gzip mtime zero,
and extracts the raw backend proof and schedule-selection bytes. When pulling
results out of the VM, omit the uncompressed `verifier-preprocessing.json`.

Host-safe checks on the committed data, from this directory:

```sh
python3 validate_pair.py ../../fixtures/browser ../../website-target.json
PYTHONDONTWRITEBYTECODE=1 python3 test_fixtures.py -v
black --check .
rustfmt --edition 2021 --config skip_children=true --check export.rs
```

The validator independently checks standard SHA-256 outputs, little-endian IV
encoding, exact argument serialization, all recorded hashes, target asset
pins, required captured diagnostics, identical verifier preprocessing and
matching proof shapes. It is an artifact consistency check, not a cryptographic
verifier. Native verification and mutation rejection are executed by the driver.

`make_inputs.py` also contains public generators for future tiers, but only the
corrected tier21 pair has been generated and validated in this landing.
