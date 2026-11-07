"""Uni-skip constraints and serialized native stage-1 scalar integration."""

import copy
import json
import os
from pathlib import Path
import random
import shutil
import sys
import tempfile
import unittest

from inputs import capture_inputs, export, parse_proof
from reference import P, chain_final, limbs, terminal, uniskip_evaluate, uniskip_sum

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/browser"
CAPTURES = Path(os.environ.get("BROWSER_STAGE1_CAPTURE_ROOT", FIXTURES))
sys.path.insert(0, str(ROOT / "tests"))
from circom_runner import ToolFailure, compile_circuit


def unpack(value):
    return int(value[0]) + 2**64 * int(value[1])


def fixture(name):
    proof = FIXTURES / name / "proof.json"
    trace = CAPTURES / name / "jolt-transcript.jsonl"
    return proof, trace


class ReaderTests(unittest.TestCase):
    def test_proof_only_export_and_validation(self):
        for name in ["tier21-abc", "tier21-def"]:
            path, _ = fixture(name)
            proof = json.loads(path.read_text())
            wire = parse_proof(proof)
            result = export(path)
            self.assertEqual(
                result["shape"], {"LOG_T": 13, "L": 28, "stored_per_round": 3}
            )
            self.assertEqual(len(result["inputs"]["openings"]), 35)
            self.assertNotIn("tau", result["inputs"])
            self.assertEqual(len(result["missing_inputs"]), 4)
            self.assertEqual(uniskip_sum(wire.coefficients), 0)
            for mutate in ["byte", "field", "rounds", "degree", "openings", "trace"]:
                changed = copy.deepcopy(proof)
                coeffs = changed["stages"]["stage1_uni_skip_first_round_proof"][
                    "Clear"
                ]["Full"]["round_polynomials"][0]["coefficients"]
                if mutate == "byte":
                    coeffs[0][0] = True
                elif mutate == "field":
                    coeffs[0] = list(P.to_bytes(16, "little"))
                elif mutate == "degree":
                    coeffs.append([0] * 16)
                elif mutate == "rounds":
                    changed["stages"]["stage1_sumcheck_proof"]["Clear"]["Compressed"][
                        "round_polynomials"
                    ].pop()
                elif mutate == "openings":
                    changed["claims"]["Clear"]["stage1"]["outer"][
                        "outer_remainder"
                    ].pop("pc")
                else:
                    changed["trace_length"] = 8193
                with self.assertRaises(ValueError):
                    parse_proof(changed)

    def test_native_capture_matches_integer_relations(self):
        for name in ["tier21-abc", "tier21-def"]:
            path, trace = fixture(name)
            if not trace.exists():
                self.skipTest(
                    "native outer capture unavailable; set BROWSER_STAGE1_CAPTURE_ROOT"
                )
            wire = parse_proof(json.loads(path.read_text()))
            events = [json.loads(line) for line in trace.read_text().splitlines()]
            data = capture_inputs(wire, events)
            challenge = unpack(data["uniskipChallenge"])
            self.assertEqual(
                uniskip_evaluate(wire.coefficients, challenge), wire.uniskip_output
            )
            coefficient = unpack(data["batchingCoefficient"])
            remainder = list(map(unpack, data["remainderChallenges"]))
            value = terminal(
                list(map(unpack, data["tau"])), challenge, remainder, wire.openings
            )
            self.assertEqual(
                chain_final(
                    coefficient * wire.uniskip_output % P, wire.compressed, remainder
                ),
                coefficient * value % P,
            )
            for kind in ["polynomial", "challenge", "opening", "count"]:
                changed = copy.deepcopy(events)
                if kind == "polynomial":
                    marker = next(
                        i
                        for i, e in enumerate(changed)
                        if e["op"] == "label_count"
                        and e["label_hex"] == b"uniskip_poly".hex()
                    )
                    changed[marker + 2]["payload_hex"] = "01" * 16
                elif kind == "challenge":
                    marker = next(e for e in changed if e["op"] == "decode_challenge")
                    marker["field_le_hex"] = "00" * 16
                elif kind == "opening":
                    marker = next(
                        i
                        for i, e in enumerate(changed)
                        if e["op"] == "label"
                        and e["label_hex"] == b"opening_claim".hex()
                    )
                    changed[marker + 2]["payload_hex"] = "00" * 16
                else:
                    marker = next(
                        e
                        for e in changed
                        if e["op"] == "label_count"
                        and e["label_hex"] == b"uniskip_poly".hex()
                    )
                    marker["count"] = 27
                with self.assertRaises(ValueError):
                    capture_inputs(wire, changed)


class UniskipCircuitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="browser-uniskip-")
        cls.directory = Path(cls.temp.name)
        cls.counter = 0
        cls.compiled = {}
        for lane, filenames in [
            ("browser", ["fp128.circom"]),
            ("browser-scalar", ["sumcheck.circom"]),
            ("browser-stage1", ["stage1.circom", "uniskip.circom"]),
        ]:
            destination = cls.directory / lane
            destination.mkdir()
            for filename in filenames:
                shutil.copyfile(
                    ROOT / "circuits" / lane / filename, destination / filename
                )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def compile(self, length, log_t=None):
        key = length, log_t
        if key not in self.compiled:
            name = f"uniskip-{length}" if log_t is None else f"clear-{log_t}-{length}"
            source = self.directory / f"{name}.circom"
            component = (
                f"BrowserStage1Uniskip({length})"
                if log_t is None
                else f"BrowserStage1Clear({log_t}, {length})"
            )
            source.write_text(
                'pragma circom 2.2.3;\ninclude "browser-stage1/uniskip.circom";\n'
                + f"component main = {component};\n"
            )
            self.compiled[key] = compile_circuit(
                source, self.directory / f"build-{name}"
            )
        return self.compiled[key]

    def check(self, circuit, inputs, valid=True):
        type(self).counter += 1
        directory = self.directory / f"case-{self.counter}"
        if valid:
            circuit.check(inputs, directory)
        else:
            with self.assertRaises(ToolFailure):
                circuit.check(inputs, directory)

    def data(self, coefficients, challenge):
        return dict(
            coefficients=list(map(limbs, coefficients)),
            challenge=limbs(challenge),
            outputClaim=limbs(uniskip_evaluate(coefficients, challenge)),
        )

    def test_small_shapes_and_edges(self):
        empty = self.compile(0)
        self.check(empty, self.data([], 17))
        changed = self.data([], 17)
        changed["outputClaim"] = limbs(1)
        self.check(empty, changed, False)
        constant = self.compile(1)
        self.check(constant, self.data([0], P - 1))
        self.check(constant, self.data([1], 0), False)
        cubic = self.compile(3)
        # 2*x - 1 sums to zero on {-4,...,5}; the last stored coefficient is zero.
        for challenge in [0, 1, P - 4, 5, P - 1]:
            self.check(cubic, self.data([P - 1, 2, 0], challenge))
        changed = self.data([P - 1, 2, 0], 17)
        changed["challenge"] = [str(P % 2**64), str(P // 2**64)]
        self.check(cubic, changed, False)

    def test_degree27_and_mutations(self):
        circuit = self.compile(28)
        rng = random.Random(127)
        coefficients = [rng.randrange(P) for _ in range(28)]
        coefficients[0] = 0
        coefficients[0] = -uniskip_sum(coefficients) * pow(10, -1, P) % P
        self.assertEqual(uniskip_sum(coefficients), 0)
        data = self.data(coefficients, 2**127)
        self.check(circuit, data)
        for key in ["outputClaim", "challenge"]:
            changed = copy.deepcopy(data)
            changed[key][0] = str(int(changed[key][0]) + 1)
            self.check(circuit, changed, False)
        changed = copy.deepcopy(data)
        changed["coefficients"][0] = limbs((coefficients[0] + 1) % P)
        self.check(circuit, changed, False)

    def test_native_pair_full_scalar_stage(self):
        circuit = None
        for name in ["tier21-abc", "tier21-def"]:
            path, trace = fixture(name)
            if not trace.exists():
                self.skipTest(
                    "native outer capture unavailable; set BROWSER_STAGE1_CAPTURE_ROOT"
                )
            result = export(path, trace)
            shape = result["shape"]
            current = self.compile(shape["L"], shape["LOG_T"])
            if circuit is not None:
                self.assertIs(circuit, current)
            circuit = current
            self.check(circuit, result["inputs"])
            changed = copy.deepcopy(result["inputs"])
            changed["uniskipOutputClaim"][0] = str(
                int(changed["uniskipOutputClaim"][0]) + 1
            )
            self.check(circuit, changed, False)
        changed = copy.deepcopy(result["inputs"])
        changed["compressed"][-1][0][0] = str(int(changed["compressed"][-1][0][0]) + 1)
        self.check(circuit, changed, False)


if __name__ == "__main__":
    unittest.main()
