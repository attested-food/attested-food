#!/usr/bin/env python3
"""Unit and installed-Circom integration tests, not Jolt proof acceptance tests."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from ast_to_circom import FR, Generator
from poseidon_constants import generate as generate_poseidon, reference

CIRCUITS = Path(__file__).resolve().parents[2] / "circuits"


def atom(index):
    return {"Atom": {"Var": index}}


def scalar(value):
    return {"Atom": {"Scalar": [(value >> (64 * i)) & (2**64 - 1) for i in range(4)]}}


def bundle(nodes, root=0, assertion="EqualZero", count=2):
    return {
        "nodes": nodes,
        "inputs": [
            {"index": i, "name": f"input_{i}", "witness_type": "ProofData"}
            for i in range(count)
        ],
        "constraints": [{"name": "test", "root": root, "assertion": assertion}],
    }


class GeneratorTests(unittest.TestCase):
    def test_private_proof_and_public_statement(self):
        data = bundle([{"Sub": [atom(0), atom(1)]}])
        source, report = Generator(data, [0]).generate(True)
        self.assertIn("component main {public [v0]}", source)
        self.assertFalse(report["pcs_verified"])
        self.assertFalse(report["complete_jolt_verifier"])
        self.assertEqual(report["unused_inputs"], [])

    def test_reject_nonnative(self):
        data = bundle([{"Sub": [atom(0), atom(1)]}])
        data["inputs"][1]["target_field"] = "Fq"
        with self.assertRaisesRegex(ValueError, "nonnative"):
            Generator(data, [0])

    def test_cycle_and_unknown(self):
        with self.assertRaisesRegex(ValueError, "cyclic"):
            Generator(bundle([{"Inv": {"NodeRef": 0}}]), []).generate()
        with self.assertRaisesRegex(ValueError, "unsupported"):
            Generator(bundle([{"Oracle": atom(0)}]), []).generate()
        with self.assertRaisesRegex(ValueError, "undeclared"):
            Generator(bundle([{"Inv": atom(42)}]), []).generate()

    def test_duplicate_index(self):
        data = bundle([{"Inv": atom(0)}])
        data["inputs"][1]["index"] = 0
        with self.assertRaisesRegex(ValueError, "duplicate"):
            Generator(data, [])

    def test_public_equality_requires_explicit_public_input(self):
        data = bundle(
            [{"Atom": {"Var": 0}}], assertion={"EqualPublicInput": {"name": "input_1"}}
        )
        with self.assertRaisesRegex(ValueError, "explicitly public"):
            Generator(data, []).generate()
        source, _ = Generator(data, [1]).generate()
        self.assertIn("v0 === v1", source)

    def test_inverse_nonzero(self):
        source, _ = Generator(bundle([{"Div": [atom(0), atom(1)]}]), []).generate()
        self.assertIn("inv0 * v1 === 1", source)

    def test_deep_chain(self):
        nodes = [{"Atom": {"Var": 0}}]
        nodes.extend({"Add": [{"NodeRef": i - 1}, scalar(1)]} for i in range(1, 5000))
        source, report = Generator(bundle(nodes, root=4999), []).generate()
        self.assertEqual(report["reachable_nodes"], 5000)
        self.assertIn("n4999 === 0", source)

    def test_duplicate_names(self):
        data = bundle([{"Inv": atom(0)}])
        data["inputs"][1]["name"] = "input_0"
        with self.assertRaisesRegex(ValueError, "duplicate input name"):
            Generator(data, [])

    def test_integer_indices_and_bounds(self):
        data = bundle([{"Inv": atom(0)}])
        for index in (True, "0", 1.0):
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, "integer"):
                    Generator(data, [index])
        for index in (-1, 9):
            with self.assertRaisesRegex(ValueError, "invalid node reference"):
                Generator(data, [], exports=[index]).generate()
        with self.assertRaisesRegex(ValueError, "not an AST input"):
            Generator(data, [9])

    def test_scalar_encoding_validation(self):
        for limbs in ([0, 0, 0], [2**64, 0, 0, 0], [True, 0, 0, 0], [-1, 0, 0, 0]):
            with self.subTest(limbs=limbs):
                with self.assertRaises(ValueError):
                    Generator(bundle([{"Atom": {"Scalar": limbs}}]), []).generate()

    def test_boundary_outputs_and_equal_node(self):
        data = bundle(
            [{"Atom": {"Var": 0}}, {"Mul": [atom(1), atom(1)]}],
            assertion={"EqualNode": 1},
        )
        source, report = Generator(data, [0], exports=[1]).generate()
        self.assertIn("v0 === n1", source)
        self.assertIn("boundary[0] <== n1", source)
        self.assertEqual(report["boundary_node_ids"], [1])

    def test_unused_inputs_reported(self):
        _, report = Generator(bundle([{"Inv": atom(0)}]), []).generate()
        self.assertEqual(report["unused_inputs"], [1])

    def test_unsupported_backend_and_empty_constraints(self):
        data = bundle([{"TranscriptHash": [{"Keccak": []}, scalar(0), scalar(1)]}])
        with self.assertRaisesRegex(ValueError, "unsupported transcript"):
            Generator(data, [], poseidon_include="poseidon.circom").generate()
        data["constraints"] = []
        with self.assertRaisesRegex(ValueError, "empty scalar"):
            Generator(data, []).generate()

    def test_hash_parameters_required(self):
        data = bundle(
            [{"TranscriptHash": [{"Poseidon": atom(0)}, scalar(0), scalar(1)]}]
        )
        with self.assertRaisesRegex(ValueError, "fixed Poseidon3"):
            Generator(data, []).generate()


@unittest.skipUnless(
    shutil.which("circom") and shutil.which("snarkjs") and shutil.which("node"),
    "installed circom/snarkjs/node required",
)
class CircuitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("BHAI_SCRATCH_DIR"))
        self.root = Path(self.temp.name)
        shutil.copy(CIRCUITS / "transcript.circom", self.root)

    def tearDown(self):
        self.temp.cleanup()

    def run_command(self, *args, success=True):
        result = subprocess.run(
            list(map(str, args)), cwd=self.root, capture_output=True, text=True
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def compile(self, source):
        (self.root / "test.circom").write_text(source)
        self.run_command(
            "circom",
            self.root / "test.circom",
            "--r1cs",
            "--wasm",
            "--O1",
            "-o",
            self.root,
        )

    def witness(self, inputs, success=True):
        (self.root / "input.json").write_text(json.dumps(inputs))
        self.run_command(
            "node",
            self.root / "test_js/generate_witness.js",
            self.root / "test_js/test.wasm",
            self.root / "input.json",
            self.root / "test.wtns",
            success=success,
        )
        if success:
            result = self.run_command(
                "snarkjs",
                "wtns",
                "check",
                self.root / "test.r1cs",
                self.root / "test.wtns",
            )
            self.assertIn("WITNESS IS CORRECT", result.stdout)

    def test_arithmetic_multiple_witnesses_and_tampering(self):
        nodes = [{"Mul": [atom(0), atom(0)]}, {"Sub": [{"NodeRef": 0}, atom(1)]}]
        source, _ = Generator(bundle(nodes, root=1), [1]).generate(True)
        self.compile(source)
        for x in (3, 17):
            self.witness({"v0": str(x), "v1": str(x * x)})
        self.witness({"v0": "3", "v1": "10"}, success=False)
        self.witness({"v0": "4", "v1": "9"}, success=False)

    def test_zero_denominator_rejected(self):
        nodes = [{"Div": [atom(0), atom(1)]}, {"Sub": [{"NodeRef": 0}, scalar(2)]}]
        self.compile(Generator(bundle(nodes, root=1), []).generate(True)[0])
        self.witness({"v0": "10", "v1": "5"})
        self.witness({"v0": "0", "v1": "0"}, success=False)

    def test_transforms(self):
        source = """pragma circom 2.2.3;
