# snarkrs as the SP1 v6.10 Groth16 wrap prover: feasibility

2026-11-07. Read-only investigation. Nothing built, run or installed except header parsers over the local artifacts.

Verdict: feasible, nothing blocks it. snarkrs can prove against SP1's existing gnark proving key and the proof verifies under the deployed `SP1VerifierGroth16` v6.1.0, because the circuit is plain R1CS Groth16 with no commitment, the curve, field, domain generator, point layout and blinding algebra all match, and the only real algorithmic gap is that gnark's H bases are monomial (coefficient) bases where snarkrs produces snarkjs odd-coset evaluations. That gap costs one extra coset iNTT on the scalar side. The work is mostly plumbing plus a 100x scale-up of the CUDA path beyond anything snarkrs has been tested at.

Path abbreviations:
- `GO` = `~/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/sp1-recursion-gnark-ffi-6.10.0/go`
- `FFI` = `.../sp1-recursion-gnark-ffi-6.10.0`, `PROVER` = `.../sp1-prover-6.10.0`, `SDK` = `.../sp1-sdk-6.10.0`
- `GNARK` = `~/go/pkg/mod/github.com/consensys/gnark@v0.14.0`. SP1 actually builds against the fork `github.com/p4u/gnark v0.0.0-20251217225531-cd7874155e26` (`GO/go.mod:32`, a `replace`). That fork is in the local module cache and `prove.go`, `setup.go`, `marshal.go`, `solidity.go`, `constraint/bn254/system.go`, `constraint/bn254/marshal.go` and `constraint/marshal.go` are byte-identical to v0.14.0, so the line refs below hold for both. The fork adds `backend/accelerated/icicle`.
- `GC` = `~/go/pkg/mod/github.com/consensys/gnark-crypto@v0.19.3-0.20251115174214-022ec58e8c19`
- `SR` = `~/workspace/experimentation/rust-groth16-prover` (snarkrs)
- `ART` = `~/.sp1/circuits/groth16/v6.1.0`

## 1. Circuit size

Read from the file headers (pk dump header and the R1CS CBOR body streamed with a skip-only parser; no full load).

| Quantity | Value | Source |
|---|---:|---|
| System type | 1 = R1CS (Groth16, as expected) | R1CS body `Type`, enum at `GNARK/constraint/core.go:24-26` |
| Constraints | 15,972,262 | R1CS body `NbConstraints` |
| Domain | 2^24 = 16,777,216 (95.2% full) | pk header `Domain.Cardinality` |
| Wires total | 15,747,144 | pk header `nbWires` |
| Public (incl. constant 1) | 6: `1, VkeyHash, CommittedValuesDigest, ExitCode, VkRoot, ProofNonce` | R1CS body `Public`; struct at `GO/sp1/sp1.go:28-37` |
| Secret | 64,900 (`Vars_*`, felts, exts) | R1CS body `Secret` |
| Internal | 15,682,238 | R1CS body `NbInternalVariables` |
| Commitments (BSB22) | 0 | pk `nbCommitments = 0`; the range checker that would add one is disabled by `GROTH16=1` (`GO/sp1/koalabear/koalabear.go:90-96`, `GO/sp1/prove_groth16.go:33`) |
| gnark version in file | 0.14.0 | R1CS header (`GNARK/constraint/bn254/marshal.go:17-50`) |

Proving key section sizes (`ART/groth16_pk.bin`, 5,862,173,061 B, gnark `WriteDump` format, sums exactly to the file size):

| Section | Points | Size |
|---|---:|---:|
| G1.A (infinity filtered, NbInfinityA = 2,978,799) | 12,768,345 | 0.82 GB |
| G1.B (NbInfinityB = 476,595) | 15,270,549 | 0.98 GB |
| G1.Z (H bases) | 16,777,215 (= n - 1) | 1.07 GB |
| G1.K (private wires) | 15,747,138 (= wires - 6) | 1.01 GB |
| G2.B | 15,270,549 | 1.95 GB |

`ART/groth16_vk.bin` is 492 B (compressed: alpha, beta, gamma, delta, 6 K points, empty commitment lists). `sha256(groth16_vk.bin) = 4388a21c...e696`, which is exactly `VERIFIER_HASH()` in `ART/SP1VerifierGroth16.sol:32-34`, so these local artifacts are the deployed v6.1.0 circuit.

