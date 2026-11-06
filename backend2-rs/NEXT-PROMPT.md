# Next session prompt: one OpenVM proof from S3 fetch (TLSNotary) to redacted Eurekha key-value pairs

Paste this as the task. Repo: `~/workspace/hackathons/ethglobal-mumbai-2026/attested-food-github-repo/backend2-rs` (branch `main`, commit per step, do not push unless asked).

## Goal

One OpenVM 2.1 STARK proving: notary-signed TLS session with the lab's S3 bucket → the served PDF → its redaction → every non-customer key-value pair. Public: bucket host, `sha256(object key)`, notary address, body commitment, `sha256(redacted PDF)` + spans, key-value pairs + result rows. Private: PDF, blinders, request path.

## Decisions (made by the user)

- Reveal bucket host + `sha256(key)`, NOT the full URL (key = password to the unredacted original).
- Output: all non-customer key-value pairs + result rows + redacted-PDF hash/spans.
- Verify the TLSNotary attestation inside the guest (one proof).
- Server-side prover: OpenVM (fastest native: 36.7 s full Equinox statement on M2 Max CPU, one run).

## Done so far

- `backend2-rs/`: `core/` (copy of backend equinox-core, rev in `core/UPSTREAM_REV`), `guest/` (OpenVM, format byte: 0 Equinox, 1 Eurekha), `server/` (axum, `POST /prove?mode=stark|execute`, multipart `pdf`, `format=equinox|eurekha`, `labels`, `blinder`; `/verify`, `/program`, `/health`; prove lock `/tmp/equinox-prove.lock.d`).
- `core/src/eurekha.rs`: spans = PII-font (`XXXXXX+DejaVuSansMono`) hex strings shown by Tj/TJ in uncompressed content; redacted = spans zeroed to `0`; commits `sha256(redacted)`; extracts kv (`Key : Value` runs, `Key`,`:`,`Value` grid, ULR, dates table, lab, accreditation, signatory) and result rows; dedups repeated page headers, panics on conflicts; asserts no customer line (decoded PII string) appears in any output.
- `core/tests/eurekha.rs`: spans + redacted hash match `mock-pdfs` manifests for all 3 reports; redacted bytes equal `out/redacted/*.pdf`.
- Measured: Eurekha STARK 42.4 s end to end (prove 36.3 s, 2,305,288 instructions, proof 534,601 B), verified, tamper rejected; Equinox 1,672,873 instructions.
- Commits: `2a93eba`, `7966de8`, `055034a`, `a4ad157`.

## Steps

1. [done] STARK-prove Eurekha now (no TLS yet): `curl -X POST 'localhost:8793/prove?mode=stark' -F format=eurekha -F pdf=@../../mock-pdfs/out/raw/choco-millet-muesli.pdf`. Record keygen/prove/verify/proof size in README. Optimize if needed: guest hashes original AND redacted (two 90 KB SHAs), and copies the PDF.
2. [done, `22d3166` + next commit] TLS binding in core (copy, do not edit `../backend`):
   - Port into `core/src/tlsn.rs`: host list instead of const `SERVER_NAME` (accept `eurekhalabs.s3.amazonaws.com` and its regional form), expose matched host.
   - Add path opening: `OnchainTlsn` += `path_index: u32`, `path_preimage: Vec<u8>` (53 B, `0x00|0x00 Sent|0x01|4u64LE|path_end u64LE|0x01|0x20|hash32`, leaf = `SHA256(DOMAIN_TRANSCRIPT_COMMITMENT || preimage)`, domain `bd0ab9ac6ea93ebda2500e8769e63a9e`). Guest private: path bytes + path blinder; check `SHA256(path || blinder) == hash`, range length == path len; output `sha256(key)` (key = path without leading `/`). Verify the preimage layout against a real attestation before trusting it.
   - Guest format 2 = Eurekha attested: `tlsn::check` (k256 `K256Recover`, keccak header sig, Merkle root, server-name leaf, body leaf) → `eurekha::run` → bind (`body_commitment` == attested hash, `pdf_len` == range len) → path opening. Pin the notary: commit its address in the public values.
3. [done: zktls copy, proxy session on choco-millet-muesli; objects were already public on eurekhalabs, no upload needed] Produce a real attestation of an S3 object:
   - Upload: `mock-pdfs/scripts/upload.sh` → `s3://eurekhalabs/<key>` (check if already uploaded; needs AWS creds, `aws` skill; ask before creating buckets).
   - TLSNotary: backend `zktls` hard-codes the Equinox host (~20 places: `tlsn.rs:35`, `proxy.rs:14,20,36`, `notary.rs:108,154`, `policy.rs:161`, `presentation.rs`, `browser.rs`, server `api.rs`, web, contract). Options: copy `zktls` into backend2-rs with a host list (preferred, no conflict with backend lanes), or a backend branch. Also capture the path blinder: server prover keeps it in `secrets.bin` (`prover.rs:143`); export must add the path leaf (`onchain.rs:100-118` analogue, direction Sent, start 4).
   - Run `equinox-tls-prove --url-file <f> --out-dir <d> --mode proxy|mpc` (MPC ~60 s, ~22 GB; take the prove lock), then `export-onchain`.
4. [done: `eurekha-attested` = format 2, signature left to the verifier, 42.5 s; `eurekha-attested-sig` = format 3, in-guest k256, 95.8 s] Server: `format=eurekha-attested` taking `presentation.bin` (or `onchain.json` + `secrets.bin`) + PDF; returns proof, public values, redacted PDF.
5. [done in core/tests/tlsn_eurekha.rs] Tests: tamper cases rejected (flipped result glyph, wrong host, wrong path blinder, swapped attestation, non-PII span); keep `core/tests/eurekha.rs` green.
6. Later: EVM path (`openvm-sdk` feature `evm-prove`, KZG params in `~/.openvm/params`, Halo2 verifier). Known blocker from the GPU box: an earlier OpenVM verifier wrapper was ~100 KB, over EIP-170. GPU: `openvm-sdk` feature `cuda` on the g6e box (`i-078bdddab89a51802`, 13.232.15.45, powers off 2026-11-07 09:18 UTC); SP1 there: 5.8 s prove on L40S.

## Constraints

- Never commit or copy report PDFs into VMs/remote boxes casually: they hold customer PII (`*.pdf` gitignored).
- Heavy proofs/TLS sessions: take `/tmp/equinox-prove.lock.d`; another session runs SP1 benches on this Mac.
- Untrusted repos: build in tart VM `ubuntu-24.04-zkvm-webgpu-build` (default disk mode, never `sync=none`).
- Known leaks to keep documented: QR on the redacted PDF points to the original; body length public; path length public via transcript offsets.
