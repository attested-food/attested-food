# Genuine website Jolt fixtures

Two native-generated, browser-format proofs of the exact website Equinox guest:
`tier21-abc` and `tier21-def`. Both start from the standard SHA-256 IV encoded
as eight little-endian u32 words, with total length 3 and the indicated ASCII
message. The input is public test data, not a report or a TLSNotary secret.

Both full native verifications succeeded. Separately changing the Akita PCS
backend proof, public input or public output was rejected by the native full
verifier. Diagnostics are in each manifest and `provenance/tier21-*.log`.

| Fixture | Cycles | Padded cycles | Proof bytes | Expected output |
|---|---:|---:|---:|---|
| abc | 5084 | 8192 | 83017 | `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad` |
| def | 5084 | 8192 | 82972 | `cb8379ac2098aa165029e3938a51da0bcecfc008fd6795f401178647f96c5b34` |

The verifier preprocessing is byte-identical between the two fixtures.
`pair-validation.json` records the common protocol, trace, RAM, read/write,
one-hot and polynomial-order configuration. Both proofs were generated a
second time and the raw proof bytes matched the earlier corrected runs.

## Exact target and provenance

`website-match.json` records direct SHA-256 comparisons with the active
website assets and comparisons of all ten guest/core Rust source files with
`website-target.json`. Three shipped artifacts match exactly: the guest ELF,
program preprocessing and Akita schedules. No new guest was substituted.

- Browser fork: `6d3bdeb4e3f42f1480f50220f546d64e9adb0058` plus local patches.
- Jolt: `d39bd518a65ea89401de63c3343e98fbad5f1b80` plus browser patches.
- Akita: `252abb895046cc1d5b9955a26a2ad2318148ac26` plus browser patches.
- Solinas field: `2^128 - 2^32 + 22537`; packed, transparent Akita PCS.
- Spongefish: 0.7.4. Exact dependencies are in `provenance/Cargo.lock`.

`provenance/build.json` records source fingerprints, repository bases,
installed guest/core sources, binary hash, tool versions and build flags.
Tracked changes are preserved as patches, additional source as tar archives,
and the exact native engine and driver are copied alongside the build log.
These are source data, not instructions to execute on the host.

Generation and third-party compilation ran only inside disposable Tart clone
`ubuntu-24.04-jolt-cached-e71ea395`. No private report or user secret was used.

## Artifact schema

Each directory contains:

- `manifest.json`: `website-jolt-akita-fixture-v1`, observed native outcomes,
  timing/cycle counts, target asset hashes and canonical artifact hashes.
- `proof.bin`, `program-io.bin`, `verifier-preprocessing.bin`: exact bytes from
  the website's shared engine, using bincode 2 serde standard configuration.
- `input.bin`: postcard encodings of tier u8, ByteBuf and empty chosen vector,
  concatenated as the browser does. `segment-input.bin` is the ByteBuf payload.
- `outputs-postcard.bin`: exact padded guest output region. `outputs.bin` is
  the 32-byte return value after its postcard Vec length prefix is stripped.
- `proof.json`, `program-io.json`: original serde views of the native objects.
  `verifier-preprocessing.json.gz` is the full serde setup view, gzip-compressed
  to avoid checking in two identical 58 MB JSON files.
- `pcs-backend.bin`, `pcs-schedule-selection.bin`: exact byte arrays extracted
  from `proof.json`'s `joint_opening_proof`, checked against it by the validator.
- `pcs-decoded.txt`: Rust Debug rendering of the actual decoded Akita backend
  proof at native verification. `pcs-boundary.txt` contains the actual backend
  opening point, evaluations and commitment. These are diagnostic structured
  text, not a normalized circuit witness schema.
- `akita-transcript.tsv`: actual nested Akita verifier transcript operations,
  one `operation<TAB>hex-bytes` per line, in order. Repeated session/instance
  binds are preserved. Captured only during the positive verification.
- `checksums.json`: size and SHA-256 of all packaged fixture files except itself.

## Explicit limits

These ran natively through the same engine used by the shipped browser bundle,
not inside a browser or on WebGPU. No Circom verification has run. The native
verifier preprocesses against the same shipped program and schedules; this
is not a substitute for pinning them in a deployed verifier.

Diagnostic capture is incomplete: no outer Jolt transcript log was produced.
The hook in `legacy.rs` was not on this target's live outer transcript path.
The nested Akita transcript, PCS bytes and decoded PCS proof were captured.
Scalar/PCS circuit lanes must derive and constrain their own transcript and
arithmetic. Native acceptance flags must never replace PCS verification.

Historical Dory artifacts under the neighbouring fixture/tool directories
are a separate, out-of-target experiment. No tier20, tier31 or tier33 fixture
is claimed by this pair.