Domain generator in the pk header is `5^((r-1)/2^24)`, which equals the 2^28 root `1910321906...161904` raised to 16, i.e. the same root of unity arkworks and ffjavascript use (`SR/crates/groth16/src/prove.rs:501-514`). FrMultiplicativeGen = 5.

## 2. gnark v0.14 prove vs snarkrs prove

### gnark (`GNARK/backend/groth16/bn254/prove.go`)

- Solve: `r1cs.Solve` returns `R1CSSolution{W, A, B, C}` where A, B, C are the per-constraint values `L·w, R·w, O·w` (`prove.go:101-107`, struct at `GNARK/constraint/bn254/system.go:211-215`).
- H (`computeH`, `prove.go:346-389`): pad a, b, c to n; iFFT (DIF, so bit-reversed out); FFT on the coset `g·<w>` with `g = 5`; `(a·b - c)/(g^n - 1)` pointwise; coset iFFT (DIF). Result: monomial coefficients of `h(X) = (A·B - C)/(X^n - 1)` in bit-reversed order.
- H bases: setup computes `[t^i (t^n - 1)/delta]_1` for i in 0..n, bit-reverses the whole array, then keeps the first n-1 (`setup.go:180-192`, `247-249`). Dropping position n-1 drops coefficient `bitrev(n-1) = n-1`, which is always zero since deg h <= n-2. The Krs MSM is `MultiExp(pk.G1.Z, h[:n-1])` (`prove.go:225-227`).
- A and B bases: `[L_j(t)]`-weighted sums per wire with gnark's own domain and constraint order (`setupABC`, `setup.go:346-428`; same iterator order as the solver). Wires whose A (or B) column is zero are removed from the point arrays and flagged in `InfinityA/InfinityB` (`setup.go:194-219`); the prover filters the scalars the same way before each MSM (`prove.go:142-168`). The public wires 1..5 are all infinity in A because gnark adds no snarkjs-style public-input constraints.
- K bases: one per non-public, non-committed wire, in wire order; with zero commitments `pk.G1.K[i - 6]` belongs to wire i (`setup.go:142-178`), and the MSM runs over `wireValues[6:]` (`prove.go:233-237`).
- Wire order: `[1 | public | secret | internal]` (`GNARK/constraint/bn254/system.go:161` comment; `setup.go:87`).
- Blinding: random r, s; `Ar = alpha + A·w + r·delta`, `Bs = beta + B·w + s·delta` (G1 and G2), `Krs = K·w + Z·h + s·Ar + r·Bs1 - r·s·delta` (`prove.go:170-294`).

### snarkrs

- H: gather A, B rows from the zkey CSR, `C = A∘B` on the domain (`SR/crates/cuda/src/kernels/gather.cu:50-62,116`), then per vector iNTT plus forward NTT on the snarkjs odd coset (shift = primitive 2n-th root, `SR/crates/field/src/lib.rs:114-124`), then `A·B - C` fused into the last store (`SR/crates/cuda/src/stages.rs:533-640,699-760`). Output is H as **evaluations** on the odd coset, consumed by the zkey section 9 bases, which are the odd-index Lagrange basis of the 2n domain over delta.
- MSMs: A, B1, B2, L (= gnark K), H, five resident base vectors (`SR/crates/formats/src/lib.rs:35-59`); infinity is the all-zero packed point and is handled (`SR/crates/gpu-layout/src/lib.rs:170-188`).
- Blinding and assembly: `SR/crates/groth16/src/prove.rs:342-375`. Same algebra as gnark (`pi_c = L + H + s·pi_a + r·pib1 - r·s·delta`).

### Differences that matter

