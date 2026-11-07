#!/usr/bin/env python3
"""Map the native export to scalar circuit inputs, not a complete Jolt witness."""

import argparse
import json
import re
from pathlib import Path

PIN = "ad03c835f5f7e152b625543c488eec446e3206c0"
FR = 21888242871839275222246405745257275088548364400416034343698204186575808495617


def scalar_inputs(manifest, witness):
    if manifest.get("protocol_pin") != PIN:
        raise ValueError("Unexpected Jolt protocol pin")
    if (
        manifest.get("template") != "JoltScalarStages"
        or manifest.get("complete_jolt_verifier") is not False
        or manifest.get("pcs_verified") is not False
    ):
        raise ValueError(
            "This adapter supports only the explicitly partial scalar circuit"
        )
    inputs = manifest.get("inputs")
    if not isinstance(inputs, dict) or not inputs:
        raise ValueError("Missing scalar input schema")
    if not isinstance(witness, dict):
        raise ValueError("Expected an indexed scalar witness object")
    expected = set()
    result = {}
    for signal, name in inputs.items():
        if (
            not isinstance(signal, str)
            or re.fullmatch(r"v(0|[1-9][0-9]*)", signal) is None
        ):
            raise ValueError(f"Invalid scalar signal: {signal!r}")
        index = signal[1:]
        expected.add(index)
        item = witness.get(index)
        if not isinstance(item, dict):
            raise ValueError(f"Missing scalar witness {index}")
        if item.get("name") != name or not isinstance(name, str):
            raise ValueError(f"Witness name mismatch at {index}")
        if item.get("field") != "Fr":
            raise ValueError(f"Nonnative witness {index} cannot be reduced into Fr")
        value = item.get("value")
        if not isinstance(value, str) or re.fullmatch(r"0|[1-9][0-9]*", value) is None:
            raise ValueError(f"Witness {index} must be a canonical decimal string")
        if int(value) >= FR:
            raise ValueError(f"Witness {index} is outside Fr")
        result[signal] = value
    if set(witness) != expected:
        raise ValueError("Witness indices do not match circuit input schema")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("scalar_witness", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--acknowledge-scalar-only",
        required=True,
        action="store_true",
        help="The resulting inputs do not include Dory PCS verification",
    )
    args = parser.parse_args()
    result = scalar_inputs(
        json.loads(args.manifest.read_text()),
        json.loads(args.scalar_witness.read_text()),
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
