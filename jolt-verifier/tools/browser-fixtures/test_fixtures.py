#!/usr/bin/env python3
"""Regression checks using the committed genuine fixtures, not synthetic proofs."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from validate_pair import check_pair, validate

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/browser"
TARGET = ROOT / "website-target.json"


class FixtureTests(unittest.TestCase):
    def test_same_shape_and_standard_sha256(self):
        result = check_pair(FIXTURES, TARGET)
        self.assertTrue(result["identical_verifier_preprocessing"])
        self.assertEqual(result["same_shape"]["trace_length"], 8192)

    def mutated_fixture(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        destination = Path(directory.name) / "abc"
        shutil.copytree(FIXTURES / "tier21-abc", destination)
        return destination

    def test_changed_proof_bytes_are_rejected(self):
        destination = self.mutated_fixture()
        proof = destination / "proof.bin"
        data = bytearray(proof.read_bytes())
        data[-1] ^= 1
        proof.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "Hash mismatch: proof.bin"):
            validate(destination, b"abc", json.loads(TARGET.read_text()))

    def test_missing_native_record_is_rejected(self):
        destination = self.mutated_fixture()
        path = destination / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["native_full_verification"] = False
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "Missing native verification"):
            validate(destination, b"abc", json.loads(TARGET.read_text()))

    def test_wrong_expected_message_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Wrong LE SHA midstate/input"):
            validate(FIXTURES / "tier21-abc", b"xyz", json.loads(TARGET.read_text()))


if __name__ == "__main__":
    unittest.main()
