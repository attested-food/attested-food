"""Tests for raw deployed-Jolt digest steps, not full transcript/PCS verification."""

import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from circom_runner import ToolFailure, compile_circuit  # noqa: E402

P = 2**128 - 2**32 + 22537
B = 2**64


def limbs(value):
    return [str(value % B), str(value // B)]


@unittest.skipUnless(
    all(shutil.which(name) for name in ("circom", "snarkjs", "node")),
    "installed circom, snarkjs, and node required",
)
class JoltDigestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=os.environ.get("BHAI_SCRATCH_DIR"))
        cls.root = Path(cls.temp.name)
        cls.counter = 0
        cls.compiled = {}
        for name in ("fp128.circom", "blake2b.circom", "jolt_digest.circom"):
            shutil.copy(ROOT / "circuits/browser" / name, cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def circuit(self, size):
        if size not in self.compiled:
            source = self.root / f"digest-{size}.circom"
            if size == -1:
                body = """template Test() {
    signal input bytes[16];
    signal input expected[2];
    component decode = BrowserFp128Decode16();
    for (var i = 0; i < 16; i++) { decode.bytes[i] <== bytes[i]; }
    for (var i = 0; i < 2; i++) { decode.out[i] === expected[i]; }
}"""
            else:
                body = f"""template Test() {{
    signal input state[32];
    signal input counter;
    signal input payload[{size}];
    signal input expected[32];
    signal input expectedScalar[2];
    signal input expectedCounter;
    component step = BrowserJoltDigestStep({size});
    step.counter <== counter;
    for (var i = 0; i < 32; i++) {{ step.state[i] <== state[i]; }}
    for (var i = 0; i < {size}; i++) {{ step.payload[i] <== payload[i]; }}
    for (var i = 0; i < 32; i++) {{ step.nextState[i] === expected[i]; }}
    for (var i = 0; i < 2; i++) {{ step.scalar[i] === expectedScalar[i]; }}
    step.nextCounter === expectedCounter;
}}"""
            source.write_text(
                'pragma circom 2.2.3;\ninclude "jolt_digest.circom";\n'
                + body
                + "\ncomponent main = Test();\n"
            )
            self.compiled[size] = compile_circuit(source, self.root / f"digest-{size}")
        return self.compiled[size]

    def check(self, size, inputs, valid=True):
        circuit = self.circuit(size)
        JoltDigestTests.counter += 1
        directory = self.root / f"case-{self.counter}"
        if valid:
            circuit.check(inputs, directory)
        else:
            with self.assertRaises(ToolFailure):
                circuit.check(inputs, directory)

    def step_inputs(self, state, counter, payload):
        round_word = bytes(28) + counter.to_bytes(4, "big")
        digest = hashlib.blake2b(state + round_word + payload, digest_size=32).digest()
        scalar = int.from_bytes(digest[:16], "little") % P
        return {
            "state": list(state),
            "counter": counter,
            "payload": list(payload),
            "expected": list(digest),
            "expectedScalar": limbs(scalar),
            "expectedCounter": counter + 1,
        }

    def test_decode_boundary_and_reduction(self):
        for value in (0, 1, 2**64, P - 1, P, P + 1, 2**128 - 1):
            self.check(
                -1,
                {
                    "bytes": list(value.to_bytes(16, "little")),
                    "expected": limbs(value % P),
                },
            )

    def test_decode_invalid_result_and_byte(self):
        self.check(-1, {"bytes": [0] * 16, "expected": limbs(1)}, valid=False)
        self.check(-1, {"bytes": [256] + [0] * 15, "expected": limbs(256)}, valid=False)

    def test_squeeze_multiple_states_and_counters(self):
        for counter in (0, 1, 0x01020304):
            self.check(0, self.step_inputs(bytes(range(32)), counter, b""))

    def test_append(self):
        self.check(3, self.step_inputs(bytes(range(32)), 9, b"abc"))

    def test_digest_and_counter_tampering(self):
        inputs = self.step_inputs(bytes(range(32)), 0, b"")
        inputs["expected"][0] ^= 1
        self.check(0, inputs, valid=False)
        inputs = self.step_inputs(bytes(range(32)), 0, b"")
        inputs["expectedCounter"] = 2
        self.check(0, inputs, valid=False)

    def test_counter_width_and_overflow_rejected(self):
        inputs = self.step_inputs(bytes(range(32)), 0, b"")
        inputs["counter"] = 2**32
        self.check(0, inputs, valid=False)
        self.check(0, self.step_inputs(bytes(range(32)), 2**32 - 1, b""), valid=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
