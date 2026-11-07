# Browser verifier component sizes

Measured 2026-11-07 with Circom 2.2.3 and `--O1`. These are standalone templates from the in-progress browser circuit lane, not a complete Jolt verifier. Compilation establishes the size, not correctness of the complete protocol.

| Standalone component | Nonlinear constraints | Linear constraints | Total constraints | R1CS bytes |
|---|---:|---:|---:|---:|
| Canonical Fp128 encoding | 256 | 5 | 261 | 42,520 |
| Fp128 addition | 769 | 16 | 785 | 127,604 |
| Fp128 subtraction | 769 | 16 | 785 | 127,640 |
| Fp128 multiplication | 1,101 | 27 | 1,128 | 183,076 |
| Fp128 inverse check | 1,101 | 27 | 1,128 | 182,952 |
| BLAKE2b, 80-byte input, 32-byte digest | 165,120 | 3,496 | 168,616 | 29,159,784 |
| BLAKE2b, 128-byte input, 64-byte digest | 165,120 | 3,528 | 168,648 | 29,174,632 |

Source SHA-256 at measurement:

- `fp128.circom`: `7650b262d3f703e08456ede554f9baa555b407fb8ce1a1af545576a071a1f5f4`
- `blake2b.circom`: `dbcb3b576a0cc3809cd3e12b0f51c73f3bf0a531a1ad474a596b45b1c46fdbfd`

Reproduce with `tools/count_browser_components.py`, passing the browser circuits directory and a fresh output directory. It snapshots the source, writes standalone entry points, compiles R1CS files and records compiler output plus `counts.json`.

## Interpretation

There is no full-verifier count yet. The full website proof relation still needs its exact transcript invocations, scalar stages and Akita PCS checks assembled. Website guest cycle counts, including the `2^21` browser cap, are not outer-circuit constraint counts.

The current hash gadget is expensive. As arithmetic only, 100 independent instances of the measured 80-byte hash total 16,861,600 constraints, before other verifier work. This is a conditional cost illustration, not a measured transcript call count or a prediction of the final circuit. Composition, fixed bytes, range-check reuse and optimization can change the result. R1CS file size is not proving-key size or peak prover memory.