include "transcript.circom";
template Test() {
    signal input x;
    signal input expected[4];
    component t[4];
    for (var i = 0; i < 4; i++) {
        t[i] = TranscriptTransform(i);
        t[i].in <== x;
        t[i].out === expected[i];
    }
}
component main = Test();
"""
        self.compile(source)
        for x in (0, 1, 2**128 + 0x123456789ABCDEF, FR - 1):
            b = x.to_bytes(32, "little")
            reverse128 = int.from_bytes(b[:16][::-1], "little")
            expected = [
                int.from_bytes(b[::-1], "little") % FR,
                reverse128 * 2**128 % FR,
                reverse128,
                int.from_bytes(b[:8][::-1], "little") * 2**192 % FR,
            ]
            self.witness({"x": str(x), "expected": list(map(str, expected))})
            expected[2] += 1
            self.witness(
                {"x": str(x), "expected": list(map(str, expected))}, success=False
            )

    def test_poseidon(self):
        committed = (CIRCUITS / "poseidon.circom").read_text()
        (self.root / "poseidon.circom").write_text(committed)
        text = None
        if os.environ.get("JOLT_POSEIDON_CONSTANTS"):
            text = Path(os.environ["JOLT_POSEIDON_CONSTANTS"]).read_text()
            self.assertEqual(generate_poseidon(text), committed)
        self.compile(
            """pragma circom 2.2.3;
include "poseidon.circom";
template Test() {
    signal input x[3];
    signal input expected;
    component h = Poseidon3();
    for (var i = 0; i < 3; i++) { h.in[i] <== x[i]; }
    h.out === expected;
}
component main = Test();
"""
        )
        # Independent expected outputs published in historical poseidon_test.go.
        known = {
            (
                0,
                0,
                0,
            ): 5317387130258456662214331362918410991734007599705406860481038345552731150762,
            (
                1,
                2,
                3,
            ): 6542985608222806190361240322586112750744169038454362455181422643027100751666,
        }
        vectors = dict(known)
        if text is not None:
            vectors[(FR - 1, FR - 2, FR - 3)] = reference(
                text, [FR - 1, FR - 2, FR - 3]
            )
        for inputs, expected in vectors.items():
            if text is not None:
                self.assertEqual(reference(text, inputs), expected)
            self.witness({"x": list(map(str, inputs)), "expected": str(expected)})
            self.witness(
                {"x": list(map(str, inputs)), "expected": str((expected + 1) % FR)},
                success=False,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
