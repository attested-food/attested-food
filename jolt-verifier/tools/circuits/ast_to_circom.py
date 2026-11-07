#!/usr/bin/env python3
"""Compile the historical Jolt scalar AST. This is not a complete Jolt verifier."""

import argparse
import hashlib
import json
from pathlib import Path

FR = 21888242871839275222246405745257275088548364400416034343698204186575808495617
PIN = "ad03c835f5f7e152b625543c488eec446e3206c0"


def variant(value):
    if not isinstance(value, dict) or len(value) != 1:
        raise ValueError(f"expected externally tagged enum, got {value!r}")
    return next(iter(value.items()))


def integer(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("expected an integer")
    return value


class Generator:
    def __init__(self, bundle, public_indices, exports=(), poseidon_include=None):
        self.nodes = bundle["nodes"]
        self.constraints = bundle["constraints"]
        self.inputs = {}
        names = set()
        for item in bundle["inputs"]:
            index = integer(item["index"])
            if index < 0 or index in self.inputs:
                raise ValueError("negative or duplicate input index")
            if item.get("target_field", "Fr") != "Fr":
                raise ValueError(
                    "Fq AST inputs require nonnative constraints, not Fr reduction"
                )
            if not isinstance(item["name"], str) or item["name"] in names:
                raise ValueError("invalid or duplicate input name")
            names.add(item["name"])
            self.inputs[index] = item
        self.public = sorted(set(integer(i) for i in public_indices))
        if any(i not in self.inputs for i in self.public):
            raise ValueError("public index is not an AST input")
        self.exports = [integer(i) for i in exports]
        self.poseidon_include = poseidon_include
        self.lines = []
        self.values = {}
        self.used_inputs = set()
        self.hash_count = 0
        self.transform_count = 0

    def atom(self, atom):
        tag, value = variant(atom)
        if tag == "Var":
            value = integer(value)
            if value not in self.inputs:
                raise ValueError(f"undeclared Var({value})")
            self.used_inputs.add(value)
            return f"v{value}"
        if tag == "Scalar":
            if not isinstance(value, list) or len(value) != 4:
                raise ValueError("Scalar requires four little-endian u64 limbs")
            if any(integer(limb) < 0 or limb >= 2**64 for limb in value):
                raise ValueError("invalid u64 limb")
            return str(sum(limb << (64 * i) for i, limb in enumerate(value)) % FR)
        raise ValueError(f"unsupported atom {tag}")

    def edge(self, edge):
        tag, value = variant(edge)
        if tag == "Atom":
            return self.atom(value)
        if tag == "NodeRef":
            return self.values[integer(value)]
        raise ValueError(f"unsupported edge {tag}")

    def dependencies(self, index):
        if index < 0 or index >= len(self.nodes):
            raise ValueError(f"invalid node reference {index}")
        tag, value = variant(self.nodes[index])
        if tag == "Atom":
            self.atom(value)
            return []
        if tag in ("Add", "Sub", "Mul", "Div"):
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError(f"{tag} requires two edges")
            edges = value
        elif tag in (
            "Neg",
            "Inv",
            "ByteReverse",
            "Truncate128Reverse",
            "Truncate128",
            "AppendU64Transform",
        ):
            edges = [value]
        elif tag == "TranscriptHash":
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError("TranscriptHash requires data, state, counter")
            backend, data = variant(value[0])
            if backend != "Poseidon":
                raise ValueError(f"unsupported transcript backend {backend}")
            if not self.poseidon_include:
                raise ValueError("Poseidon nodes require a fixed Poseidon3 include")
            edges = [data, value[1], value[2]]
        else:
            raise ValueError(f"unsupported AST node {tag}")
        result = []
        for edge in edges:
            kind, child = variant(edge)
            if kind == "NodeRef":
                result.append(integer(child))
            elif kind == "Atom":
                self.atom(child)
            else:
                raise ValueError(f"unsupported edge {kind}")
        return result

    def visit(self, root):
        # Iterative DFS handles the deep transcript chains in real bundles.
        active = set()
        stack = [(integer(root), False)]
        while stack:
            index, ready = stack.pop()
            if index in self.values:
                continue
            if ready:
                self.emit(index)
                active.remove(index)
                continue
            if index in active:
                raise ValueError("cyclic AST")
            children = self.dependencies(index)
            active.add(index)
            stack.append((index, True))
            stack.extend((child, False) for child in reversed(children))

    def emit(self, index):
        tag, value = variant(self.nodes[index])
        out = f"n{index}"
        if tag == "Atom":
            self.values[index] = self.atom(value)
            return
        self.lines.append(f"    signal {out};")
        if tag in ("Add", "Sub", "Mul"):
            left, right = map(self.edge, value)
            op = {"Add": "+", "Sub": "-", "Mul": "*"}[tag]
            self.lines.append(f"    {out} <== {left} {op} {right};")
        elif tag == "Neg":
            self.lines.append(f"    {out} <== -{self.edge(value)};")
        elif tag in ("Inv", "Div"):
            numerator, denominator = (
                ("1", self.edge(value))
                if tag == "Inv"
                else tuple(map(self.edge, value))
            )
            # A separate nonzero constraint also rejects 0/0 in Div.
            self.lines.extend(
                [
                    f"    signal inv{index};",
                    f"    inv{index} <-- 1 / {denominator};",
                    f"    inv{index} * {denominator} === 1;",
                    f"    {out} <== {numerator} * inv{index};",
                ]
            )
        elif tag == "TranscriptHash":
            _, data = variant(value[0])
            args = [self.edge(value[1]), self.edge(value[2]), self.edge(data)]
            self.lines.append(f"    component h{index} = Poseidon3();")
            for i, arg in enumerate(args):
                self.lines.append(f"    h{index}.in[{i}] <== {arg};")
            self.lines.append(f"    {out} <== h{index}.out;")
            self.hash_count += 1
        else:
            mode = {
                "ByteReverse": 0,
                "Truncate128Reverse": 1,
                "Truncate128": 2,
                "AppendU64Transform": 3,
            }[tag]
            self.lines.extend(
                [
                    f"    component t{index} = TranscriptTransform({mode});",
                    f"    t{index}.in <== {self.edge(value)};",
                    f"    {out} <== t{index}.out;",
                ]
            )
            self.transform_count += 1
        self.values[index] = out

    def generate(self, standalone=False):
        if not self.constraints:
            raise ValueError("empty scalar constraint set")
        assertions = []
        by_name = {item["name"]: index for index, item in self.inputs.items()}
        for constraint in self.constraints:
            self.visit(constraint["root"])
            lhs = self.values[constraint["root"]]
            assertion = constraint["assertion"]
            if assertion == "EqualZero":
                rhs = "0"
            else:
                tag, value = variant(assertion)
                if tag == "EqualNode":
                    self.visit(value)
                    rhs = self.values[value]
                elif tag == "EqualPublicInput":
                    name = value["name"]
                    if name not in by_name or by_name[name] not in self.public:
                        raise ValueError(
                            "EqualPublicInput must reference an explicitly public input"
                        )
                    rhs = f"v{by_name[name]}"
                    self.used_inputs.add(by_name[name])
                else:
                    raise ValueError(f"unsupported assertion {assertion}")
            assertions.append(f"    {lhs} === {rhs};")
        for index in self.exports:
            self.visit(index)
        # Unused inputs often signal a broken statement/proof binding.
        unused = sorted(set(self.inputs) - self.used_inputs)
        header = [
            "pragma circom 2.2.3;",
            "// Scalar stages only. Dory PCS is NOT verified by this template.",
            'include "transcript.circom";',
        ]
        if self.poseidon_include:
            if '"' in self.poseidon_include or "\n" in self.poseidon_include:
                raise ValueError("invalid include path")
            header.append(f'include "{self.poseidon_include}";')
        header.extend(["", "template JoltScalarStages() {"])
        header.extend(f"    signal input v{i};" for i in sorted(self.inputs))
        if self.exports:
            header.append(f"    signal output boundary[{len(self.exports)}];")
        tail = [
            f"    boundary[{i}] <== {self.values[node]};"
            for i, node in enumerate(self.exports)
        ]
        result = header + self.lines + assertions + tail + ["}"]
        if standalone:
            public = ", ".join(f"v{i}" for i in self.public)
            visibility = f" {{public [{public}]}}" if self.public else ""
            result.extend(["", f"component main{visibility} = JoltScalarStages();"])
        manifest = {
            "protocol_pin": PIN,
            "complete_jolt_verifier": False,
            "pcs_verified": False,
            "template": "JoltScalarStages",
            "public_indices": self.public,
            "inputs": {f"v{i}": self.inputs[i]["name"] for i in sorted(self.inputs)},
            "unused_inputs": unused,
            "boundary_node_ids": self.exports,
            "reachable_nodes": len(self.values),
            "assertions": len(assertions),
            "poseidon_hashes": self.hash_count,
            "transforms": self.transform_count,
        }
        return "\n".join(result) + "\n", manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--public-indices",
        required=True,
        type=Path,
        help="JSON list; do not trust historical WitnessType metadata",
    )
    parser.add_argument("--exports", type=Path, help="JSON node IDs to connect to PCS")
    parser.add_argument("--poseidon-include")
    parser.add_argument(
        "--standalone-scalar",
        action="store_true",
        help="emit scalar-only test main, never a full verifier",
    )
    args = parser.parse_args()
    raw = args.bundle.read_bytes()
    generator = Generator(
        json.loads(raw),
        json.loads(args.public_indices.read_text()),
        json.loads(args.exports.read_text()) if args.exports else [],
        args.poseidon_include,
    )
    source, manifest = generator.generate(args.standalone_scalar)
    manifest["bundle_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source)
    args.output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
