# Verifying lab reports without lab cooperation

Findings from a spike on the Equinox Labs sample report (Kellogg's Choco Millet Muesli, see [idea.md](idea.md#example-report)). Tested Nov 2026.

**Constraint:** everything must work with what labs already publish. No lab, regulator or brand has to adopt a format, sign anything, or work with us.

## How Equinox delivers a report

- The PDF is rendered by headless Chrome. It has **no embedded digital signature**.
- The "Download Report" QR on the last page points to `titan.equinoxlab.com/report/with_letter_head/download/<encrypted id>`. That URL needs **no login** and answers with a `302` redirect to a **public S3 object** in the `equinox-labs-latest` bucket.
- The S3 object path contains the **customer's name**, then year, month, product and report number.
- The file behind the QR is byte-identical to the PDF the customer received (same SHA-256).
- The "NABL Scope" QR on every page points to a scope PDF in the same bucket.

### Privacy consequences

- The Download Report QR is a bearer link. Anyone who scans it from a shared copy gets the full report, including name and address. **It must be removed from anything we publish.**
- Report number and ULR, together with a guessed name, let someone rebuild the S3 URL. **Treat them as private**: prove them inside a proof, don't publish them. The "Public?" column in idea.md's example-report table needs revising for these fields.
- We did not probe the bucket beyond the one known file. Worth reporting the issue to Equinox.

## PDF structure (Equinox, 2 pages, 394 KB)

| Part | Contents | Personal details? |
|---|---|---|
| Page 1 content stream (one Flate stream, ~6 KB compressed / 30 KB decoded) | Customer block (client name, address, contact person), sample details, **8 results**: added sugars, carbohydrate, dietary fibre, energy, protein, total fat, total sugars, cholesterol | **Yes, mixed with results** |
| Page 2 content stream (separate, ~10 KB compressed) | **6 results**: sodium, saturated / unsaturated / trans fat, MUFA, PUFA, plus signatory and notes | No |
| Download Report QR image (~36 KB) | Bearer link to the full report | Leads to everything |
| Fonts | Subsets shared across pages | Minor: reveal which characters are used |
| Metadata | Title is a UUID, Creator is a Chrome user agent, dates | No |

No XMP, form fields, annotations, embedded files or incremental updates were found.

Chrome writes **one content stream per page**, so personal details and results on the same page cannot be separated at the stream level.

## Proving origin: zkTLS on the S3 object

S3's `ETag` header for the object **equals the MD5 of the PDF** (single-part upload, SSE-S3). So a zkTLS proof of a tiny S3 response is enough to prove "Equinox's bucket holds a file with this MD5 and size", and the user checks the MD5 of their local file against it.

- A request for `Range: bytes=0-0` returns ETag, `Content-Range: bytes 0-0/<size>`, Last-Modified and only 1 body byte, so the whole PDF never goes through the slow MPC step.
- Both `titan.equinoxlab.com` and the S3 host accept TLS 1.2 (needed for TLSNotary) and TLS 1.3.
- MD5 is weak, but it holds up here: the lab generates the file, so the user cannot engineer a collision against it.
- **No email proof is needed for Equinox.**

### Spike result (TLSNotary v0.1.0-alpha.15, MPC-TLS, Apple M2)

| Step | Time |
|---|---|
| MPC preprocessing | 0.19 s |
| TLS handshake + request to the real S3 server | 2.31 s |
| Commit + notary attestation | 0.21 s |
| Build selective-disclosure presentation | ~0 s |
| Verify presentation | ~0 s |
| **Total** | **2.7 s**, 490 MB peak memory, 10 KB proof |

The verified presentation shows the host (bucket), ETag, size, Last-Modified and session time. The request path (the part with the customer's name) is hidden.

Caveats:

- The notary ran in-process. A remote notary adds network latency; expect roughly 5–20 s (estimate, not measured).
- The native build was tested, the browser (WASM) build was not.
- The hidden path's **length** is still visible. Pad the request to hide it.
- A dummy notary key was used. Production needs a notary with a published key, ideally more than one.
- Bucket ownership rests on a one-time public check (titan.equinoxlab.com redirects to it). For a stronger link, add a second zkTLS proof of the titan redirect, tied to the S3 proof with a salted commitment of the path.
- If Equinox switches to multipart or KMS uploads, ETag stops being the MD5. Fallback: a zkTLS proof of the full file download (slower).

## Proving the values

- **Page 2 (6 values):** reveal the page-2 stream as is. Anyone can parse it. No trust in us needed.
- **Page 1 (8 values):** the stream must stay hidden. Options:
  1. **zkVM (SP1 / RISC Zero) on the user's device:** fingerprint the hidden parts, decompress the 6 KB stream, extract the values. Estimated 1–5 min, native app only, not browser. Untested.
  2. **Hackathon shortcut:** extract page-1 values outside the proof and label them "extracted by attested.food" until option 1 lands.
- The Download Report QR image must also stay hidden (it is a second hidden region).

**Confirmation-attack risk:** if hidden parts are bound only by public hash states, someone who already suspects a particular contributor can guess the exact hidden content (name, address, phone) and confirm it. A full zkVM proof that keeps hash states private avoids this. Acceptable for a hackathon, but it should be stated.

## Redaction (on device)

- Use **MuPDF.js** (WASM, AGPL) in the browser so personal details never leave the device. True removal, not boxes drawn over text.
- Detection: a per-lab template (Equinox's labels are fixed), plus a regex sweep for phone, email, PIN code, PAN and Aadhaar. Presidio as the fallback for unknown labs.
- Always: strip metadata and XMP, drop annotations and form fields, rewrite the whole file, remove the Download Report QR.
- Under 1 s per report. Add ~30 s for the user to review a preview.

## Sample custody (still open)

The report states "Sample Collected by: Client" and that results apply to the sample as received. A genuine report proves what the lab received, not what was on the shelf. Candidate fixes that need no cooperation: a zkEmail proof of the order receipt (Amazon, Blinkit, Zepto, BigBasket sign their emails), a photo of the batch number on the sealed pack, lab-collected samples for funded campaigns, and agreement across multiple reports.

## Next steps

1. Measure zkTLS with a remote notary, and in the browser.
2. Add the titan redirect proof and pad the path.
3. Spike the zkVM proof for page-1 values and time it.
4. Revise idea.md's example-report table (report number, ULR and QR become private).
