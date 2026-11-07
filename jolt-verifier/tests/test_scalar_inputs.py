"""Schema tests only; these objects are not Jolt proof fixtures."""

import copy
import importlib.util
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "scalar_inputs.py"
SPEC = importlib.util.spec_from_file_location("scalar_inputs", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ScalarInputTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "protocol_pin": MODULE.PIN,
            "template": "JoltScalarStages",
            "complete_jolt_verifier": False,
            "pcs_verified": False,
            "inputs": {"v0": "example_a", "v3": "example_b"},
        }
        self.witness = {
            "0": {"name": "example_a", "field": "Fr", "value": "0"},
            "3": {"name": "example_b", "field": "Fr", "value": str(MODULE.FR - 1)},
        }

    def test_maps_indices_without_changing_values(self):
        self.assertEqual(
            MODULE.scalar_inputs(self.manifest, self.witness),
            {"v0": "0", "v3": str(MODULE.FR - 1)},
        )

    def test_rejects_wrong_protocol(self):
        self.manifest["protocol_pin"] = "unapproved"
        with self.assertRaises(ValueError):
            MODULE.scalar_inputs(self.manifest, self.witness)

    def test_rejects_full_verifier_claim(self):
        self.manifest["complete_jolt_verifier"] = True
        with self.assertRaises(ValueError):
            MODULE.scalar_inputs(self.manifest, self.witness)

    def test_rejects_missing_or_extra_indices(self):
        for witness in (
            {"0": self.witness["0"]},
            {**self.witness, "1": self.witness["0"]},
        ):
            with self.subTest(witness=witness), self.assertRaises(ValueError):
                MODULE.scalar_inputs(self.manifest, witness)

    def test_rejects_nonnative_field(self):
        self.witness["0"]["field"] = "Fq"
        with self.assertRaises(ValueError):
            MODULE.scalar_inputs(self.manifest, self.witness)

    def test_rejects_mismatched_names(self):
        self.witness["0"]["name"] = "different_input"
        with self.assertRaises(ValueError):
            MODULE.scalar_inputs(self.manifest, self.witness)

    def test_rejects_noncanonical_values(self):
        for value in (True, 0, "-1", "+1", "01", " 1", str(MODULE.FR)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                witness = copy.deepcopy(self.witness)
                witness["0"]["value"] = value
                MODULE.scalar_inputs(self.manifest, witness)

    def test_rejects_invalid_signal_names(self):
        for name in ("v01", "v-1", "other"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                manifest = copy.deepcopy(self.manifest)
                manifest["inputs"] = {name: "example_a"}
                MODULE.scalar_inputs(manifest, self.witness)


if __name__ == "__main__":
    unittest.main()
