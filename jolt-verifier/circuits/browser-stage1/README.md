# Website stage-1 RV64 remainder

Partial clear-mode stage relation for the website `/prove` equinox guest, tiers 20/21/31/33. Uses the Solinas field `p = 2^128 - 2^32 + 22537` inside BN254 Fr. Not a complete stage-1 verifier or complete Jolt proof verifier. Transcript challenges, the uni-skip output and opening claims remain external signals. No host acceptance flags or challenge-dependent inversion hints are used.

## Pinned source

Jolt `d39bd518a65ea89401de63c3343e98fbad5f1b80`, wasm fork `6d3bdeb4e3f42f1480f50220f546d64e9adb0058`, Akita `252abb895046cc1d5b9955a26a2ad2318148ac26`, Spongefish `0.7.4`. Inspected native source read-only in the existing fixture VM, without building or modifying it.

The following files have identical SHA256 across `/home/admin/jolt-cli-src`, `/home/admin/.cargo/git/checkouts/jolt-bc4943ecdf5f6930/d39bd51` and the patched website tree `/home/admin/jwp/.wasm-deps/jolt`:

| Path under source root | SHA256 |
| --- | --- |
| `crates/jolt-r1cs/src/constraints/jolt.rs` | `da49558380565daaa1e3ffae53af6e66e0a9eecdec5c076a3b3e58517279f640` |
| `crates/jolt-r1cs/src/constraints/rv64.rs` | `819ac358475be6afec35f7db9ed20e23cbf18048dfacaaf3b4803c8c9a6acaeb` |
| `crates/jolt-poly/src/lagrange.rs` | `4059a55eb786a10d78def96317e28f833cc51a6d3c2908022bc4fb76e75bceb5` |
| `crates/jolt-verifier/src/stages/stage1/verify.rs` | `521c74634ebd87f316a43a653e8c12c415edb5b8899b7c4cb0548db34504911d` |
| `crates/jolt-verifier/src/stages/stage1/outer_remainder.rs` | `927ee380c9c2952a66b91fa39ac3dbcc33051491adcf87bad316ef6b26478cfc` |

Exact source entry points at that Jolt revision:

