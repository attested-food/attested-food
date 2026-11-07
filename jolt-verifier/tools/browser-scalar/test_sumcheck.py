"""Authored scalar fixtures only. These are not genuine Jolt proof tests."""

import copy
import os
from pathlib import Path
import random
import shutil
import struct
import sys
import tempfile
import unittest

from reference import P, batch_initial, evaluate, limbs, reconstruct, reduce_claim

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from circom_runner import ToolFailure, compile_circuit, run, tool


class IntegerReferenceTests(unittest.TestCase):
    def test_reconstruction(self):
        rng = random.Random(390518)
        for degree in range(1, 33):
            for challenge in [0, 1, P - 1, rng.randrange(P)]:
                coefficients = [rng.randrange(P) for _ in range(degree + 1)]
                claim = (coefficients[0] + sum(coefficients)) % P
                stored = [coefficients[0], *coefficients[2:]]
                self.assertEqual(reconstruct(stored, claim), coefficients)
                self.assertEqual(
                    evaluate(reconstruct(stored, claim), challenge),
                    sum(c * challenge**i for i, c in enumerate(coefficients)) % P,
                )
        with self.assertRaises(ValueError):
            reconstruct([], 0)
        with self.assertRaises(ValueError):
            reconstruct([P], 0)


class CircuitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="browser-scalar-")
        cls.directory = Path(cls.temp.name)
        source = Path(
            os.environ.get(
                "BROWSER_FP128_SOURCE", ROOT / "circuits/browser/fp128.circom"
            )
        )
        if not source.is_file():
            raise RuntimeError("missing core fp128.circom; set BROWSER_FP128_SOURCE")
        (cls.directory / "browser").mkdir()
        shutil.copyfile(source, cls.directory / "browser/fp128.circom")
        (cls.directory / "browser-scalar").mkdir()
        shutil.copyfile(
            ROOT / "circuits/browser-scalar/sumcheck.circom",
            cls.directory / "browser-scalar/sumcheck.circom",
        )
        cls.counter = 0
        cls.poly = cls.compile(
            "poly",
            """signal input compressed[3][2];
    signal input claim[2];
    signal input challenge[2];
    signal input expectedCoefficients[4][2];
    signal input expected[2];
    signal output out[2];
    component p = BrowserCompressedUniPoly(3);
    p.compressed <== compressed;
    p.claim <== claim;
    p.challenge <== challenge;
    p.coefficients === expectedCoefficients;
    p.out === expected;
    out <== p.out;""",
        )
        cls.chain = cls.compile(
            "chain",
            """signal input initialClaim[2];
    signal input compressed[3][3][2];
    signal input challenges[3][2];
    signal input expectedFinal[2];
    component c = BrowserCompressedSumcheck(3, 3, [1, 2, 3]);
    c.initialClaim <== initialClaim;
    c.compressed <== compressed;
    c.challenges <== challenges;
    c.expectedFinal <== expectedFinal;""",
        )
        cls.zero = cls.compile(
            "zero",
            """signal input initialClaim[2];
    signal input expectedFinal[2];
    component c = BrowserCompressedSumcheck(0, 1, [0]);
    c.initialClaim <== initialClaim;
    c.expectedFinal <== expectedFinal;""",
        )
        cls.batch = cls.compile(
            "batch",
            """signal input values[3][2];
    signal input weights[3][2];
    signal input expected[2];
    signal input finalValues[3][2];
    signal input finalExpected[2];
    component b = BrowserSumcheckBatchInitial(3, 255, [255, 254, 0]);
    component f = BrowserSumcheckWeightedSum(3);
    b.inputClaims <== values;
    b.weights <== weights;
    b.out === expected;
    f.values <== finalValues;
    f.weights <== weights;
    f.out === finalExpected;""",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile(cls, name, body):
        source = cls.directory / f"{name}.circom"
        source.write_text(
            'pragma circom 2.2.3;\ninclude "browser-scalar/sumcheck.circom";\n'
            + "template Test() {\n    "
            + body
            + "\n}\ncomponent main = Test();\n"
        )
        return compile_circuit(source, cls.directory / f"build-{name}")

    def check(self, circuit, inputs, valid=True):
        type(self).counter += 1
        directory = self.directory / f"case-{self.counter}"
        if valid:
            circuit.check(inputs, directory)
        else:
            with self.assertRaises(ToolFailure):
                circuit.check(inputs, directory)
        return directory

    def poly_input(self, stored, claim, challenge):
        coefficients = reconstruct(stored, claim)
        return dict(
            compressed=list(map(limbs, stored)),
            claim=limbs(claim),
            challenge=limbs(challenge),
            expectedCoefficients=list(map(limbs, coefficients)),
            expected=limbs(evaluate(coefficients, challenge)),
        )

    def test_polynomial_edges_and_mutations(self):
        for stored, claim, challenge in [
            ([0, 0, 0], 0, 0),
            ([P - 1, P - 1, P - 1], P - 1, P - 1),
            ([2**64 - 1, 2**64, P - 2], 17, 1),
            ([17, 23, 42], P - 3, 2**127),
        ]:
            self.check(self.poly, self.poly_input(stored, claim, challenge))
        original = self.poly_input([17, 23, 42], P - 3, 2**127)
        for key in [
            "compressed",
            "claim",
            "challenge",
            "expectedCoefficients",
            "expected",
        ]:
            mutated = copy.deepcopy(original)
            if key in ["compressed", "expectedCoefficients"]:
                mutated[key][0][0] = str(int(mutated[key][0][0]) + 1)
            else:
                mutated[key][0] = str(int(mutated[key][0]) + 1)
            self.check(self.poly, mutated, False)
        mutated = copy.deepcopy(original)
        mutated["challenge"] = [str(P & (2**64 - 1)), str(P >> 64)]
        self.check(self.poly, mutated, False)
        mutated = copy.deepcopy(original)
        mutated["compressed"][0] = [str(2**64), "0"]
        self.check(self.poly, mutated, False)

    def test_r1cs_witness_mutation(self):
        directory = self.check(self.poly, self.poly_input([17, 23, 42], 123, 77))
        witness = bytearray((directory / "witness.wtns").read_bytes())
        offset = 12
        while offset < len(witness):
            section, size = struct.unpack_from("<IQ", witness, offset)
            offset += 12
            if section == 2:
                # BN254 witness field size is 32 bytes. Index 1 is main.out[0].
                index = offset + 32
                value = int.from_bytes(witness[index : index + 32], "little")
                witness[index : index + 32] = (value + 1).to_bytes(32, "little")
                break
            offset += size
        else:
            self.fail("missing witness section")
        path = directory / "mutated.wtns"
        path.write_bytes(witness)
        try:
            result = run(
                [tool("snarkjs"), "wtns", "check", str(self.poly.r1cs), str(path)]
            )
        except ToolFailure:
            return
        self.assertNotIn("WITNESS IS CORRECT", result.stdout + result.stderr)

    def test_round_chain_and_padding(self):
        polynomials = [[P - 1], [19, P - 2], [0, 23, 42]]
        challenges = [P - 1, 0, 2**64]
        claims = reduce_claim(123, polynomials, challenges)
        data = dict(
            initialClaim=limbs(123),
            compressed=[list(map(limbs, p + [0] * (3 - len(p)))) for p in polynomials],
            challenges=list(map(limbs, challenges)),
            expectedFinal=limbs(claims[-1]),
        )
        self.check(self.chain, data)
        mutated = copy.deepcopy(data)
        mutated["compressed"][0][1] = limbs(1)
        self.check(self.chain, mutated, False)
        mutated = copy.deepcopy(data)
        mutated["compressed"][1][0] = limbs(20)
        self.check(self.chain, mutated, False)
        mutated = copy.deepcopy(data)
        mutated["expectedFinal"] = limbs((claims[-1] + 1) % P)
        self.check(self.chain, mutated, False)

    def test_zero_rounds(self):
        self.check(
            self.zero, dict(initialClaim=limbs(P - 1), expectedFinal=limbs(P - 1))
        )
        self.check(
            self.zero, dict(initialClaim=limbs(0), expectedFinal=limbs(1)), False
        )

    def test_batch_padding_and_final_fold(self):
        values, weights = [P - 1, 2**64, 17], [19, P - 2, 23]
        expected = batch_initial(values, weights, 255, [255, 254, 0])
        final_values = [42, 0, P - 1]
        data = dict(
            values=list(map(limbs, values)),
            weights=list(map(limbs, weights)),
            expected=limbs(expected),
            finalValues=list(map(limbs, final_values)),
            finalExpected=limbs(sum(v * w for v, w in zip(final_values, weights)) % P),
        )
        self.check(self.batch, data)
        for key in ["values", "weights", "finalValues"]:
            mutated = copy.deepcopy(data)
            mutated[key][0] = limbs(1)
            self.check(self.batch, mutated, False)


if __name__ == "__main__":
    unittest.main()
