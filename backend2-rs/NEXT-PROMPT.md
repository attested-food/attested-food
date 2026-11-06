# Next session prompt: backend2-rs (prover.openlabel.fyi), state and next steps

Repo: `~/workspace/hackathons/ethglobal-mumbai-2026/attested-food-github-repo` (branch `main`, pushed up to `9854a5b`; later commits local). Read `backend2-rs/README.md` first.

## What runs today

- GPU box: AWS g6e.xlarge `i-078bdddab89a51802`, `13.232.15.45` (no Elastic IP; a restart changes the IP and `prover.openlabel.fyi` DNS must follow), ssh `-i ~/.claude/skills/aws/keys/agent-ap-south-1.pem ubuntu@13.232.15.45`. L40S 46 GB, 4 vCPU, 30 GB RAM. Scheduled power-off moved to **2026-11-07 12:30 UTC (6 PM IST)**; shutdown behavior is stop (disk kept). Caveat: the `bhai` agent's `~/PROMPT.md`/`~/GOAL*.md` tell it to `sudo shutdown -h now` after its 08:30 UTC report; the user has not decided whether to edit them.
- backend2 server: tmux `backend2`, `127.0.0.1:4000` behind nginx `https://prover.openlabel.fyi`; `~/backend2-start.sh`, `~/backend2-env.sh` (Go, CUDA 12.8), `~/backend2-redeploy.sh` (rebuild under `heavy`, kill old, wait for :4000, restart). Sync source with `rsync -az --exclude target --exclude zktls/runs --exclude '*.pdf' --exclude contracts/out --exclude contracts/cache backend2-rs/ ubuntu@13.232.15.45:backend2-rs/`.
- Box lock: `heavy <label> <cmd>` (flock `~/locks/cpugpu.lock`, `heavy status`). backend2 takes it only while proving (`server/src/lock.rs`, `PROVE_FLOCK`). Do not touch tmux `bhai`, `server`, `goal2-anvil`.
- API: `POST /prove?mode=sp1-groth16` (default) with only a `pdf` (`format=eurekha-attested`): server reads the S3 link from the PDF's QR, fetches it under TLSNotary (server is also the notary, dev key), checks bytes equal, proves. Job API `GET /jobs/{id}`: stages, progress, `partial["sp1-compressed"]` (SP1 STARK) then `result.artifact` (Groth16 for `contracts/` `EurekhaReportRegistry.submit`). Frontend `/prove` page (React) sends only the PDF.
- Measured on the box: SP1 STARK 16 to 43 s, gnark Groth16 (CPU, 4 vCPU) 142 s warm, 344 s when the box swaps (RAM tight: SP1 GPU server holds ~15-20 GB RAM, 11-18 GB VRAM). Live artifact passes all 9 Foundry tests; program vkey `0x00721e79...` (box build).

## In progress: `sp1-groth16-snarkrs` mode (snarkrs CUDA replaces gnark's Groth16 step)

Split with the snarkrs Claude session (`rust-groth16-prover`, reachable via SendMessage `uds:/tmp/cc-socks/39878.sock` while it runs): they own snarkrs (gnark pk/vk import, gnark-basis H, CUDA at 2^24, library API `snarkrs_gnark::GnarkProvingKey::read_dump`, `snarkrs_cuda::GnarkProver::new/prove(&GnarkWitness) -> Proof{a,b,c}`, `snarkrs_gnark::verify`); we own the SP1 side. They use the same box under `heavy`; they may not finish before the power-off.

Done on our side:
- `docs/snarkrs-sp1-groth16-feasibility.md`: SP1 circuit is plain R1CS, 15,972,262 constraints, domain 2^24, 0 commitments, sha256(vk) = contract VERIFIER_HASH.
- `sp1/witness-export` (Go): solves SP1's circuit with gnark, writes W, A·w, B·w (gnark dump encoding). Mac: read 10.9 s, solve 2.75 s, 11.2 GB peak, 1.5 GB output; public inputs check out.
- `eurekha-sp1 wrap-witness --stark stark.bin --out witness.json`: compressed proof -> SP1 `shrink_wrap` on CPU (`SP1LocalNodeBuilder` + `cpu_worker_builder`) -> SP1's gnark witness input, as SP1's `run_groth16`. `prove --stark-only` writes `stark.bin`. Measured on the M2 Max (12 cores): compressed STARK 80 s (CPU, 28 GB peak), CPU node build 11.9 s, **shrink + wrap 224 s (27.7 GB peak)**, witness 12 ms; `sp1-witness` then solves it (2.76 s), so the chain works. On the box (4 vCPU, 30 GB RAM) the CPU wrap would be slower than gnark's whole 142 s Groth16 and likely OOM: **the CPU wrap route is not viable there**.

Next steps:
1. Find a GPU shrink+wrap path before investing more (the CPU wrap is too slow, see above). SP1's GPU server (`sp1-gpu-server`, client crate `sp1-cuda` 6.10.0) only takes whole-proof `ProveWithMode` requests and runs gnark itself, so options are: SP1's GPU prover source (succinctlabs sp1-gpu) built with a hook that dumps the gnark witness, or calling its shrink/wrap as a library; or hand gnark's witness dump from inside the GPU server. Until then snarkrs can only replace gnark when the wrap happens on the GPU.
2. Done on the Mac: stark.bin -> witness.json -> `sp1-witness` solve works; still to check W[1..5] against the proof's public values.
3. When snarkrs `GnarkProver` lands: link it in `eurekha-sp1` (key resident), add `serve` job type and server `mode=sp1-groth16-snarkrs`, encode SP1's 356-byte proof (4-byte vk hash prefix, exit code, vk root, nonce, A, B with imaginary first, C; SP1's Go `NewSP1Groth16Proof`), verify with `sp1-verifier` and the Foundry tests.
4. Benchmark on the box: gnark vs snarkrs for the same job (STARK, wrap, solve, Groth16), warm, and record in README.
5. Open: STARKs we publish (`partial`, OpenVM `stark`) may not be zero-knowledge (unverified); OpenVM Halo2 route (`mode=openvm-halo2`) needs ~14 GB downloads, not started; real notary instead of the dev key.
