# sp1-witness

Solves SP1's gnark Groth16 circuit (v6.1.0 artifacts in `~/.sp1/circuits/groth16/v6.1.0`) for one SP1 witness input and writes the full solution, so an external Groth16 prover (snarkrs CUDA) can prove with SP1's own proving key.

```sh
go build -o sp1-witness ./cmd/sp1-witness
./sp1-witness -circuit-dir ~/.sp1/circuits/groth16/v6.1.0 -witness witness.json -out solution.bin
```

Output: gnark's dump encoding (as the proving key's `WriteDump`): `unsafe.WriteMarker`, then `unsafe.WriteSlice` of W (every wire, gnark order, `W[0] = 1`, public inputs `W[1..6]`), Aw and Bw (A·w and B·w per constraint), `fr.Element` in Montgomery form, little-endian, unpadded.

`sp1/` is SP1's circuit package copied from `sp1-recursion-gnark-ffi` 6.10.0 (`go/sp1`, MIT OR Apache-2.0, Succinct Labs), without its prover, setup and ICICLE files; `go.mod`/`go.sum` and `koalabear.h` are SP1's too. SP1 links the two KoalaBear inverse hints from Rust; `sp1/koalabear/koalabear_inv.c` is a C version (field p = 2^31 - 2^24 + 1, extension x^4 - 3).

Measured on the M2 Max with SP1's sample input (`groth16_witness.json`): read circuit 10.9 s, solve 2.75 s (15,972,262 constraints, 15,747,144 wires), write 0.39 s, peak RSS 11.2 GB, output 1.53 GB; `W[1..6]` equals the input's five public values.
