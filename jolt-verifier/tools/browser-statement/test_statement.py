"""Website postcard framing constraints, not complete proof verification."""

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
from circom_runner import ToolFailure, compile_circuit  # noqa: E402
from website_statement import encode_guest_input, encode_guest_output  # noqa: E402


@unittest.skipUnless(
    all(shutil.which(name) for name in ("circom", "snarkjs", "node")),
    "installed circom, snarkjs, and node required",
)
class StatementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=os.environ.get("BHAI_SCRATCH_DIR"))
        cls.root = Path(cls.temp.name)
        cls.compiled = {}
        cls.counter = 0
        (cls.root / "browser").mkdir()
        (cls.root / "browser-statement").mkdir()
        shutil.copy(ROOT / "circuits/browser/fp128.circom", cls.root / "browser")
        shutil.copy(
            ROOT / "circuits/browser-statement/statement.circom",
            cls.root / "browser-statement",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def circuit(self, tier, n, m):
        key = (tier, n, m)
        if key not in self.compiled:
            source = self.root / f"statement-{tier}-{n}-{m}.circom"
            # Invalid shapes instantiate directly, so the template must reject them.
            if tier not in (20, 21, 31, 33) or n < 0 or n >= 500000 or m >= 4096:
                body = f"component main = BrowserWebsiteStatement({tier}, {n}, {m});"
            else:
                from website_statement import encode_length

                ni = n + len(encode_length(n)) + 2
                mo = m + len(encode_length(m))
                body = f"""template Test() {{
    signal input payload[{n}];
    signal input result[{m}];
    signal input expectedInput[{ni}];
    signal input expectedOutput[{mo}];
    component statement = BrowserWebsiteStatement({tier}, {n}, {m});
    for (var i = 0; i < {n}; i++) {{ statement.payload[i] <== payload[i]; }}
    for (var i = 0; i < {m}; i++) {{ statement.result[i] <== result[i]; }}
    for (var i = 0; i < {ni}; i++) {{ statement.inputBytes[i] === expectedInput[i]; }}
    for (var i = 0; i < {mo}; i++) {{ statement.outputBytes[i] === expectedOutput[i]; }}
}}
component main = Test();"""
            source.write_text(
                'pragma circom 2.2.3;\ninclude "browser-statement/statement.circom";\n'
                + body
                + "\n"
            )
            self.compiled[key] = compile_circuit(
                source, self.root / f"compiled-{tier}-{n}-{m}"
            )
        return self.compiled[key]

    def inputs(self, tier, payload, result):
        return {
            "payload": list(payload),
            "result": list(result),
            "expectedInput": list(encode_guest_input(tier, payload)),
            "expectedOutput": list(encode_guest_output(result)),
        }

    def check(self, tier, inputs, valid=True):
        circuit = self.circuit(tier, len(inputs["payload"]), len(inputs["result"]))
        StatementTests.counter += 1
        directory = self.root / f"case-{self.counter}"
        if valid:
            circuit.check(inputs, directory)
        else:
            with self.assertRaises(ToolFailure):
                circuit.check(inputs, directory)

    def test_all_website_tiers(self):
        for tier in (20, 21, 31, 33):
            self.check(tier, self.inputs(tier, b"abc", bytes(range(32))))

    def test_empty_payloads(self):
        self.check(21, self.inputs(21, b"", b""))

    def test_varint_boundaries(self):
        for size in (127, 128):
            self.check(21, self.inputs(21, bytes(size), bytes(size)))

    def test_maximum_serialized_output(self):
        self.check(31, self.inputs(31, b"", bytes(4094)))

    def test_tampered_framing_and_payload_rejected(self):
        for name, index in (
            ("expectedInput", 0),
            ("expectedInput", 1),
            ("expectedInput", 2),
            ("expectedInput", -1),
            ("expectedOutput", 0),
            ("expectedOutput", 1),
        ):
            inputs = self.inputs(21, b"abc", b"def")
            inputs[name][index] ^= 1
            self.check(21, inputs, valid=False)

    def test_nonbyte_payloads_rejected(self):
        for name in ("payload", "result"):
            for value in (-1, 256):
                inputs = self.inputs(21, b"abc", b"def")
                inputs[name][0] = value
                self.check(21, inputs, valid=False)

    def test_disallowed_tier_and_sizes_rejected(self):
        for shape in ((19, 0, 0), (21, -1, 0), (21, 500000, 0), (21, 0, 4096)):
            with self.assertRaises(ToolFailure):
                self.circuit(*shape)


if __name__ == "__main__":
    unittest.main(verbosity=2)