| Item | gnark | snarkrs | Change needed |
|---|---|---|---|
| H scalars | monomial coeffs, bit-reversed, n-1 used | odd-coset evaluations | add coset iNTT and a scale of `1/(shift^n - 1)`; for the odd coset `shift^n = -1`, so the scale is `-1/2`. h is the unique polynomial, so coset choice does not matter |
| H bases | `Z`, n-1, bit-reversed | section 9, n, natural | permute Z to natural order once at load (`natural[k] = Z[bitrev(k)]`), pad slot n-1 with infinity |
| A, B, G2 B bases | infinity entries removed | full n_vars | re-expand with all-zero points at load (+0.4 GB), or compact scalars per MSM |
| A·w, B·w per constraint | from the solver | from CSR gather | take them from the solver; no R1CS matrices needed at all |
| C·w | from the solver | `A∘B` | keep `A∘B`; identical on a satisfied witness, padding rows are 0 |
| Public-input constraints | none | snarkjs adds n_pub+1 rows | irrelevant once the gather is bypassed |
| Wire order, K/L indexing | `[1, pub(5), private...]`, K = wires 6.. | witness[0]=1, L = witness[n_public+1..] | none (n_public = 5) |
| Point and scalar memory layout | `G1Affine{X,Y}` Montgomery 4x u64 LE, 64 B; G2 `{A0,A1}`; infinity = (0,0) | `PackedG1Affine` Montgomery 8x u32 LE, 64 B; Fq2 c0 then c1; infinity = all zero | none: the dump slices are byte-identical to snarkrs' packed layout on little-endian hosts, so they can be uploaded straight from an mmap |
| Domain root | `5^((r-1)/2^24)` | ffjavascript/arkworks root | none, verified equal |
| Blinding | r, s random | r, s from CryptoRng | none |

### Can a gnark pk be turned into a snarkjs zkey without toxic waste?

Yes for H, contrary to the expectation, but there is no reason to do it. The zkey H base i is `[L^{2n}_{2i+1}(t)/delta]`, and `L^{2n}_{2i+1}(X) = Z(X)·q_i(X)` with deg q_i = n-1, so each zkey base is a public linear combination of `[t^j Z(t)/delta]`. gnark only ships j <= n-2, but the j = n-1 component only ever multiplies h_{n-1} = 0, so dropping it is sound. Computing it is a G1 "NTT in the exponent": roughly n/2 · log n = 2·10^8 G1 scalar multiplications by twiddles, hours of GPU time and days of CPU time, once. Doing the equivalent transform on the 2^24 scalars per proof costs one extra NTT (milliseconds). The rest of a zkey (section 4 coefficients) would need decoding gnark's compressed blueprint instructions, which the solver-output route avoids entirely. Conclusion: do not convert; teach snarkrs to read the gnark pk.

## 3. Getting the full solved witness out of gnark

SP1 hands gnark only the input witness JSON (`GO/sp1/sp1.go:44-53`: vars, felts, exts plus the 5 publics); `frontend.NewWitness` turns it into the 64,905-value public+secret witness (`GO/sp1/prove_groth16.go:85-92`) and gnark's solver computes the other 15.68M wires using hints. Hints are registered in `init()` of the koalabear package (`GO/sp1/koalabear/koalabear.go:22-28`): `InvFHint`, `InvEHint`, `ReduceHint`, `SplitLimbsHint`; two of them call into Rust over cgo (`koalabearinv`, `koalabearextinv`, `koalabear.go:481-518`, defined in `FFI/src/koalabear.rs:6-21`). gnark's own `ToBinary`/`IsZero` hints come along via the std imports.

Cleanest exporter: a small `cmd/` inside a copy of SP1's Go module (so the `p4u/gnark` replace and package `sp1` with its hints come for free):

1. `cs := groth16.NewCS(ecc.BN254); cs.ReadFrom(bufio.NewReader(f))` on `groth16_circuit.bin` (same as `GO/sp1/prove_groth16.go:39-47`). Do not load the pk.
2. Parse the witness JSON into `sp1.WitnessInput`, `a := sp1.NewCircuit(in)` (`GO/sp1/utils.go:93-116`), `w, _ := frontend.NewWitness(&a, ecc.BN254.ScalarField())`.
3. `sol, _ := cs.Solve(w)` (`GNARK/constraint/bn254/system.go:55-95`), cast to `*cs_bn254.R1CSSolution`.
4. Dump `sol.W` (15,747,144), `sol.A`, `sol.B` (15,972,262 each; C optional). `R1CSSolution.WriteTo` exists (`system.go:216`) but writes canonical big-endian with a u32 length (`GC/ecc/bn254/fr/vector.go:53-71`); a raw `unsafe.Slice` dump of the `[]fr.Element` backing arrays is already in snarkrs' `PackedFr` layout and avoids 47M conversions.
5. Link the two cgo symbols: build with SP1's own `FFI` static lib, or a 20-line Rust staticlib copying `FFI/src/koalabear.rs`. Reimplementing them in C is possible but adds a way to get the KoalaBear extension wrong.

