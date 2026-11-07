"""Differential tests for our unkeyed sequential BLAKE2b circuit."""

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


@unittest.skipUnless(
    all(shutil.which(name) for name in ("circom", "snarkjs", "node")),
    "installed circom, snarkjs, and node required",
)
class Blake2bTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=os.environ.get("BHAI_SCRATCH_DIR"))
        cls.root = Path(cls.temp.name)
        for name in ("fp128.circom", "blake2b.circom"):
            shutil.copy(ROOT / "circuits/browser" / name, cls.root)
        cls.compiled = {}
        cls.counter = 0

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def circuit(self, size, digest_size):
        key = (size, digest_size)
        if key not in self.compiled:
            name = f"hash-{size}-{digest_size}"
            source = self.root / f"{name}.circom"
            source.write_text(
                f"""pragma circom 2.2.3;
include "blake2b.circom";
template Test() {{
    signal input message[{size}];
    signal input expected[{digest_size}];
    component hash = BrowserBlake2b({size}, {digest_size});
    for (var i = 0; i < {size}; i++) {{ hash.in[i] <== message[i]; }}
    for (var i = 0; i < {digest_size}; i++) {{ hash.digest[i] === expected[i]; }}
}}
component main = Test();
"""
            )
            self.compiled[key] = compile_circuit(source, self.root / name)
        return self.compiled[key]

    def check(self, message, digest_size=32, expected=None, valid=True):
        circuit = self.circuit(len(message), digest_size)
        if expected is None:
            expected = hashlib.blake2b(bytes(message), digest_size=digest_size).digest()
        inputs = {"message": list(message), "expected": list(expected)}
        Blake2bTests.counter += 1
        directory = self.root / f"case-{self.counter}"
        if valid:
            circuit.check(inputs, directory)
        else:
            with self.assertRaises(ToolFailure):
                circuit.check(inputs, directory)

    def test_empty(self):
        self.check(b"")

    def test_multiple_messages_one_circuit(self):
        for message in (b"abc", b"\0\0\0", b"\xff\x80\x01"):
            self.check(message)

    def test_full_block(self):
        self.check(bytes(range(128)))

    def test_multiple_blocks(self):
        self.check(bytes(range(129)))

    def test_blake2b512(self):
        self.check(b"abc", digest_size=64)

    def test_digest_length_is_domain_separated(self):
        truncated = hashlib.blake2b(b"abc", digest_size=64).digest()[:32]
        self.assertNotEqual(truncated, hashlib.blake2b(b"abc", digest_size=32).digest())
        self.check(b"abc", expected=truncated, valid=False)

    def test_modified_digest_and_message(self):
        digest = hashlib.blake2b(b"abc", digest_size=32).digest()
        wrong = bytes([digest[0] ^ 1]) + digest[1:]
        self.check(b"abc", expected=wrong, valid=False)
        self.check(b"abd", expected=digest, valid=False)

    def test_non_byte_input_rejected(self):
        digest = hashlib.blake2b(b"\0bc", digest_size=32).digest()
        self.check([256, 98, 99], expected=digest, valid=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
