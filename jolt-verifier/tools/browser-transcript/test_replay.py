"""Initialized outer transcript components, not full Jolt verification."""

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
BASE = 2**64


def replay(payloads, squeezes):
    state = hashlib.blake2b(b"Jolt" + bytes(28), digest_size=32).digest()
    states = [list(state)]
    challenges = []
    if len(payloads) != len(squeezes):
        raise ValueError("Transcript schedule length mismatch")
    for counter, (payload, squeeze) in enumerate(zip(payloads, squeezes)):
        state = hashlib.blake2b(
            state + bytes(28) + counter.to_bytes(4, "big") + payload, digest_size=32
        ).digest()
        states.append(list(state))
        if squeeze:
            value = int.from_bytes(state[:16], "little") % P
            challenges.append([str(value % BASE), str(value // BASE)])
    return {
        "payload": list(b"".join(payloads)),
        "expectedStates": states,
        "expectedChallenges": challenges,
    }


@unittest.skipUnless(
    all(shutil.which(name) for name in ("circom", "snarkjs", "node")),
    "installed circom, snarkjs, and node required",
)
class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=os.environ.get("BHAI_SCRATCH_DIR"))
        cls.root = Path(cls.temp.name)
        cls.compiled = {}
        cls.counter = 0
        shutil.copytree(ROOT / "circuits/browser", cls.root / "browser")
        shutil.copytree(
            ROOT / "circuits/browser-transcript", cls.root / "browser-transcript"
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def circuit(self, kind):
        if kind not in self.compiled:
            if kind == "field":
                body = """template Test() {
    signal input limbs[2];
    signal input expected[16];
    component message = BrowserJoltFieldMessage();
    for (var i = 0; i < 2; i++) { message.limbs[i] <== limbs[i]; }
    for (var i = 0; i < 16; i++) { message.bytes[i] === expected[i]; }
}"""
            elif kind in ("label", "word", "plain"):
                label = "0, [0]" if kind == "word" else "3, [97,98,99]"
                has_count = 0 if kind == "plain" else 1
                body = f"""template Test() {{
    signal input count;
    signal input expected[32];
    component message = BrowserJoltLabelMessage({label}, {has_count});
    message.count <== count;
    for (var i = 0; i < 32; i++) {{ message.bytes[i] === expected[i]; }}
}}"""
            elif kind == "bad-schedule":
                body = "template Test() { component invalid = BrowserJoltReplay(1, [1], [1]); invalid.payload[0] <== 0; }"
            else:
                n = 0 if kind == "initial" else 3
                size = 0 if n == 0 else 3
                nc = 0 if n == 0 else 2
                sizes = "[0]" if n == 0 else "[3,0,0]"
                flags = "[0]" if n == 0 else "[0,1,1]"
                body = f"""template Test() {{
    signal input payload[{size}];
    signal input expectedStates[{n + 1}][32];
    signal input expectedChallenges[{nc}][2];
    component transcript = BrowserJoltReplay({n}, {sizes}, {flags});
    for (var i = 0; i < {size}; i++) {{ transcript.payload[i] <== payload[i]; }}
    for (var i = 0; i < {n + 1}; i++) {{
        for (var j = 0; j < 32; j++) {{ transcript.states[i][j] === expectedStates[i][j]; }}
    }}
    for (var i = 0; i < {nc}; i++) {{
        for (var j = 0; j < 2; j++) {{ transcript.challenges[i][j] === expectedChallenges[i][j]; }}
    }}
}}"""
            source = self.root / f"{kind}.circom"
            source.write_text(
                'pragma circom 2.2.3;\ninclude "browser-transcript/replay.circom";\n'
                + body
                + "\ncomponent main = Test();\n"
            )
            self.compiled[kind] = compile_circuit(
                source, self.root / f"compiled-{kind}"
            )
        return self.compiled[kind]

    def check(self, kind, inputs, valid=True):
        circuit = self.circuit(kind)
        ReplayTests.counter += 1
        directory = self.root / f"case-{self.counter}"
        if valid:
            circuit.check(inputs, directory)
        else:
            with self.assertRaises(ToolFailure):
                circuit.check(inputs, directory)

    def test_initialization(self):
        self.check("initial", replay([], []))

    def test_two_messages_same_fixed_schedule(self):
        for payload in (b"abc", b"def"):
            self.check("replay", replay([payload, b"", b""], [0, 1, 1]))

    def test_state_and_challenge_tampering(self):
        inputs = replay([b"abc", b"", b""], [0, 1, 1])
        inputs["expectedStates"][2][0] ^= 1
        self.check("replay", inputs, valid=False)
        inputs = replay([b"abc", b"", b""], [0, 1, 1])
        inputs["expectedChallenges"][0][0] = "0"
        self.check("replay", inputs, valid=False)

    def test_payload_byte_range(self):
        inputs = replay([b"abc", b"", b""], [0, 1, 1])
        inputs["payload"][0] = 256
        self.check("replay", inputs, valid=False)

    def test_canonical_big_endian_field_messages(self):
        for value in (0, 1, P - 1):
            self.check(
                "field",
                {
                    "limbs": [str(value % BASE), str(value // BASE)],
                    "expected": list(value.to_bytes(16, "big")),
                },
            )
        self.check(
            "field",
            {
                "limbs": [str(P % BASE), str(P // BASE)],
                "expected": list(P.to_bytes(16, "big")),
            },
            valid=False,
        )

    def test_label_count_and_u64_word(self):
        count = 0x0102030405060708
        for kind, prefix in (("label", b"abc" + bytes(21)), ("word", bytes(24))):
            expected = list(prefix + count.to_bytes(8, "big"))
            self.check(kind, {"count": str(count), "expected": expected})
            for invalid in (-1, 2**64):
                self.check(
                    kind, {"count": str(invalid), "expected": expected}, valid=False
                )
            expected[31] ^= 1
            self.check(kind, {"count": str(count), "expected": expected}, valid=False)

    def test_plain_label_requires_zero_count(self):
        expected = list(b"abc" + bytes(29))
        self.check("plain", {"count": 0, "expected": expected})
        self.check("plain", {"count": 1, "expected": expected}, valid=False)

    def test_squeeze_with_payload_rejected(self):
        with self.assertRaises(ToolFailure):
            self.circuit("bad-schedule")


if __name__ == "__main__":
    unittest.main(verbosity=2)
