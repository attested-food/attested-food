# backend2-rs

Rust server that takes an Equinox lab-report PDF and returns an OpenVM 2.1 STARK proof of the chosen test values: report number, product, ULR, issue date, the analyte rows, and the commitment `SHA256(pdf || blinder)`, with a check that no customer-block word is published.

- `core/`: `equinox-core`, the `no_std` PDF logic (xref walk, our own DEFLATE, glyph decoding, row extraction, SHA-256, public-values layout). Copied from the Equinox backend, revision in `core/UPSTREAM_REV`.
- `guest/`: the OpenVM guest, a thin wrapper over `equinox_core::run`, and `openvm.toml` (RV32IM, IO, SHA-2 extension). It reveals `sha256(PublicValues::encode())`, since OpenVM user public values are a fixed 32 bytes.
- `zktls/`: TLSNotary server-side prover and in-process notary (copied from the Equinox backend, browser protocol left out), own workspace. `equinox-tls-prove` fetches an allowlisted S3 report URL (Equinox or `eurekhalabs`) and writes `body.pdf`, `blinder.hex`, `onchain.json` (public leaves, incl. the request leaves) and `request.json` (private: the request, whose path is the object key, and its blinders) to `--out-dir`.
- `server/`: `equinox-openvm-server` (axum). `build.rs` compiles the guest; one thread owns the OpenVM SDK and serves prove and verify jobs.

## Build and run

```sh
rustup toolchain install nightly-2026-08-23 --component rust-src   # guest toolchain, pinned for a reproducible program commitment
cargo build --release
./target/release/equinox-openvm-server                            # http://127.0.0.1:8793 (BIND to change)
```

`OPENVM_SKIP_BUILD=1` builds the server without the guest (`/health` then reports it). A STARK proof takes the machine-wide lock `/tmp/equinox-prove.lock.d` shared with the Equinox backend, so heavy proofs never overlap on one host.

## API

Proving is a job: `POST /prove` answers `202 { jobId, statusUrl }` once the native preflight passes (a bad PDF, attestation or PII leak is still an immediate 400), and the caller polls `GET /jobs/{id}`. `&wait=1` holds the request and answers with the result instead.

```sh
J=$(curl -s -X POST 'localhost:8793/prove?mode=sp1-groth16' -F format=eurekha-attested \
  -F pdf=@body.pdf -F blinder=$(cat blinder.hex) -F onchain=@onchain.json -F request=@request.json)
curl -s localhost:8793/jobs/$(echo $J | jq -r .jobId)
```

| Route | In | Out |
|---|---|---|
| `GET /health` | | `{ ok, guestElfBytes, sp1 }` (`sp1`: the warm worker's setup and warm-up status) |
| `GET /program` | | `{ appExeCommit, appVmCommit }`, the pinned OpenVM program |
| `POST /prove?mode=...` | multipart `pdf`, `format` (`equinox`, `eurekha`, `eurekha-attested`, `eurekha-attested-sig`), `labels` (Equinox), `blinder` (16 bytes hex; random if absent, required for attested formats), `onchain` + `request` (attested formats: `onchain.json`, `request.json` of a `zktls` run) | `202 { jobId, status, statusUrl }` |
| `GET /jobs/{id}` | | `{ status: queued\|running\|done\|failed, stage, stages: [{ name, ms \| elapsedMs }], elapsedMs, progress: { fraction, etaMs }, preview: { publicValues, publicValuesHex }, partial, result, error }` |
| `POST /verify` | JSON `{ proof, publicValues }` | `{ valid, publicValues, program }`, or 400 (OpenVM STARKs) |

Modes (default `sp1-groth16`): `stark` (OpenVM STARK, `proof` base64 bincode `VersionedVmStarkProof`), `sp1-groth16` (`format=eurekha-attested`: `artifact { vkey, publicValues, proof, notarySignature }`, the arguments of `EurekhaReportRegistry.submit`), `openvm-halo2` (reserved, 501). `result` is `{ mode, format, publicValues, publicValuesHex, notarySignature, redactedPdf, revealed, instructions, program, proof, proofBytes, artifact, timingsMs }`.

Stages: `queued`, `starting sp1 worker`, `waiting for prove lock`, `execute`, `keygen`, `prove`, `verify` (OpenVM); `prove stark`, `verify stark`, `prove groth16`, `verify groth16` (SP1).

`sp1-groth16` returns two proofs. The compressed SP1 STARK appears under `partial["sp1-compressed"]` (`proof`: base64 bincode `SP1ProofWithPublicValues`, verifiable off-chain with sp1-sdk) as soon as it is verified, while the Groth16 proof for the contract is still being made; the job's `result.artifact` holds the Groth16 proof at the end. The SDK cannot wrap an existing compressed proof, so the Groth16 request proves core + compress again: seconds on the GPU, minutes on a CPU. `progress` is an estimate, since neither SDK reports a fraction done: working time so far over the working time of the last finished job of the same mode (queue and lock waits excluded); `null` until one has finished. Jobs live in memory for an hour after they finish. Responses never include the body blinder: with it, the public `body_commitment` and the redacted PDF, anyone could test guesses of the redacted customer fields offline.

Both provers stay warm: OpenVM keygen runs at start and its keys stay in the prover thread; SP1 runs as one long-lived `eurekha-sp1 serve` child that sets up at start and, with `EUREKHA_SP1_WARM_RUN=<zktls run dir>`, proves once so gnark's Groth16 proving key is loaded before the first request. Proofs take the machine-wide lock: `/tmp/equinox-prove.lock.d`, or `PROVE_FLOCK=<file>` (an `flock`, as the GPU box's `heavy` uses).

