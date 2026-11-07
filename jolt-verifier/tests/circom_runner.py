"""Compile Circom circuits and check generated witnesses against their R1CS."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ToolFailure(RuntimeError):
    def __init__(self, command: list[str], result: subprocess.CompletedProcess[str]):
        self.command = command
        self.result = result
        super().__init__(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout}{result.stderr}"
        )


def run(command: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise ToolFailure(command, result)
    return result


def tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise RuntimeError(f"Required tool is not installed: {name}")
    return executable


@dataclass(frozen=True)
class CompiledCircuit:
    r1cs: Path
    wasm: Path
    witness_generator: Path

    def check(self, inputs: dict[str, Any], directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=False)
        input_path = directory / "input.json"
        witness_path = directory / "witness.wtns"
        input_path.write_text(json.dumps(inputs) + "\n", encoding="utf-8")
        run(
            [
                tool("node"),
                str(self.witness_generator),
                str(self.wasm),
                str(input_path),
                str(witness_path),
            ]
        )
        run([tool("snarkjs"), "wtns", "check", str(self.r1cs), str(witness_path)])


def compile_circuit(
    source: Path,
    directory: Path,
    *,
    include_paths: tuple[Path, ...] = (),
    timeout: int = 300,
) -> CompiledCircuit:
    source = source.resolve(strict=True)
    directory.mkdir(parents=True, exist_ok=False)
    directory = directory.resolve(strict=True)
    command = [tool("circom"), str(source), "--r1cs", "--wasm", "--sym", "--O1"]
    for path in include_paths:
        command.extend(["-l", str(path.resolve(strict=True))])
    command.extend(["-o", str(directory)])
    run(command, timeout=timeout)
    compiled = CompiledCircuit(
        r1cs=directory / f"{source.stem}.r1cs",
        wasm=directory / f"{source.stem}_js" / f"{source.stem}.wasm",
        witness_generator=directory / f"{source.stem}_js" / "generate_witness.js",
    )
    for artifact in (compiled.r1cs, compiled.wasm, compiled.witness_generator):
        if not artifact.is_file():
            raise RuntimeError(f"Circom did not produce expected artifact: {artifact}")
    return compiled