For an in-process integration instead of files, export a Go function that returns the three slice pointers to Rust (section 6).

Test vector without running SP1 at all: `ART/groth16_witness.json` (2.8 MB) is the template witness SP1 used when building these artifacts (`GO/sp1/build.go:260-300` proves and verifies with it), so it satisfies the circuit.

Solve time: measured on the g6e.xlarge (4 vCPU) as 14 to 30 s warm, separate from the 110 to 126 s gnark CPU prove and from the cold R1CS load of 36.6 s (`research/product-lab-testing/13-equinox-final-workflow-gpu-bench.md`, "Warm OpenVM on the L40S and the Groth16 phase answer"). Not measured on the Mac.

## 4. What snarkrs' CUDA prover must change

Stages:

1. **gnark key loader** (new, `formats`): parse the dump header (`GNARK/backend/groth16/bn254/marshal.go:378-445`: marker `0xdeadbeef` LE, `fft.Domain` per `GC/ecc/bn254/fr/fft/domain.go:353-383`, raw alpha/beta/delta, G2 beta/delta, `nbWires`, `NbInfinityA/B` as BE u64, `InfinityA/B` as 1 byte per wire with no length prefix, `nbCommitments` u32, then five `u64 LE length + raw array` slices per `GC/utils/unsafe/dump_slice.go`). Expand A, B, G2 B back to n_vars with zero points, permute Z out of bit-reversed order and pad to n, keep K as the L query. Prefer a direct mmap-to-device path over building arkworks `ProvingKey` vectors (72 B per G1, 136 B per G2 in arkworks).
2. **gnark vk loader** for the self-check (compressed points; arkworks can decompress). Optional, since SP1 already verifies after proving (`PROVER/src/worker/prover/recursion.rs:777`).
3. **H stage, gnark mode**: skip the CSR gather; upload solver A and B values (2 x 511 MB), compute `c = a∘b` on device (one elementwise kernel, the gather already contains it), run the existing iNTT, odd-coset NTT and fused `a·b - c`, then add: coset iNTT (existing `tw_inv` passes plus a load-time multiply by `shift^{-i}`, either a 512 MB power table like `coset_pows` or on-the-fly powers) and the `-1/2` scale. Hand the natural-order coefficients to the H MSM.
4. **MSMs at 2^24**: no algorithm change, but snarkrs' largest validated circuit is 140,261 constraints (`SR/PERFORMANCE.md:25-32`), about 112x smaller. Things to fix or audit:
   - `MEASURED_MAX_WINDOW = 8` (`SR/crates/cuda/src/msm.rs:341`, used by `window_size`, `msm.rs:406-428`) was tuned at 70k to 140k; at 16M a window of 12 to 16 cuts windows from 32 to 16 to 22 and should be re-swept.
   - u32 limits (`msm.rs:177-190`): entry words = windows x n x 2 = 1.07e9 at c = 8, under `u32::MAX` but over 4 GiB in bytes, so any kernel that forms a byte offset in u32 overflows. Audit every offset product before trusting results.
   - G2 B MSM (15.75M G2 points) will dominate.
   - SP1's witness is dominated by bits from `ToBinary`; snarkrs' 0/1 classification (`msm.rs:591`, `2382`) should help.
5. **Assembly and encoding**: reuse `assemble_from_terms` unchanged; add the SP1 encoding (section 5).

L40S (46 GB) device memory, estimated, not measured:

| Item | Size |
|---|---:|
| Bases, re-expanded (A, B1, K 1.01 GB each, Z 1.07 GB, G2 B 2.02 GB) | 6.1 GB |
| Witness Montgomery + standard copies | 1.0 GB |
| a, b, c, t NTT vectors (4 x 2^24 x 32 B) | 2.15 GB |
| Twiddles + coset tables | about 1 to 1.5 GB |
| MSM sort entries per MSM (`msm.rs:497-500,1900-1905`): c = 8 gives 4.3 GB, c = 13 gives 2.7 GB | x5 if all five plans are live at once: 13 to 21 GB |
| Total | about 23 to 31 GB, fits; serialising the five MSM plans brings it under 15 GB |