Before proving, the server runs the same extraction natively: a PDF the guest would reject fails in milliseconds, and a result that would publish PII is refused. `/prove` checks the guest revealed `sha256(publicValues)` and verifies the proof before returning it. `/verify` checks the proof against the pinned program and that it commits to the given public values (a flipped public-value byte is rejected).

## Measured

This Mac (M2 Max, 12 cores, 96 GB), the sample report (393,722 B), CPU prover, one run each:

| Step | Time |
|---|---|
| execute (1,654,284 instructions) | 2.0 s |
| app + aggregation keygen (first STARK only) | 3.1 s |
| prove (app segments + STARK aggregation) | 31.6 s |
| verify | 17 ms |
| `/prove?mode=stark` end to end | 36.7 s |

Proof 534,601 B.

Eurekha report (`format=eurekha`, `mock-pdfs/out/raw/choco-millet-muesli.pdf`, 90,718 B), same machine, one run:

| Step | Time |
|---|---|
| execute (2,305,288 instructions) | 2.4 s |
| app + aggregation keygen (first STARK only) | 3.6 s |
| prove | 36.3 s |
| verify | 21 ms |
| `/prove?mode=stark` end to end | 42.4 s |

Proof 534,601 B (aggregation output, independent of the guest run). Public values: 5 redaction spans, `redacted_sha256 0f3af67c...e426cc` (matches the `mock-pdfs` manifest), 22 key-value pairs, 11 result rows. `/verify` accepts it and rejects a one-byte change to the public values.

Program (format-dispatch guest): `appExeCommit 0097bec6...3b3fee`, `appVmCommit 00773b10...ba0f93` (pinned by the guest toolchain and source).

## Eurekha with its TLSNotary attestation

One proof from the S3 fetch to the redacted values:

```sh
cd zktls && cargo build --release
echo https://eurekhalabs.s3.amazonaws.com/reports/2026/<object>.pdf > runs/x/url.txt
./target/release/equinox-tls-prove --url-file runs/x/url.txt --out-dir runs/x/proxy --mode proxy   # MPC: --mode mpc
R=runs/x/proxy; curl -X POST 'localhost:8793/prove?mode=stark' -F format=eurekha-attested \
  -F pdf=@$R/body.pdf -F blinder=$(cat $R/blinder.hex) -F onchain=@$R/onchain.json -F request=@$R/request.json
```

The guest checks every attestation leaf against the header's Merkle root, the notary-signed server name (one of the allowed buckets), and the body commitment `SHA256(pdf || blinder)` and its length. It then opens the three request commitments (`GET `, path, rest) and the `ConnectionInfo` leaf privately: one `Host` header naming the attested bucket, both transcript lengths, and a path of `/` + key. It runs the Eurekha redaction and extraction and commits `EurekhaAttested`: signer, bucket host, TLS session time, `sha256(object key)` (never the key: it is the link to the unredacted original), and the Eurekha values.

Two variants:

- `eurekha-attested` (format 2): the guest does not check the notary signature. It commits the 54-byte attestation header, and the verifier checks `ecrecover(keccak256(header), notarySignature)` against the notary it trusts (3,000 gas on-chain). The response carries `notarySignature`. The server still checks the signature before proving, so it never proves a forged attestation.
- `eurekha-attested-sig` (format 3): the guest recovers the notary with `k256` + `sha3` in software and commits its address.

Measured on the same Mac, `choco-millet-muesli` (90,718 B), real proxy-mode session with the dev notary (16 s), one run each:

| Format | Instructions | Prove | `/prove` end to end |
|---|---|---|---|
| `eurekha` (no TLS) | 2,305,288 | 36.3 s | 42.4 s |
| `eurekha-attested` | 2,350,321 | 33.9 s | 42.5 s (incl. 5.4 s first keygen) |
| `eurekha-attested-sig` | 11,506,702 | 93.8 s | 95.8 s |

All TLS checks other than the signature add 45k instructions. The signature adds 9.2M, so it is left to the verifier by default. OpenVM's secp256k1 extension (the `k256` fork in `guest-libs/k256`, a git dependency) would shrink format 3 but was not tried. The proof is 534,601 B for every format. `core/tests/tlsn_eurekha.rs` runs both statements on the saved session and rejects a wrong notary, an edited PDF or blinder, another object key, a wrong path blinder, reordered or substituted leaves, a forged `ConnectionInfo` and another host's server-name leaf. The server rejects a forged signature (`BadNotarySignature`) and a wrong body blinder (`BodyMismatch`).

Program (formats 0 to 3): `appExeCommit 00290706...245687`, `appVmCommit 00773b10...ba0f93`.

## On-chain verification

The STARK itself is not verified on-chain. OpenVM ships no Solidity STARK verifier, and the 534,601-byte proof would cost up to about 8.6M gas in calldata alone (16 gas per non-zero byte, 4 per zero byte) before any verification work.

OpenVM's route is `Sdk::prove_evm` (`openvm-sdk` feature `evm-prove`): it wraps the aggregated STARK in a Halo2/KZG proof on BN254, and `Sdk::generate_halo2_verifier_solidity` emits `OpenVmHalo2Verifier.sol` with `verify(bytes publicValues, bytes proofData, bytes32 appExeCommit, bytes32 appVmCommit)`. Here `publicValues` is the 32-byte digest the guest reveals and the two commits are `/program`'s. What it needs that this server does not have yet:

- KZG SRS files `kzg_bn254_{k}.srs` in `~/.openvm/params` (`cargo openvm setup` downloads them).
- A one-time Halo2 proving-key keygen, which OpenVM documents as memory and compute heavy.
- `solc` to compile the generated verifier.

Gas for `verify` has not been measured here.
