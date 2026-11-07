"""Provenance-inventory tests; the dummy files are not proving artifacts."""

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "tools/pin_website.py"
SPEC = importlib.util.spec_from_file_location("pin_website", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WebsitePinTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="website-pin-")
        self.root = Path(self.temporary.name)
        self.assets = self.root / "frontend/static/vendor/jolt"
        for name in MODULE.REQUIRED_ASSETS:
            path = self.assets / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"inventory-test-only")

    def tearDown(self):
        self.temporary.cleanup()

    def test_hashes_required_assets(self):
        result = MODULE.inventory_assets(self.assets)
        self.assertEqual(set(result), set(MODULE.REQUIRED_ASSETS))
        self.assertEqual(
            result["worker.js"],
            {
                "sha256": hashlib.sha256(b"inventory-test-only").hexdigest(),
                "bytes": len(b"inventory-test-only"),
            },
        )

    def test_missing_asset_rejected(self):
        (self.assets / "equinox.elf").unlink()
        with self.assertRaisesRegex(ValueError, "Missing website prover asset"):
            MODULE.inventory_assets(self.assets)

    def test_escaping_symlink_rejected(self):
        outside = self.root / "outside.txt"
        outside.write_bytes(b"not-a-vendor-asset")
        (self.assets / "escape").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "escapes"):
            MODULE.inventory_assets(self.assets)

    def test_streaming_hash(self):
        data = b"0123456789abcdef" * 100000
        path = self.root / "large.bin"
        path.write_bytes(data)
        self.assertEqual(MODULE.file_digest(path), hashlib.sha256(data).hexdigest())

    def mock_git(self, root, *args):
        if args[0] == "rev-parse":
            return b"0123456789012345678901234567890123456789\n"
        if args[0] == "ls-tree":
            return b"guests/jolt/FORK_REV\n"
        if args[0] == "show":
            if args[1].endswith("frontend/src/lib/jolt.ts"):
                return b"const TIER = { shaChunk: 20, shaFinish: 21, extract: 31, tls: 33 };"
            if args[1].endswith("guests/jolt/FORK_REV"):
                return b"abcdef0123456789abcdef0123456789abcdef01\n"
            if args[1].endswith("guests/jolt/src/lib.rs"):
                entries = ",".join(
                    f"{key} = {value}" for key, value in MODULE.GUEST_CONFIG.items()
                )
                return f"#[jolt::provable({entries})]\nfn equinox".encode()
            return b"inventory-source-test-only"
        raise AssertionError(f"Unexpected command: {args}")

    def test_inventory_does_not_claim_verification(self):
        with patch.object(MODULE, "git", side_effect=self.mock_git):
            result = MODULE.pin(self.root, self.root, "HEAD")
        self.assertFalse(any(result["verification"].values()))
        self.assertEqual(result["guest"]["allowed_tiers"], MODULE.TIERS)

    def test_changed_tiers_rejected(self):
        def changed_git(root, *args):
            result = self.mock_git(root, *args)
            if args[0] == "show" and args[1].endswith("frontend/src/lib/jolt.ts"):
                return result.replace(b"shaChunk: 20", b"shaChunk: 2")
            return result

        with patch.object(MODULE, "git", side_effect=changed_git):
            with self.assertRaisesRegex(ValueError, "tier configuration differs"):
                MODULE.pin(self.root, self.root, "HEAD")

    def test_changed_guest_memory_rejected(self):
        def changed_git(root, *args):
            result = self.mock_git(root, *args)
            if args[0] == "show" and args[1].endswith("guests/jolt/src/lib.rs"):
                return result.replace(
                    b"max_input_size = 500000", b"max_input_size = 900000"
                )
            return result

        with patch.object(MODULE, "git", side_effect=changed_git):
            with self.assertRaisesRegex(ValueError, "memory configuration differs"):
                MODULE.pin(self.root, self.root, "HEAD")


if __name__ == "__main__":
    unittest.main()
