// sp1-witness: solve SP1's gnark Groth16 circuit for one SP1 witness input and
// write the full solution for an external Groth16 prover (snarkrs).
//
//	sp1-witness -circuit-dir ~/.sp1/circuits/groth16/v6.1.0 -witness witness.json -out solution.bin
//
// Output, gnark's own dump encoding (the same as the proving key's WriteDump):
// unsafe.WriteMarker, then unsafe.WriteSlice of W (every wire, gnark order,
// W[0] = 1), Aw and Bw (A·w and B·w per constraint), all fr.Element in
// Montgomery form, little-endian, unpadded. The public inputs are W[1..6].
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark-crypto/utils/unsafe"
	"github.com/consensys/gnark/backend/groth16"
	cs "github.com/consensys/gnark/constraint/bn254"
	"github.com/consensys/gnark/frontend"

	"github.com/succinctlabs/sp1-recursion-gnark/sp1"
)

func main() {
	dir := flag.String("circuit-dir", "", "SP1 Groth16 circuit dir (groth16_circuit.bin, constraints.json)")
	witnessPath := flag.String("witness", "", "SP1 witness input JSON")
	out := flag.String("out", "", "solution output file")
	flag.Parse()
	if *dir == "" || *witnessPath == "" || *out == "" {
		flag.Usage()
		os.Exit(2)
	}
	os.Setenv("CONSTRAINTS_JSON", *dir+"/constraints.json")
	os.Setenv("GROTH16", "1")

	t := time.Now()
	f, err := os.Open(*dir + "/groth16_circuit.bin")
	check(err)
	// As SP1 loads it (sp1-recursion-gnark-ffi go/sp1/prove_groth16.go).
	ccs := groth16.NewCS(ecc.BN254)
	_, err = ccs.ReadFrom(bufio.NewReaderSize(f, 1<<20))
	check(err)
	r1cs := ccs.(*cs.R1CS)
	f.Close()
	fmt.Fprintf(os.Stderr, "read r1cs: %s (%d constraints, %d wires)\n", time.Since(t), r1cs.GetNbConstraints(), r1cs.GetNbInternalVariables()+r1cs.GetNbPublicVariables()+r1cs.GetNbSecretVariables())

	t = time.Now()
	data, err := os.ReadFile(*witnessPath)
	check(err)
	var input sp1.WitnessInput
	check(json.Unmarshal(data, &input))
	assignment := sp1.NewCircuit(input)
	witness, err := frontend.NewWitness(&assignment, ecc.BN254.ScalarField())
	check(err)
	fmt.Fprintf(os.Stderr, "witness: %s\n", time.Since(t))

	t = time.Now()
	res, err := r1cs.Solve(witness)
	check(err)
	sol := res.(*cs.R1CSSolution)
	fmt.Fprintf(os.Stderr, "solve: %s (%d wires, %d constraints)\n", time.Since(t), len(sol.W), len(sol.A))

	t = time.Now()
	o, err := os.Create(*out)
	check(err)
	w := bufio.NewWriterSize(o, 1<<22)
	check(unsafe.WriteMarker(w))
	for _, v := range []fr.Vector{sol.W, sol.A, sol.B} {
		check(unsafe.WriteSlice(w, []fr.Element(v)))
	}
	check(w.Flush())
	check(o.Close())
	fmt.Fprintf(os.Stderr, "write: %s\n", time.Since(t))
}

func check(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}