Host (30 GB RAM box): today gnark holds R1CS plus pk, observed around 27 GB resident with the rest of SP1 on the 32 GB g6e (doc 13). With snarkrs the Go side keeps only the R1CS plus solver output (W 0.5 GB, a/b/c 1.5 GB; R1CS heap not measured, guess 8 to 12 GB), and the gnark pk (5.9 GB on disk, more as a Go heap) is never loaded. snarkrs streams the pk from page cache to the device with a small pinned staging buffer. Net effect should be lower host pressure than today.

Time on the L40S, extrapolated: snarkrs' 140k-constraint circuit proves in 66 ms warm on this exact GPU (`SR/PERFORMANCE.md:577-597`). Linear scaling gives about 7 s at 2^24; with a tuned window and the bit-heavy witness, 3 to 7 s is a reasonable expectation. Plus about 1 s of PCIe for a, b, W. Against gnark's 110 to 126 s on 4 vCPU, the Groth16 phase would become solve-bound (14 to 30 s).

Effort estimate (one engineer who knows snarkrs):

| Piece | Days |
|---|---:|
| Go exporter / solve bridge, Mac test with `groth16_witness.json` | 1 to 1.5 |
| gnark pk + vk loader, Z permutation, infinity expansion | 1 to 1.5 |
| CPU-backend gnark mode end to end, verified by gnark `Verify` on the Mac | 1 |
| CUDA H stage change (skip gather, coset iNTT, scale) | 1 to 2 |
| CUDA MSM at 2^24: window sweep, memory, u32 audit, L40S runs | 2 to 4 |
| SP1 integration and encoding | 1 to 2 |
| Total | 7 to 12 |

## 5. Final SP1 proof bytes

- gnark side: `NewSP1Groth16Proof` (`GO/sp1/utils.go:63-91`). `public_inputs` = the 5 publics as decimal strings; `raw_proof` = hex of `Proof.WriteRawTo` (`GNARK/backend/groth16/bn254/marshal.go:22-56`: `Ar | Bs | Krs | u32 len(Commitments)=0 | CommitmentPok`), used later by SP1's gnark verify; `encoded_proof` = hex of `exit_code(32) | vk_root(32) | proof_nonce(32) | MarshalSolidity()`, where `MarshalSolidity` is the first 256 bytes of the raw proof when there are no commitments (`GNARK/backend/groth16/bn254/solidity.go:807-820`).
- 256-byte proof layout: `A.x, A.y, B.x.A1, B.x.A0, B.y.A1, B.y.A0, C.x, C.y`, each 32-byte big-endian canonical (G2 imaginary part first, `GC/ecc/bn254/marshal.go:1083-1099`), matching `uint256[8]` and the EIP-197 order the verifier copies straight to the precompile (`ART/Groth16Verifier.sol:519-560`). snarkrs' arkworks `Fq2` is `c0 + c1·u`, so write c1 then c0.
- Rust side: `groth16_vkey_hash = sha256(groth16_vk.bin)` (`FFI/src/groth16_bn254.rs:27-31,63`). `SP1ProofWithPublicValues::bytes()` = `vkey_hash[..4] | encoded_proof` (`SDK/src/proof.rs:167-187`). On chain, `SP1VerifierGroth16.verifyProof` checks the 4-byte selector against `VERIFIER_HASH`, abi-decodes `(exitCode, vkRoot, nonce, uint256[8])`, requires `exitCode == 0` and `vkRoot == VK_ROOT()`, and builds `inputs = [programVKey, sha256(publicValues) & (2^253 - 1), exitCode, vkRoot, nonce]` (`ART/SP1VerifierGroth16.sol:60-80`).
- Where the publics come from (`PROVER/src/worker/prover/recursion.rs:747-777`, same logic in `PROVER/src/build.rs:363-380`): all from the wrap proof's `RecursionPublicValues`. `vkey_hash = koalabears_to_bn254(sp1_vk_digest)`, `committed_values_digest = koalabear_bytes_to_bn254(words_to_bytes(committed_value_digest))`, `exit_code = pv.exit_code`, `vk_root = koalabears_to_bn254(pv.vk_root)`, `proof_nonce = koalabears_proof_nonce_to_bn254(pv.proof_nonce)`. They reach gnark as the witness JSON fields and are also copied verbatim into `public_inputs` and the encoded prefix. SP1's verifier cross-checks the encoded prefix against `public_inputs` (`PROVER/src/verify.rs:827-852`).

