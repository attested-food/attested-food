"""Source-derived vectors and constrained Spongefish component tests."""

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from reference import (
    AkitaReference,
    P,
    ReferenceSponge,
    bridge_session,
    framed,
    h,
    initial_frame,
    mask,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from circom_runner import ToolFailure, compile_circuit  # noqa: E402


def limbs(value):
    return [str(value % 2**64), str(value // 2**64)]


class ReferenceTests(unittest.TestCase):
    def test_published_source_assertion_uses_different_field(self):
        # Akita's source test uses Prime128Offset275, not the website field.
        # This is a published source assertion, not a native run by this lane.
        transcript = AkitaReference(b"backend-test", b"instance")
        raw = transcript.challenge_bytes(32)
        self.assertEqual(
            int.from_bytes(raw, "little") % (2**128 - 275),
            313598626200370843239849985198023824966,
        )
        self.assertEqual(
            raw.hex(),
            "b79223450596a1976cbf8be3fa29b18a3ebec8574d1ababbcaf4a07573c07fc8",
        )

    def test_squeeze_streaming_and_direction_change(self):
        s = ReferenceSponge()
        s.absorb(b"ab")
        s.absorb(b"c")
        cv = h(h(mask(0) + bytes(64) + b"abc"))
        first = h(mask(1) + cv + bytes(8))
        second = h(mask(1) + cv + (1).to_bytes(8, "big"))
        self.assertEqual(
            s.squeeze(3) + s.squeeze(61) + s.squeeze(32), first + second[:32]
        )
        self.assertEqual(s.consumed, 96)
        s.absorb(b"new")
        next_cv = h(mask(2) + cv + (96).to_bytes(8, "big"))
        self.assertEqual(s.cv, next_cv)
        next_cv = h(h(mask(0) + next_cv + b"new"))
        self.assertEqual(s.squeeze(32), h(mask(1) + next_cv + bytes(8))[:32])

    def test_akita_short_requests_consume_full_32_byte_blocks(self):
        a = AkitaReference(b"session", b"instance")
        b = AkitaReference(b"session", b"instance")
        first = b.challenge_bytes(64)
        self.assertEqual(a.challenge_bytes(1), first[:1])
        self.assertEqual(a.challenge_bytes(1), first[32:33])
        self.assertEqual(a.sponge.consumed, 64)
        self.assertEqual(a.challenge_bytes(0), b"")
        self.assertEqual(a.sponge.consumed, 64)

    def test_bridge_rejects_noncanonical_challenge(self):
        for value in (-1, P, 2**128 - 1):
            with self.assertRaises(ValueError):
                bridge_session(b"label", value)


@unittest.skipUnless(
    all(shutil.which(name) for name in ("circom", "snarkjs", "node")),
    "installed circom, snarkjs, and node required",
)
class CircuitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=os.environ.get("BHAI_SCRATCH_DIR"))
        cls.root = Path(cls.temp.name)
        cls.counter = 0
        cls.compiled = {}
        (cls.root / "browser").mkdir()
        (cls.root / "browser-spongefish").mkdir()
        for name in ("fp128.circom", "blake2b.circom"):
            shutil.copy(ROOT / "circuits/browser" / name, cls.root / "browser")
        shutil.copy(
            ROOT / "circuits/browser-spongefish/spongefish.circom",
            cls.root / "browser-spongefish",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def compile(self, name, body):
        if name not in self.compiled:
            source = self.root / f"{name}.circom"
            source.write_text(
                'pragma circom 2.2.3;\ninclude "browser-spongefish/spongefish.circom";\n'
                + body
                + "\ncomponent main = Test();\n"
            )
            self.compiled[name] = compile_circuit(source, self.root / name)
        return self.compiled[name]

    def check(self, circuit, inputs, valid=True):
        CircuitTests.counter += 1
        directory = self.root / f"case-{self.counter}"
        if valid:
            circuit.check(inputs, directory)
        else:
            with self.assertRaises(ToolFailure):
                circuit.check(inputs, directory)

    def counter_hash(self, tag):
        return self.compile(
            f"counter-{tag}",
            f"""template Test() {{
    signal input cv[64];
    signal input counter;
    signal input expected[64];
    component hash = SpongefishCounterHash({tag});
    hash.counter <== counter;
    for (var i = 0; i < 64; i++) {{ hash.cv[i] <== cv[i]; }}
    for (var i = 0; i < 64; i++) {{ hash.out[i] === expected[i]; }}
}}""",
        )

    def test_squeeze_counter_hash_and_tampering(self):
        circuit = self.counter_hash(1)
        cv = h(h(mask(0) + bytes(64) + initial_frame(b"backend-test", b"instance")))
        for counter in (0, 1, 2**32 + 1):
            expected = h(mask(1) + cv + counter.to_bytes(8, "big"))
            self.check(
                circuit,
                {"cv": list(cv), "counter": str(counter), "expected": list(expected)},
            )
        expected = bytearray(h(mask(1) + cv + bytes(8)))
        expected[0] ^= 1
        self.check(
            circuit,
            {"cv": list(cv), "counter": "0", "expected": list(expected)},
            valid=False,
        )

    def test_end_squeeze_binds_consumed_bytes_and_u64_be(self):
        circuit = self.counter_hash(2)
        cv = bytes(range(64))
        for consumed in (32, 64, 96, 2**32 + 1):
            expected = h(mask(2) + cv + consumed.to_bytes(8, "big"))
            self.check(
                circuit,
                {"cv": list(cv), "counter": str(consumed), "expected": list(expected)},
            )
        wrong = h(mask(2) + cv + (2).to_bytes(8, "big"))
        self.check(
            circuit,
            {"cv": list(cv), "counter": "96", "expected": list(wrong)},
            valid=False,
        )
        self.check(
            circuit,
            {"cv": list(cv), "counter": str(2**64), "expected": list(wrong)},
            valid=False,
        )

    def test_finish_absorb_double_hash_and_mutation(self):
        circuit = self.compile(
            "finish",
            """template Test() {
    signal input cv[64];
    signal input data[3];
    signal input expected[64];
    component finish = SpongefishFinishAbsorb(3);
    for (var i = 0; i < 64; i++) { finish.cv[i] <== cv[i]; }
    for (var i = 0; i < 3; i++) { finish.data[i] <== data[i]; }
    for (var i = 0; i < 64; i++) { finish.nextCV[i] === expected[i]; }
}""",
        )
        for cv, data in ((bytes(64), b"abc"), (bytes(range(64)), b"xyz")):
            expected = h(h(mask(0) + cv + data))
            self.check(
                circuit,
                {"cv": list(cv), "data": list(data), "expected": list(expected)},
            )
        wrong = h(mask(0) + bytes(64) + b"abc")
        self.check(
            circuit,
            {"cv": list(bytes(64)), "data": list(b"abc"), "expected": list(wrong)},
            valid=False,
        )

    def test_bridged_preamble_bytes_and_noncanonical_challenge(self):
        circuit = self.compile(
            "preamble",
            """template Test() {
    signal input label[3];
    signal input challenge[2];
    signal input instance[2];
    signal input expected[165];
    component preamble = AkitaBridgedPreamble(3, 2);
    for (var i = 0; i < 3; i++) { preamble.baseLabel[i] <== label[i]; }
    for (var i = 0; i < 2; i++) {
        preamble.outerChallenge[i] <== challenge[i];
        preamble.instance[i] <== instance[i];
    }
    for (var i = 0; i < 165; i++) { preamble.frame[i] === expected[i]; }
}""",
        )
        for challenge in (0, 0x0102030405060708090A0B0C0D0E0F10, P - 1):
            expected = initial_frame(bridge_session(b"pcs", challenge), b"io")
            self.check(
                circuit,
                {
                    "label": list(b"pcs"),
                    "challenge": limbs(challenge),
                    "instance": list(b"io"),
                    "expected": list(expected),
                },
            )
        expected = bytearray(initial_frame(bridge_session(b"pcs", 1), b"io"))
        expected[64] ^= 1
        self.check(
            circuit,
            {
                "label": list(b"pcs"),
                "challenge": limbs(1),
                "instance": list(b"io"),
                "expected": list(expected),
            },
            valid=False,
        )
        self.check(
            circuit,
            {
                "label": list(b"pcs"),
                "challenge": limbs(P),
                "instance": list(b"io"),
                "expected": list(expected),
            },
            valid=False,
        )

    def test_absorb_frame_length_and_byte_bounds(self):
        circuit = self.compile(
            "frame",
            """template Test() {
    signal input payload[3];
    signal input expected[11];
    component encoder = AkitaAbsorbFrame(3);
    for (var i = 0; i < 3; i++) { encoder.payload[i] <== payload[i]; }
    for (var i = 0; i < 11; i++) { encoder.frame[i] === expected[i]; }
}""",
        )
        expected = list(framed(b"abc"))
        self.check(circuit, {"payload": list(b"abc"), "expected": expected})
        expected[0] = 4
        self.check(
            circuit, {"payload": list(b"abc"), "expected": expected}, valid=False
        )
        self.check(
            circuit,
            {"payload": [256, 98, 99], "expected": list(framed(b"\0bc"))},
            valid=False,
        )

    def test_decode_256_bits_without_outer_field_reduction(self):
        circuit = self.compile(
            "decode",
            """template Test() {
    signal input bytes[32];
    signal input expected[2];
    component decode = AkitaDecode32();
    for (var i = 0; i < 32; i++) { decode.bytes[i] <== bytes[i]; }
    for (var i = 0; i < 2; i++) { decode.out[i] === expected[i]; }
}""",
        )
        for value in (
            0,
            P,
            2**128,
            2**256 - 1,
            int.from_bytes(bytes(range(32)), "little"),
        ):
            self.check(
                circuit,
                {
                    "bytes": list(value.to_bytes(32, "little")),
                    "expected": limbs(value % P),
                },
            )
        self.check(
            circuit,
            {"bytes": [255] * 32, "expected": limbs(((2**256 - 1) % P + 1) % P)},
            valid=False,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
