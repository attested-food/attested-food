"""Browser-field component tests. These are not full Jolt verification tests."""

import os
from pathlib import Path
import random
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from circom_runner import ToolFailure, compile_circuit  # noqa: E402

P = 2**128 - 2**32 + 22537
B = 2**64
FR = 21888242871839275222246405745257275088548364400416034343698204186575808495617


def limbs(value):
    return [str(value % B), str(value // B)]


@unittest.skipUnless(
    all(shutil.which(name) for name in ("circom", "snarkjs", "node")),
    "installed circom, snarkjs, and node required",
)
class Fp128Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=os.environ.get("BHAI_SCRATCH_DIR"))
        cls.root = Path(cls.temp.name)
        cls.counter = 0
        shutil.copy(ROOT / "circuits/browser/fp128.circom", cls.root)
        arithmetic = cls.root / "arithmetic.circom"
        arithmetic.write_text(
            """pragma circom 2.2.3;
include "fp128.circom";
template Arithmetic() {
    signal input a[2];
    signal input b[2];
    signal input expected[3][2];
    component add = BrowserFp128Add();
    component sub = BrowserFp128Sub();
    component mul = BrowserFp128Mul();
    for (var i = 0; i < 2; i++) {
        add.a[i] <== a[i]; add.b[i] <== b[i];
        sub.a[i] <== a[i]; sub.b[i] <== b[i];
        mul.a[i] <== a[i]; mul.b[i] <== b[i];
    }
    for (var i = 0; i < 2; i++) {
        add.out[i] === expected[0][i];
        sub.out[i] === expected[1][i];
        mul.out[i] === expected[2][i];
    }
}
component main = Arithmetic();
"""
        )
        cls.arithmetic = compile_circuit(arithmetic, cls.root / "arithmetic")
        inverse = cls.root / "inverse.circom"
        inverse.write_text(
            """pragma circom 2.2.3;
include "fp128.circom";
component main = BrowserFp128InverseCheck();
"""
        )
        cls.inverse = compile_circuit(inverse, cls.root / "inverse")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self, circuit, inputs, valid=True):
        Fp128Tests.counter += 1
        target = self.root / f"case-{self.counter}"
        if valid:
            circuit.check(inputs, target)
        else:
            with self.assertRaises(ToolFailure):
                circuit.check(inputs, target)

    def arithmetic_input(self, a, b):
        return {
            "a": limbs(a),
            "b": limbs(b),
            "expected": [limbs((a + b) % P), limbs((a - b) % P), limbs(a * b % P)],
        }

    def test_boundary_products(self):
        values = [0, 1, B - 1, B, B + 1, P // 2, P - B, P - 2, P - 1]
        for a in values:
            for b in (0, 1, P - 1):
                with self.subTest(a=a, b=b):
                    self.check(self.arithmetic, self.arithmetic_input(a, b))

    def test_deterministic_random_pairs(self):
        rng = random.Random(0xA71A128)
        for _ in range(16):
            a, b = rng.randrange(P), rng.randrange(P)
            with self.subTest(a=a, b=b):
                self.check(self.arithmetic, self.arithmetic_input(a, b))

    def test_modified_results(self):
        for operation in range(3):
            inputs = self.arithmetic_input(P - 1, P - 2)
            value = int(inputs["expected"][operation][0]) + B * int(
                inputs["expected"][operation][1]
            )
            inputs["expected"][operation] = limbs((value + 1) % P)
            self.check(self.arithmetic, inputs, valid=False)

    def test_no_outer_field_product_shortcut(self):
        a, b = P - 1, P - 2
        self.assertGreater(a * b, FR)
        wrong = (a * b % FR) % P
        self.assertNotEqual(wrong, a * b % P)
        inputs = self.arithmetic_input(a, b)
        inputs["expected"][2] = limbs(wrong)
        self.check(self.arithmetic, inputs, valid=False)

    def test_noncanonical_field_inputs_rejected(self):
        for a in (P, P + 1, 2**128 - 1):
            inputs = self.arithmetic_input(a % P, 1)
            inputs["a"] = limbs(a)
            self.check(self.arithmetic, inputs, valid=False)

    def test_noncanonical_limbs_rejected(self):
        for encoded in ([str(B), "0"], ["0", str(B)], ["-1", "0"]):
            inputs = self.arithmetic_input(0, 0)
            inputs["a"] = encoded
            self.check(self.arithmetic, inputs, valid=False)

    def test_inverse(self):
        for a in (1, B, P - 1, 123456789):
            self.check(self.inverse, {"in": limbs(a), "inverse": limbs(pow(a, -1, P))})

    def test_zero_and_wrong_inverse_rejected(self):
        self.check(self.inverse, {"in": limbs(0), "inverse": limbs(0)}, valid=False)
        self.check(self.inverse, {"in": limbs(2), "inverse": limbs(3)}, valid=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
