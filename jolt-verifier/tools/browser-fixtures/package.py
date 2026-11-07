#!/usr/bin/env python3
"""Package already verified native fixtures without changing their canonical bytes."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def package(directory):
    setup = directory / "verifier-preprocessing.json"
    (directory / "verifier-preprocessing.json.gz").write_bytes(
        gzip.compress(setup.read_bytes(), mtime=0)
    )
    proof = json.loads((directory / "proof.json").read_text())
    opening = proof["joint_opening_proof"]
    (directory / "pcs-backend.bin").write_bytes(bytes(opening["backend_proof"]))
    (directory / "pcs-schedule-selection.bin").write_bytes(
        bytes(opening["schedule_selection"])
    )
    checksums = {
        path.name: {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(directory.iterdir())
        if path.is_file()
        and path.name not in {"checksums.json", "verifier-preprocessing.json"}
    }
    (directory / "checksums.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    package(parser.parse_args().directory)
