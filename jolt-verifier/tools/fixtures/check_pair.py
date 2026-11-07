#!/usr/bin/env python3
"""Check two exported fixtures share one exact scalar AST and program configuration.

This checks export consistency, not cryptographic validity or circuit satisfaction.
"""

import argparse
import hashlib
import json
from pathlib import Path

from prepare_upstream import REVISION


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(directory):
    def read_json(name):
        return json.loads((directory / name).read_text())

    full = read_json("full-proof.json")
    require(full["schema"] == "jolt-dory-fixture-v1", "Wrong fixture schema")
    require(full["upstream_commit"] == REVISION, "Wrong upstream revision")
    require(
        full["transcript"] == "poseidon"
        and full["pcs"] == "dory-pcs-0.3.0"
        and full["zk"] is False,
        "Wrong protocol",
    )
    require(
        full["native_checks"]
        == {
            "original": True,
            "pcs_tamper_rejected": True,
            "claim_tamper_rejected": True,
            "io_tamper_rejected": True,
        },
        "Missing successful native checks",
    )
    witness = read_json("scalar-witness.json")
    require(bool(witness), "Empty scalar witness")
    require(
        all(record["field"] == "Fr" for record in witness.values()),
        "Unsupported scalar witness field",
    )
    return full, read_json("stages_bundle.json"), witness


def check_pair(first, second):
    require(
        first.resolve() != second.resolve(), "Two distinct fixture directories required"
    )
    a, ast_a, witness_a = load(first)
    b, ast_b, witness_b = load(second)
    require(a["shape"] == b["shape"], "Proof configuration or shape differs")
    require(a["verifier_setup"] == b["verifier_setup"], "Verifier setup differs")
    require(
        (first / "preprocessing.bin").read_bytes()
        == (second / "preprocessing.bin").read_bytes(),
        "Program preprocessing differs",
    )
    require(ast_a == ast_b, "Scalar AST differs; cannot reuse one fixed circuit")
    metadata = lambda witness: {
        key: (record["name"], record["field"]) for key, record in witness.items()
    }
    require(
        metadata(witness_a) == metadata(witness_b), "Witness variable shape differs"
    )
    require(
        a["program_io"]["inputs_hex"] != b["program_io"]["inputs_hex"],
        "Program inputs must differ",
    )
    require(
        (first / "proof.bin").read_bytes() != (second / "proof.bin").read_bytes(),
        "Proof bytes must differ",
    )
    require(witness_a != witness_b, "Scalar witness values must differ")
    normalized = json.dumps(ast_a, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": "jolt-fixture-pair-v1",
        "ast_sha256": hashlib.sha256(normalized).hexdigest(),
        "shape": a["shape"],
        "scalar_variables": len(witness_a),
        "check": "export-consistency-only",
        "circuit_verification": "not-performed",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    args = parser.parse_args()
    print(json.dumps(check_pair(args.first, args.second), indent=2, sort_keys=True))
