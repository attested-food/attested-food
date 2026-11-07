"""Tests of the test harness, not evidence of Jolt proof verification."""

import tempfile
import unittest
from pathlib import Path

from circom_runner import ToolFailure, compile_circuit


class CircomRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="circom-runner-")
        cls.directory = Path(cls.temporary.name)
        source = cls.directory / "harness.circom"
        source.write_text(
            "pragma circom 2.2.3;\n"
            "template Harness() {\n"
            "    signal input a;\n"
            "    signal input b;\n"
            "    signal input product;\n"
            "    a * b === product;\n"
            "}\n"
            "component main {public [product]} = Harness();\n",
            encoding="utf-8",
        )
        cls.compiled = compile_circuit(source, cls.directory / "build")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_accepts_satisfying_witness_and_checks_r1cs(self):
        self.compiled.check(
            {"a": "2", "b": "3", "product": "6"}, self.directory / "accepted"
        )

    def test_rejects_unsatisfying_witness(self):
        with self.assertRaises(ToolFailure):
            self.compiled.check(
                {"a": "2", "b": "3", "product": "7"}, self.directory / "rejected"
            )

    def test_rejects_missing_inputs(self):
        with self.assertRaises(ToolFailure):
            self.compiled.check({"a": "2", "product": "6"}, self.directory / "missing")

    def test_compile_failure_is_not_an_acceptance(self):
        source = self.directory / "invalid.circom"
        source.write_text("not a circuit\n", encoding="utf-8")
        with self.assertRaises(ToolFailure):
            compile_circuit(source, self.directory / "invalid-build")


if __name__ == "__main__":
    unittest.main()
