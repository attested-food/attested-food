#!/usr/bin/env python3
"""Measure standalone components, not a complete website Jolt verifier."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

COMPONENTS = {
    "canonical": ("fp128.circom", "BrowserFp128Canonical()"),
    "add": ("fp128.circom", "BrowserFp128Add()"),
    "sub": ("fp128.circom", "BrowserFp128Sub()"),
    "mul": ("fp128.circom", "BrowserFp128Mul()"),
    "inverse": ("fp128.circom", "BrowserFp128InverseCheck()"),
    "blake256_80_bytes": ("blake2b.circom", "BrowserBlake2b(80,32)"),
    "blake512_128_bytes": ("blake2b.circom", "BrowserBlake2b(128,64)"),
}


def measure(circuits, output):
    output.mkdir(parents=True, exist_ok=False)
    compiler = shutil.which("circom")
    if compiler is None:
        raise RuntimeError("circom must already be installed")
    sources = {}
    for name in ("fp128.circom", "blake2b.circom"):
        raw = (circuits / name).read_bytes()
        (output / name).write_bytes(raw)
        sources[name] = hashlib.sha256(raw).hexdigest()
    records = {}
    for name, (include, template) in COMPONENTS.items():
        source = output / f"{name}.circom"
        source.write_text(
            f'pragma circom 2.2.3;\ninclude "{include}";\n'
            f"component main = {template};\n"
        )
        result = subprocess.run(
            [compiler, str(source), "--r1cs", "--O1", "-o", str(output)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        logs = result.stdout + result.stderr
        (output / f"{name}.log").write_text(logs)
        if result.returncode:
            raise RuntimeError(f"Compilation failed for {name}:\n{logs}")
        counts = {}
        for key, label in (
            ("nonlinear", "non-linear constraints"),
            ("linear", "linear constraints"),
            ("wires", "wires"),
        ):
            match = re.search(rf"(?m)^{label}:\s*(\d+)", logs)
            if match is None:
                raise RuntimeError(f"Missing {label} in compiler output for {name}")
            counts[key] = int(match.group(1))
        counts["total_constraints"] = counts["nonlinear"] + counts["linear"]
        counts["r1cs_bytes"] = (output / f"{name}.r1cs").stat().st_size
        records[name] = counts
    report = {
        "scope": "Standalone components only, not a complete Jolt verifier",
        "compiler": subprocess.check_output([compiler, "--version"], text=True).strip(),
        "optimization": "O1",
        "source_sha256": sources,
        "components": records,
    }
    (output / "counts.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--circuits", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(measure(args.circuits.resolve(), args.output.resolve()), indent=2))