- [`jolt-r1cs/src/constraints/jolt.rs`](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-r1cs/src/constraints/jolt.rs): `spartan_outer_row_weights`, `JoltSpartanOuterRemainder::new`, `expected_output_claim`, `spartan_outer_tau_kernel`.
- [`jolt-r1cs/src/constraints/rv64.rs`](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-r1cs/src/constraints/rv64.rs): `rv64_eq_constraint_rows`, columns 0 through 35 and all 19 equality rows, including subtraction bias `2^64` and affine constants.
- [`jolt-poly/src/lagrange.rs`](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-poly/src/lagrange.rs): domain size 10 starts at -4, so nodes are `{-4,...,5}`, not `{-5,...,4}`. The circuit uses product-form basis polynomials with fixed inverse denominators, valid at every node without branching.
- [`jolt-verifier/src/stages/stage1/verify.rs`](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-verifier/src/stages/stage1/verify.rs): clear uni-skip initial claim is zero, its reduced output supplies the remainder input claim.
- [`jolt-verifier/src/stages/stage1/outer_remainder.rs`](https://github.com/a16z/jolt/blob/d39bd518a65ea89401de63c3343e98fbad5f1b80/crates/jolt-verifier/src/stages/stage1/outer_remainder.rs): all 35 opening points are the reversed remainder challenge vector.
- `crates/jolt-verifier/src/stages/stage1/outputs.rs`, `crates/jolt-verifier-derive/src/lib.rs`: singleton remainder batch, one `challenge_scalar()` coefficient even for a singleton; initial and terminal claims are both multiplied by it.
- `crates/jolt-claims/src/protocols/jolt/geometry/spartan.rs`: `SpartanOuterDimensions::rv64`, affine terms enabled, `R = log_t + 1`.

This unit fixes the non-`field-inline` RV64 layout of 35 opening claims and 19 equality rows. The inspected website manifest selects Akita/Solinas and does not request `field-inline`; source file equality alone does not certify the feature graph or source-to-asset build. Fixture provenance remains owned by the native fixture lane.

## Implemented relation

Let `r` be the raw remainder challenges, `u` the uni-skip challenge and `L_i` the Lagrange basis on `{-4,...,5}`.

- First row group `[1,2,3,4,5,6,11,14,17,18]` receives weights `(1-r[0])*L_i(u)`.
- Second row group `[0,7,8,9,10,12,13,15,16]` receives weights `r[0]*L_i(u)`, using only basis indices 0 through 8. There is no tenth row in this group.
- `Az = sum_row(weight[row] * A_row(openings,1))`, likewise `Bz`. Each form includes its public constant-column contribution.
- `tauKernel = sum_i(L_i(tau[last])*L_i(u)) * product_j((1-tau[j])*(1-r[R-1-j]) + tau[j]*r[R-1-j])`.
- Unweighted terminal is `tauKernel * Az * Bz`, not a sum of rowwise products.
- Remainder initial claim is `batchingCoefficient * uniskipOutputClaim`, with no padding for a singleton.
- Remainder final claim is `batchingCoefficient * terminal`.

The integrated template constrains the compressed sumcheck to those endpoints. It permits a zero coefficient because the native field draw permits zero; transcript binding must establish the coefficient rather than a fabricated nonzero restriction.

## Typed interface

Every scalar is `Fp128 = signal[2]`, canonical little-endian u64 limbs. Compile with Circom 2.2.3 over BN254 Fr. `LOG_T` is a public compile-time shape, `0 <= LOG_T <= 21`; `R = LOG_T + 1`. The application must bind the approved trace length separately.

`BrowserStage1Terminal(LOG_T)` inputs:

- `tau[LOG_T+2]: Fp128`, in native draw order.
- `uniskipChallenge: Fp128`.
- `remainderChallenges[R]: Fp128`, in raw sumcheck order, stream first.
- `openings[35]: Fp128`, in column order below.

Outputs: `terminal: Fp128`, `tauKernel: Fp128`, `az: Fp128`, `bz: Fp128`, `openingPoint[R]: Fp128`. The point output is shared by every opening, in native opening order (reversed raw challenges). Every opening is canonical even if its matrix column is unused, such as `IsFirstInSequence`.

`BrowserStage1Remainder(LOG_T)` takes the same inputs plus `uniskipOutputClaim: Fp128`, `batchingCoefficient: Fp128`, `compressed[R][3]: Fp128`. Outputs `initialClaim`, `expectedFinal`, `openingPoint` and constant-zero `uniskipInitialClaim`. The fixed serialized shape is three stored coefficients per round: `[c0,c2,c3]`. Native verification also admits shorter nonempty polynomials below the degree bound. Those shapes need their actual serialized lengths compiled into the scalar checker; do not silently pad them because transcript counts differ.

Opening indices 0 through 34, matching native declaration order:

```text
LeftInstructionInput, RightInstructionInput, Product, ShouldBranch, PC,
UnexpandedPC, Imm, RamAddress, Rs1Value, Rs2Value, RdWriteValue,
RamReadValue, RamWriteValue, LeftLookupOperand, RightLookupOperand,
NextUnexpandedPC, NextPC, NextIsVirtual, NextIsFirstInSequence,
LookupOutput, ShouldJump, AddOperands, SubtractOperands, MultiplyOperands,
Load, Store, Jump, WriteLookupOutputToRD, VirtualInstruction, Assert,
DoNotUpdateUnexpandedPC, Advice, IsCompressed, IsFirstInSequence,
IsLastInSequence
```

## Remaining exact wiring

- Verify the separate full uni-skip polynomial over 10 centered integer nodes, degree at most 27, initial sum zero, evaluation at `uniskipChallenge` equal to `uniskipOutputClaim`.
- Connect native transcript draws for tau (`LOG_T+2`), uni-skip and remainder challenges; absorb uni-skip output under `opening_claim` before the singleton coefficient draw. The batch also absorbs its input under `sumcheck_claim` before drawing that coefficient.
- Absorb counted compressed rounds and all 35 output claims in native order. Connect the parent transcript and fixed serialized lengths rather than trusting supplied challenges.
- Authenticate all 35 openings through subsequent stages and Akita PCS at the derived opening point; bind statement, program/configuration and trace length.
- Compare genuine website stage fixtures when the native lane exports them. These tests use authored consistent scalar data only. They deliberately solve for a last-round coefficient, which illustrates why externally supplied challenges are not proof verification.

## Tests

```sh
python3 -m unittest discover -s jolt-verifier/tools/browser-stage1 -v
```

Independent integer reference uses named row expressions and direct integer arithmetic, not the circuit's sparse coefficient tables. Tests cover basis-node identities, partition of unity, affine constants and subtraction bias, terminal values at grid and field boundaries, reversed opening points, integrated cubic rounds, zero batching coefficient, and mutations of claims, openings, challenges, coefficients and round messages. Every successful witness must pass `snarkjs wtns check`.
