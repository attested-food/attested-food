# Genuine fixture status

No genuine Jolt proof fixtures have been generated or checked by this lane yet.
No full Circom verification result is claimed.

Source-only fixture tooling lives in `../tools/fixtures/`. Native verification,
scalar AST export and PCS export remain uncompiled. The exporter is not a
replacement for circuit PCS verification.

## Pinned protocol

- Jolt commit: `ad03c835f5f7e152b625543c488eec446e3206c0`.
- Non-ZK Fibonacci, BN254, `transcript-poseidon`, default Dory PCS.
- `dory-pcs` 0.3.0, crates.io SHA-256:
  `b8c58baea9f0ed973489cd1981b0e6a8c91aafddb05e3903b1dd54175ddcb52d`.
- Workspace replaces arkworks 0.5 crates with the pinned lockfile's
  `a16z/arkworks-algebra` git source. Keep the existing lockfile unchanged.

## Verification so far

On disposable VM `ubuntu-24.04-jolt-cached-e71ea395`:

- Six source-patcher tests passed against pristine pinned source.
- Patcher applied to `/home/admin/jolt-circom-source`.
- Installed `RUSTUP_TOOLCHAIN=1.95` rustfmt parsed and formatted all four
  patched Rust files successfully.
- `cargo check --offline --locked -p transpiler --bin transpiler
  --features transcript-poseidon` stopped at dependency resolution:
  `no matching package named ark-bn254 found`, crates.io index,
  required by `dory-pcs v0.3.0`.
- This is the first observed missing dependency, not an exhaustive list.
  No native compilation errors can be reported before resolution succeeds.
- An initial attempt with `+1.95.0` accidentally triggered rustup synchronization
  and began a component download. It was cancelled. Subsequent commands used
  the already installed `RUSTUP_TOOLCHAIN=1.95`, with Cargo offline and locked.

No proof generation, native proof verification, tamper rejection, witness
satisfaction, fixed-shape pair acceptance or full circuit verification has run.
Dependency fetching still requires coordinator/user approval.
