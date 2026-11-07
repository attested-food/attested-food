"""Guest serialization tests, not proof verification or guest execution."""

import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "tools/website_statement.py"
SPEC = importlib.util.spec_from_file_location("website_statement", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class WebsiteStatementTests(unittest.TestCase):
    def test_roundtrip_allowed_tiers(self):
        for tier in (20, 21, 31, 33):
            with self.subTest(tier=tier):
                payload = b"serialization-test-only"
                raw = MODULE.encode_guest_input(tier, payload)
                self.assertEqual(raw[0], tier)
                self.assertEqual(raw[-1:], b"\x00")
                self.assertEqual(
                    MODULE.decode_guest_input(raw), MODULE.GuestInput(tier, payload)
                )

    def test_other_tiers_rejected(self):
        for tier in (0, 1, 2, 30, 32, 40, 255, True):
            with self.subTest(tier=tier), self.assertRaises(ValueError):
                MODULE.encode_guest_input(tier, b"")
        with self.assertRaises(ValueError):
            MODULE.decode_guest_input(b"\x02\x00\x00")

    def test_empty_labels_and_end_of_input_are_required(self):
        raw = MODULE.encode_guest_input(20, b"x")
        for suffix in (b"", b"\x01\x00", b"\x00\x00"):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                MODULE.decode_guest_input(raw[:-1] + suffix)

    def test_truncated_or_overlong_lengths_rejected(self):
        for raw in (b"", b"\x14\x80", b"\x14\x81\x00x\x00", b"\x14\x02x"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                MODULE.decode_guest_input(raw)

    def test_input_limit_applies_to_the_serialized_input(self):
        raw = MODULE.encode_guest_input(20, b"x" * 499995)
        self.assertEqual(len(raw), MODULE.MAX_INPUT_SIZE)
        self.assertEqual(len(MODULE.decode_guest_input(raw).payload), 499995)
        with self.assertRaises(ValueError):
            MODULE.encode_guest_input(20, b"x" * 499996)

    def test_output_roundtrip_and_serialized_limit(self):
        for payload in (b"", b"x" * 32, b"x" * 4094):
            with self.subTest(size=len(payload)):
                self.assertEqual(
                    MODULE.decode_guest_output(MODULE.encode_guest_output(payload)),
                    payload,
                )
        with self.assertRaises(ValueError):
            MODULE.encode_guest_output(b"x" * 4095)

    def test_noncanonical_or_mismatched_output_rejected(self):
        for raw in (b"", b"\x80\x00", b"\x02x", b"\x01xy", b"\xff" * 8):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                MODULE.decode_guest_output(raw)

    def test_payloads_must_be_bytes(self):
        for payload in ("x", [], bytearray(b"x")):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    MODULE.encode_guest_input(20, payload)
                with self.assertRaises(ValueError):
                    MODULE.encode_guest_output(payload)


if __name__ == "__main__":
    unittest.main()
