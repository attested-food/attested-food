# Eurekha Labs mock reports

Mock lab reports (fictional lab "Eurekha Labs") for the EthGlobal Mumbai 2026 project, plus a byte-level redaction that hides the customer fields with a minimal, mechanically checkable diff. Reference layout: `kelloggs_choco_millet_muesli_EQNX_001_NL_26_10_09217.pdf` (real Equinox report).

## Layout

- `template/eurekha-report.typ`: Typst template, data from `--input data=/data/<id>.json`
- `data/*.json`: one report each; `customer` = PII, `s3.key` = object key (random suffix)
- `scripts/pdf.mjs`: minimal PDF reader (classic xref, streams, page tree, ToUnicode, text ops), Node built-ins only
- `scripts/normalize.mjs`: Typst PDF -> raw PDF (lab side)
- `scripts/redact.mjs`: raw PDF -> redacted PDF + manifest (holder side)
- `scripts/check.mjs`: guest predicate + verifier policy, reference for the zkVM guest
- `scripts/build.mjs`: compile + normalize + redact + check every report into `out/`
- `scripts/optimize.mjs`: raw PDF -> prover-friendly raw PDF (same text runs, same rendering)
- `scripts/build-opt.mjs`: prover-friendly variants into `out/opt/` (originals untouched)
- `scripts/upload.sh`: put `out/raw/*.pdf` to `s3://eurekhalabs/<key>`, creates the bucket if missing

## Run

```sh
node scripts/build.mjs            # needs typst 0.14; first run downloads @preview/tiaoma (QR)
scripts/upload.sh                 # AWS_PROFILE honoured
node scripts/redact.mjs out/raw/<id>.pdf /tmp/r.pdf --expect data/<id>.json
node scripts/check.mjs out/raw/<id>.pdf /tmp/r.pdf /tmp/r.manifest.json
```

Builds are deterministic (fixed creation timestamp, bundled fonts only).

## Template rules

- Customer fields (name, address, contact) set in `DejaVu Sans Mono`, nothing else uses it: the PII font
- Each PII line: own text run, kerning and ligatures off, `box` (no wrap), padded with U+00A0 to `PII_WIDTH` chars, max `PII_LINES` lines: run length hides value length
- Allowed chars `PII_CHARSET`, asserted at compile time
- Invisible charset run (white, 1pt) placed before any PII: fixes PII font subset, glyph numbering and ToUnicode, byte-identical across customers (checked)
- QR = public S3 URL of the original

## Raw PDF (normalize)

- Page content streams uncompressed
- Every text string rewritten as hex: 2-byte glyph id = 4 hex digits at a fixed offset
- Everything else byte-identical to Typst output, xref rebuilt
- This raw file is what S3 serves and what zkTLS attests

## Redaction

- Hex digits of every PII-font string -> `0`: glyph 0 (.notdef), same advance in a monospace font, so layout is unchanged; renders as boxes
- Same length, no offset moves; ~400 of ~90 KB bytes change (~0.45%)
- Manifest: `spans` ([start, end) of each PII hex string), sha256 + length of both files

## What the proof checks

Guest (private original, public: redacted hash, spans):
- `sha256(original || blinder)` = attested commitment (existing equinox-core check)
- equal length
- every differing byte lies in a span and is `0` in the redacted file
- commit `sha256(redacted)` and the spans

Verifier (public redacted PDF, outside the proof):
- hash matches
- each span = interior of a hex string shown by Tj/TJ in a page content stream under the PII font (`/^[A-Z]{6}\+DejaVuSansMono$/`), Type0 Identity-H
- each span all `0`

Since non-span bytes are identical, the redacted file's structure is the original's, so the verifier policy holds for the original too. Rejected (tested): zeroing a result glyph, claiming a non-PII string as a span, swapping a PII glyph for another, partial blanking, touching the xref.

## Prover-friendly variants

`node scripts/build-opt.mjs` (after `build.mjs`), for the zkVM guest (cost scales with bytes and content tokens):
- `out/opt/template/`: template with `--input opt=1`: QR as raster Image XObject (sized like the vector one), no kerning, no bold face
- `out/opt/full/`: template + `optimize.mjs`: one BT per page with Td moves, Tf / colour only on change, Tj, `q cm ... Q` table strokes flattened into one group, numbers rounded (coords 2 dp, colours 3 dp), ICC -> Device colour spaces, no XMP, no /ProcSet, unreachable objects dropped
- Checked per file: text-show runs (trimmed) equal the original's, redact + check pass; pixel diff vs `template` only anti-aliasing plus one 0.4pt border shifted 1 px
- Not S3-uploaded; choco: 90,718 B -> 69,426 B (template) -> 49,577 B (full), content ops 4,123 -> 686
- ToUnicode CMaps are already uncompressed in Typst output; remaining Flate streams: 2 font files, 2 CIDSets, QR image + SMask

## Known leaks / limits

- QR in the redacted copy still points to the unredacted original (accepted for the demo)
- Body length public (Content-Length); independent of PII here
- QR caption ("Download Report") lands on page 2 when the QR is at the bottom of page 1 (multigrain, peanut)
- Reader only handles Typst-shaped PDFs: classic xref, no object streams, no incremental updates
- The backend (`../backend`, equinox-core) parses Equinox/Skia reports; Eurekha reports need their own extraction rules there