So a snarkrs proof needs only (A, B, C) plus the five public values, which are already in the witness JSON. The simplest correct encoder is to hand (A, B, C) back to Go, build `groth16_bn254.Proof{Ar, Bs, Krs}` and call the existing `NewSP1Groth16Proof`; byte equality with today's format is then true by construction.

## 6. Recommended plan

0. **Baseline first (half a day).** SP1 already ships a GPU gnark path: the `groth16-cuda` feature on `sp1-sdk` (`SDK/Cargo.toml:47-48`) builds the Go lib with `-tags=icicle` (`FFI/build.rs:51-54`) and routes to `ProveGroth16` in `GO/sp1/prove_groth16_icicle.go` via the fork's ICICLE backend. It needs the ICICLE CUDA backend installed at `/usr/local/lib/backend` (`GO/sp1/00_icicle_init.go`); check Ingonyama's terms for that backend before relying on it. Measure it on the L40S. If it already lands near 10 s, snarkrs only buys independence from ICICLE and the solve still dominates.
1. **Mac correctness loop.** Go exporter on `ART/groth16_witness.json`; snarkrs CPU (or Metal) gnark mode; verify with gnark `groth16.Verify` and the vk. For stage-level debugging, have the exporter also run a copy of gnark's 40-line `computeH` and compare H coefficients, and compare each MSM against gnark-crypto `MultiExp` on the same inputs.
2. **CUDA on the L40S.** Same artifacts, re-sweep the window, check memory, run 20 warm proofs through gnark verify.
3. **SP1 integration.** `[patch.crates-io] sp1-recursion-gnark-ffi` with a fork whose Go side exports `SolveGroth16Bn254(dataDir, witnessPath)` returning W, A, B pointers (R1CS cached in a global as today, pk never loaded) and `EncodeGroth16Bn254(A, B, C, witnessPath)` wrapping `NewSP1Groth16Proof`. The Rust `Groth16Bn254Prover::prove` (`FFI/src/groth16_bn254.rs:54-65`) calls solve, runs snarkrs in-process (no Rust staticlib inside the Go archive, so no duplicate Rust runtime), then encode. Keep SP1's post-prove gnark verify (`recursion.rs:777`) as the gate.

Biggest risks:

- **Scale.** snarkrs CUDA is validated to 140k constraints on T4 and L40S; 2^24 is about 112x bigger. Expect latent u32 offset bugs, allocation failures and window mistuning before the first verifying proof.
- **H transform details.** Bit-reversed Z, the `-1/2` coset factor, the dropped n-1 base. Any slip gives a proof that silently fails to verify; the computeH comparison in step 1 catches it.
- **Hint linkage.** The exporter must link the same KoalaBear inverse functions; a wrong extension inverse gives an unsatisfied solve, not a bad proof, so it fails loudly.
- **Solve dominates.** After snarkrs the floor is gnark's single-process solve (14 to 30 s on 4 vCPU) plus a 36.6 s cold R1CS load. More vCPUs help the solve; snarkrs does not.
- **Artifact coupling.** The dump format is gnark-internal and endianness-dependent (fine on x86_64 and arm64); a future SP1 circuit version changes all sizes and the vk hash. Pin to v6.1.0 and check `sha256(groth16_vk.bin)` at load.
- **Host RAM on a 30 GB box.** R1CS heap size is unmeasured; measure RSS after `ReadFrom` plus `Solve` before sizing the box.

Nothing found that makes it infeasible: no commitment extension, domain 2^24 is below snarkrs' 2^27 cap (`SR/crates/formats/src/lib.rs:701`), and the generator, layouts and Groth16 equation all match the deployed verifier.

## Next steps

1. Benchmark `sp1-sdk/groth16-cuda` on the L40S to set the bar.
2. Write the Go exporter and measure solve time and RSS on the Mac with `groth16_witness.json`.
3. Prototype the gnark loader plus monomial H on snarkrs' CPU backend and get one proof through gnark `Verify` before touching CUDA.
