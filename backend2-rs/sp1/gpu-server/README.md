# sp1-gpu-server with snarkrs Groth16

`snarkrs.patch` applies to SP1 `v6.10.0` (`git clone --depth 1 --branch v6.10.0 https://github.com/succinctlabs/sp1`). It gives `sp1-recursion-gnark-ffi` a `snarkrs` feature: `Groth16Bn254Prover::prove` serializes the witness as before, then, when `SP1_GROTH16_PROVER=snarkrs`, solves it with `snarkrs-gnark-solver` and proves it on the GPU with `snarkrs-cuda` (`snarkrs_cuda::gnark::prepare`, snarkrs main 484e6a4) instead of gnark's Go prover. The circuit is read once per process and the key (`groth16_pk.bin`, a gnark `WriteDump`) streamed once into VRAM, about 14 GB. Without the variable the server proves with gnark as released.

The snarkrs crates are path deps on `/home/ubuntu/rust-groth16-prover` (the GPU box) until they are pushed. Build on the box (CMake >= 3.24, CUDA 12.8):

```sh
CUDA_ARCHS=89 cargo build --release -p sp1-gpu-server --features sp1-recursion-gnark-ffi/snarkrs
```

Install as `~/.sp1/bin/sp1-gpu-server`. `sp1-cuda` replaces that binary only when it is missing or its `--version` is not `6.10.0`, so the build stays. backend2's SP1 worker spawns the server with its own environment, so `SP1_GROTH16_PROVER` set for backend2 reaches it.

Checks: an earlier CPU variant of this module (`CpuBackend` in place of `snarkrs_cuda::gnark::prepare`) proved SP1's sample witness and a backend2 job's witness on the Mac, accepted by `sp1_verifier::Groth16Verifier::verify_gnark_proof` and SP1's `Groth16Verifier.sol` (`contracts/test/SnarkrsGroth16.t.sol`). The CUDA build's live artifact passes the registry tests (`contracts/test/fixtures/sp1-groth16-snarkrs.json`). Timings: `../../README.md`, Measured.
