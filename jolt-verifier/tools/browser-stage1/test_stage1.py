"""Authored stage-1 scalar tests, not native proof or transcript tests."""

import copy
from pathlib import Path
import random
import shutil
import sys
import tempfile
import unittest

from reference import P, chain_final, lagrange, limbs, row_forms, terminal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from circom_runner import ToolFailure, compile_circuit


class IntegerTests(unittest.TestCase):
    def test_lagrange_nodes_and_partition(self):
        for i, point in enumerate(range(-4, 6)):
            self.assertEqual(lagrange(point % P), [int(j == i) for j in range(10)])
        for point in [0, 1, P - 1, 2**64, 2**127, 987654321]:
            self.assertEqual(sum(lagrange(point)) % P, 1)

    def test_affine_rows_and_subtraction_bias(self):
        a, b = row_forms([0] * 35)
        self.assertEqual(a, [0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0])
        self.assertEqual(b[8], -(2**64))
        self.assertEqual([b[i] for i in [11, 13, 16, 17, 18]], [-1, -4, -4, -1, 1])
        with self.assertRaises(ValueError):
            terminal([1], 2, [], [0] * 35)


class CircuitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="browser-stage1-")
        cls.directory = Path(cls.temp.name)
        for lane, filename in [
            ("browser", "fp128.circom"),
            ("browser-scalar", "sumcheck.circom"),
            ("browser-stage1", "stage1.circom"),
        ]:
            destination = cls.directory / lane
            destination.mkdir()
            shutil.copyfile(ROOT / "circuits" / lane / filename, destination / filename)
        cls.counter = 0
        cls.terminal = cls.compile(
            "terminal",
            """signal input tau[4][2];
    signal input uniskipChallenge[2];
    signal input remainderChallenges[3][2];
    signal input openings[35][2];
    signal input expected[2];
    signal input expectedPoint[3][2];
    component t = BrowserStage1Terminal(2);
    t.tau <== tau;
    t.uniskipChallenge <== uniskipChallenge;
    t.remainderChallenges <== remainderChallenges;
    t.openings <== openings;
    t.terminal === expected;
    t.openingPoint === expectedPoint;""",
        )
        cls.remainder = cls.compile(
            "remainder",
            """signal input tau[4][2];
    signal input uniskipChallenge[2];
    signal input uniskipOutputClaim[2];
    signal input batchingCoefficient[2];
    signal input remainderChallenges[3][2];
    signal input compressed[3][3][2];
    signal input openings[35][2];
    signal input expectedInitial[2];
    signal input expectedFinal[2];
    component s = BrowserStage1Remainder(2);
    s.tau <== tau;
    s.uniskipChallenge <== uniskipChallenge;
    s.uniskipOutputClaim <== uniskipOutputClaim;
    s.batchingCoefficient <== batchingCoefficient;
    s.remainderChallenges <== remainderChallenges;
    s.compressed <== compressed;
    s.openings <== openings;
    s.initialClaim === expectedInitial;
    s.expectedFinal === expectedFinal;
    s.uniskipInitialClaim[0] === 0;
    s.uniskipInitialClaim[1] === 0;""",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile(cls, name, body):
        source = cls.directory / f"{name}.circom"
        source.write_text(
            'pragma circom 2.2.3;\ninclude "browser-stage1/stage1.circom";\n'
            + "template Test() {\n    "
            + body
            + "\n}\ncomponent main = Test();\n"
        )
        return compile_circuit(source, cls.directory / f"build-{name}")

    def check(self, circuit, data, valid=True):
        type(self).counter += 1
        directory = self.directory / f"case-{self.counter}"
        if valid:
            circuit.check(data, directory)
        else:
            with self.assertRaises(ToolFailure):
                circuit.check(data, directory)

    def terminal_data(self, tau, uniskip, challenges, openings):
        return dict(
            tau=list(map(limbs, tau)),
            uniskipChallenge=limbs(uniskip),
            remainderChallenges=list(map(limbs, challenges)),
            openings=list(map(limbs, openings)),
            expected=limbs(terminal(tau, uniskip, challenges, openings)),
            expectedPoint=list(map(limbs, reversed(challenges))),
        )

    def test_terminal_edges(self):
        rng = random.Random(139)
        for uniskip, stream, high in [
            (P - 4, 0, P - 4),
            (5, 1, 5),
            (P - 1, P - 1, 2**127),
        ]:
            openings = [rng.randrange(P) for _ in range(35)]
            tau = [2, 3, P - 2, high]
            data = self.terminal_data(tau, uniskip, [stream, 17, 23], openings)
            self.check(self.terminal, data)
        self.check(
            self.terminal, self.terminal_data([1, 2, 3, 4], 17, [19, 23, 29], [0] * 35)
        )

    def test_terminal_mutations(self):
        data = self.terminal_data(
            [2, 3, 5, 7], 17, [19, 23, 29], [1000 + i for i in range(35)]
        )
        self.check(self.terminal, data)
        for key, index in [
            ("tau", 0),
            ("tau", 3),
            ("openings", 0),
            ("openings", 14),
            ("openings", 32),
            ("remainderChallenges", 0),
            ("remainderChallenges", 2),
            ("expectedPoint", 0),
        ]:
            mutated = copy.deepcopy(data)
            mutated[key][index][0] = str(int(mutated[key][index][0]) + 1)
            self.check(self.terminal, mutated, False)
        for key in ["uniskipChallenge", "expected"]:
            mutated = copy.deepcopy(data)
            mutated[key][0] = str(int(mutated[key][0]) + 1)
            self.check(self.terminal, mutated, False)
        # IsFirstInSequence is absent from these rows, but remains canonical.
        mutated = copy.deepcopy(data)
        mutated["openings"][33] = [str(P % 2**64), str(P // 2**64)]
        self.check(self.terminal, mutated, False)

    def remainder_data(self, coefficient=31):
        tau, uniskip, challenges = [2, 3, 5, 7], 17, [19, 23, 29]
        openings = [1000 + i for i in range(35)]
        uniskip_output = P - 11
        initial = coefficient * uniskip_output % P
        target = coefficient * terminal(tau, uniskip, challenges, openings) % P
        polynomials = [[13, 17, 19], [23, 29, 31]]
        running = chain_final(initial, polynomials, challenges[:2])
        r = challenges[-1]
        c0, c2 = 37, 41
        c3 = target - running * r - c0 * (1 - 2 * r) - c2 * (r**2 - r)
        c3 = c3 * pow(r**3 - r, -1, P) % P
        polynomials.append([c0, c2, c3])
        self.assertEqual(chain_final(initial, polynomials, challenges), target)
        return dict(
            tau=list(map(limbs, tau)),
            uniskipChallenge=limbs(uniskip),
            uniskipOutputClaim=limbs(uniskip_output),
            batchingCoefficient=limbs(coefficient),
            remainderChallenges=list(map(limbs, challenges)),
            compressed=[[limbs(c) for c in poly] for poly in polynomials],
            openings=list(map(limbs, openings)),
            expectedInitial=limbs(initial),
            expectedFinal=limbs(target),
        )

    def test_remainder_wiring_and_mutations(self):
        data = self.remainder_data()
        self.check(self.remainder, data)
        for key in [
            "uniskipOutputClaim",
            "batchingCoefficient",
            "expectedInitial",
            "expectedFinal",
        ]:
            mutated = copy.deepcopy(data)
            mutated[key][0] = str(int(mutated[key][0]) + 1)
            self.check(self.remainder, mutated, False)
        mutated = copy.deepcopy(data)
        mutated["compressed"][1][0] = limbs(24)
        self.check(self.remainder, mutated, False)
        mutated = copy.deepcopy(data)
        mutated["openings"][0] = limbs(1001)
        self.check(self.remainder, mutated, False)

    def test_zero_batching_coefficient(self):
        # Native arithmetic allows zero; transcript binding is not replaced by nonzero checks.
        self.check(self.remainder, self.remainder_data(0))


if __name__ == "__main__":
    unittest.main()
