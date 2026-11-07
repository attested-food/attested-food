#!/usr/bin/env python3
"""Generate our Poseidon3 circuit from historical Jolt's numeric parameter data.

The Go input is parsed as text and is never executed. No third-party circuit code
is included. This matches the optimized t=4, RF=8, RP=56 permutation.
"""

import argparse
import hashlib
from pathlib import Path
import re

from ast_to_circom import FR, PIN


def parameters(text):
    arrays = {"cConstants": [None] * 88, "sConstants": [None] * 392}
    matrices = {
        "mMatrix": [[None] * 4 for _ in range(4)],
        "pMatrix": [[None] * 4 for _ in range(4)],
    }
    pattern = r'(cConstants|sConstants|mMatrix|pMatrix)\[(\d+)\](?:\[(\d+)\])?, _ = new\(big.Int\).SetString\("(\d+)", 10\)'
    for name, row, col, raw in re.findall(pattern, text):
        value = int(raw)
        if not 0 <= value < FR:
            raise ValueError("noncanonical Poseidon constant")
        target = matrices[name][int(row)] if col else arrays[name]
        index = int(col) if col else int(row)
        if target[index] is not None:
            raise ValueError("duplicate Poseidon constant")
        target[index] = value
    if any(v is None for a in arrays.values() for v in a) or any(
        v is None for m in matrices.values() for a in m for v in a
    ):
        raise ValueError("missing Poseidon constants")
    return (
        arrays["cConstants"],
        arrays["sConstants"],
        matrices["mMatrix"],
        matrices["pMatrix"],
    )


def generate(text):
    c, s, m, p = parameters(text)
    lines = [
        "pragma circom 2.2.3;",
        "",
        f"// Numeric parameters: a16z/jolt {PIN}.",
        f"// constants.go SHA256: {hashlib.sha256(text.encode()).hexdigest()}",
        "template Poseidon3() {",
        "    signal input in[3];",
        "    signal output out;",
    ]
    serial = 0

    def bind(expression):
        nonlocal serial
        name = f"p{serial}"
        serial += 1
        lines.append(f"    signal {name};")
        lines.append(f"    {name} <== {expression};")
        return name

    def exp5(x):
        x2 = bind(f"{x} * {x}")
        x4 = bind(f"{x2} * {x2}")
        return bind(f"{x4} * {x}")

    def mix(state, matrix):
        return [
            bind(" + ".join(f"{matrix[j][i]} * {state[j]}" for j in range(4)))
            for i in range(4)
        ]

    def ark(state, offset):
        return [bind(f"{x} + {c[offset + i]}") for i, x in enumerate(state)]

    state = ark(["0", "in[0]", "in[1]", "in[2]"], 0)
    for r in range(3):
        state = mix(ark([exp5(x) for x in state], (r + 1) * 4), m)
    state = mix(ark([exp5(x) for x in state], 16), p)
    for r in range(56):
        first = bind(f"{exp5(state[0])} + {c[20 + r]}")
        state[0] = first
        next_first = bind(" + ".join(f"{s[7 * r + j]} * {state[j]}" for j in range(4)))
        state = [next_first] + [
            bind(f"{state[k]} + {first} * {s[7 * r + 3 + k]}") for k in range(1, 4)
        ]
    for r in range(3):
        state = mix(ark([exp5(x) for x in state], 76 + 4 * r), m)
    state = mix([exp5(x) for x in state], m)
    lines.extend([f"    out <== {state[0]};", "}"])
    return "\n".join(lines) + "\n"


def reference(text, inputs):
    """Integer reference for differential tests, not an acceptance oracle."""
    c, s, m, p = parameters(text)

    def mix(state, matrix):
        return [sum(matrix[j][i] * state[j] for j in range(4)) % FR for i in range(4)]

    def full(state, offset, matrix):
        return mix(
            [(pow(x, 5, FR) + c[offset + i]) % FR for i, x in enumerate(state)], matrix
        )

    state = [(x + c[i]) % FR for i, x in enumerate([0] + list(inputs))]
    for r in range(3):
        state = full(state, 4 * (r + 1), m)
    state = full(state, 16, p)
    for r in range(56):
        state[0] = (pow(state[0], 5, FR) + c[20 + r]) % FR
        state = [sum(s[7 * r + j] * state[j] for j in range(4)) % FR] + [
            (state[k] + state[0] * s[7 * r + 3 + k]) % FR for k in range(1, 4)
        ]
    for r in range(3):
        state = full(state, 76 + 4 * r, m)
    return mix([pow(x, 5, FR) for x in state], m)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("constants_go", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--sha256", required=True, help="expected hash of the inspected constants.go"
    )
    args = parser.parse_args()
    raw = args.constants_go.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.sha256:
        parser.error("constants.go digest mismatch")
    args.output.write_text(generate(raw.decode()))


if __name__ == "__main__":
    main()
