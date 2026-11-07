#!/usr/bin/env python3
"""Regression checks using the committed genuine fixtures, not synthetic proofs."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from replay_outer import replay
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

    def test_outer_transcripts_replay_and_bridge_to_akita(self):
        for name in ["tier21-abc", "tier21-def"]:
            directory = FIXTURES / name
            result = replay(directory / "jolt-transcript.jsonl")
            self.assertEqual(
                result,
                json.loads((directory / "jolt-transcript-replay.json").read_text()),
            )
            self.assertTrue(result["nested_bridge_checked"])
            self.assertEqual(result["rounds"], 2202)
            self.assertEqual(len(result["fields"]), 334)

    def test_mutated_outer_absorb_is_rejected(self):
        self.check_outer_mutation(
            "absorb", "payload_hex", "ff", "Blake2b transition differs"
        )

    def test_mutated_decoded_challenge_is_rejected(self):
        self.check_outer_mutation(
            "decode_challenge",
            "field_le_hex",
            "00" * 16,
            "Challenge field decoding differs",
        )

    def check_outer_mutation(self, operation, key, value, error):
        events = [
            json.loads(line)
            for line in (FIXTURES / "tier21-abc/jolt-transcript.jsonl")
            .read_text()
            .splitlines()
        ]
        event = next(event for event in events if event["op"] == operation)
        event[key] = value
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in events))
            with self.assertRaisesRegex(ValueError, error):
                replay(path)


if __name__ == "__main__":
    unittest.main()
