#!/usr/bin/env python3
"""Test the source-only patcher against a pristine pinned upstream checkout."""

import argparse
from contextlib import redirect_stdout
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_upstream as exporter

UPSTREAM = None


class SourcePatcherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for relative, digest in exporter.HASHES.items():
            data = (UPSTREAM / relative).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        self.revision = patch.object(
            exporter.subprocess, "check_output", return_value=exporter.REVISION + "\n"
        )
        self.revision.start()
        self.addCleanup(self.revision.stop)

    def prepare(self):
        with redirect_stdout(io.StringIO()):
            exporter.prepare(self.root)

    def assert_pristine(self):
        for relative, digest in exporter.HASHES.items():
            self.assertEqual(
                hashlib.sha256((self.root / relative).read_bytes()).hexdigest(), digest
            )
        self.assertFalse((self.root / "transpiler/src/export_fixture.rs").exists())

    def test_export_patches_all_required_boundaries(self):
        self.prepare()
        main = (self.root / "transpiler/src/main.rs").read_text()
        self.assertIn("mod export_fixture;", main)
        self.assertLess(
            main.index("export_fixture::export("), main.index("symbolize_proof::<")
        )
        self.assertLess(
            main.index('join("scalar-witness.json")'),
            main.index("match args.target {\n        TranspilationTarget::Gnark => {"),
        )
        self.assertIn('panic!("Missing witness {idx}: {name}")', main)
        fibonacci = (self.root / "examples/fibonacci/src/main.rs").read_text()
        self.assertIn("prove_fib(input)", fibonacci)
        self.assertIn("verify_fib(input, output, io_device.panic, proof)", fibonacci)
        self.assertIn("guest::trace_fib_to_file(trace_file, input)", fibonacci)
        self.assertIn(
            'assert!(is_valid, "Native SDK verification rejected proof")', fibonacci
        )
        pcs = (
            self.root / "jolt-core/src/poly/commitment/dory/commitment_scheme.rs"
        ).read_text()
        self.assertLess(
            pcs.index('join("transcript.bin")'), pcs.index("dory::verify::<")
        )
        self.assertIn(".downcast_ref::<crate::transcripts::PoseidonTranscript>()", pcs)
        self.assertEqual(
            (self.root / "transpiler/src/export_fixture.rs").read_bytes(),
            Path(exporter.__file__).with_name("export_fixture.rs").read_bytes(),
        )

    def test_wrong_revision_is_rejected_without_writes(self):
        with patch.object(
            exporter.subprocess, "check_output", return_value="deadbeef\n"
        ):
            with self.assertRaisesRegex(ValueError, "Wrong upstream revision"):
                self.prepare()
        self.assert_pristine()

    def test_late_source_mismatch_does_not_partially_patch(self):
        relative = list(exporter.HASHES)[-1]
        with (self.root / relative).open("a") as stream:
            stream.write("\n// changed source\n")
        before = {path: path.read_bytes() for path in self.root.rglob("*.rs")}
        with self.assertRaisesRegex(ValueError, "Source changed"):
            self.prepare()
        self.assertEqual(
            before, {path: path.read_bytes() for path in self.root.rglob("*.rs")}
        )

    def test_existing_exporter_is_not_overwritten(self):
        target = self.root / "transpiler/src/export_fixture.rs"
        target.write_text("existing source\n")
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            self.prepare()
        self.assertEqual(target.read_text(), "existing source\n")
        target.unlink()
        self.assert_pristine()

    def test_second_application_is_rejected_without_writes(self):
        self.prepare()
        before = {path: path.read_bytes() for path in self.root.rglob("*.rs")}
        with self.assertRaisesRegex(ValueError, "Source changed"):
            self.prepare()
        self.assertEqual(
            before, {path: path.read_bytes() for path in self.root.rglob("*.rs")}
        )

    def test_ambiguous_source_anchor_is_rejected(self):
        for source in ("absent", "anchor anchor"):
            with self.assertRaisesRegex(ValueError, "Expected one source anchor"):
                exporter.replace_once(source, "anchor", "replacement")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", required=True, type=Path)
    args, remaining = parser.parse_known_args()
    UPSTREAM = args.upstream.resolve()
    unittest.main(argv=[__file__, *remaining])
