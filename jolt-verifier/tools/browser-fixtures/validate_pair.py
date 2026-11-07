#!/usr/bin/env python3
"""Check exported abc/def SHA fixtures and same-shape provenance, not a circuit proof."""

import argparse
import hashlib
import json
from pathlib import Path
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(directory, message, target):
    manifest = json.loads((directory / "manifest.json").read_text())
    require(manifest["schema"] == "website-jolt-akita-fixture-v1", "Wrong schema")
    require(manifest["tier"] == 21, "Not tier 21")
    require(manifest["native_full_verification"] is True, "Missing native verification")
    require(manifest["browser_execution"] is False, "Must identify native execution")
    require(manifest["circuit_verification"] == "not-run", "Unexpected circuit claim")
    require(
        set(manifest["tamper_rejections"]) == {"pcs", "input", "output"},
        "Missing tamper cases",
    )
    require(
        all(manifest["tamper_rejections"].values()), "Missing rejection diagnostics"
    )
    for name, digest in manifest["artifacts_sha256"].items():
        require(
            hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest,
            f"Hash mismatch: {name}",
        )
    checksums = json.loads((directory / "checksums.json").read_text())
    for name, record in checksums.items():
        data = (directory / name).read_bytes()
        require(
            len(data) == record["bytes"]
            and hashlib.sha256(data).hexdigest() == record["sha256"],
            f"Capture hash mismatch: {name}",
        )
    for name, digest in manifest["assets_sha256"].items():
        require(
            digest == target["assets"][name]["sha256"], f"Wrong website asset: {name}"
        )
    state = struct.pack(
        "<8I",
        0x6A09E667,
        0xBB67AE85,
        0x3C6EF372,
        0xA54FF53A,
        0x510E527F,
        0x9B05688C,
        0x1F83D9AB,
        0x5BE0CD19,
    )
    segment = state + struct.pack("<Q", len(message)) + message
    require(
        (directory / "segment-input.bin").read_bytes() == segment,
        "Wrong LE SHA midstate/input",
    )
    # Each argument has its own postcard encoding: tier, ByteBuf, empty chosen vector.
    require(
        (directory / "input.bin").read_bytes()
        == bytes([21, len(segment)]) + segment + b"\x00",
        "Wrong guest argument encoding",
    )
    expected = hashlib.sha256(message).digest()
    require(
        (directory / "outputs.bin").read_bytes() == expected,
        "Output differs from standard SHA-256",
    )
    require(manifest["outputs_hex"] == expected.hex(), "Output manifest differs")
    postcard = (directory / "outputs-postcard.bin").read_bytes()
    require(
        postcard[0] == 32 and postcard[1:33] == expected and not any(postcard[33:]),
        "Wrong padded postcard output",
    )
    for name in [
        "akita-transcript.tsv",
        "pcs-decoded.txt",
        "pcs-boundary.txt",
    ]:
        require(
            (directory / name).stat().st_size > 0, f"Missing native diagnostic: {name}"
        )
    proof = json.loads((directory / "proof.json").read_text())
    require(proof["trace_length"] == manifest["padded_cycles"], "Trace shape mismatch")
    require(
        bytes(proof["joint_opening_proof"]["backend_proof"])
        == (directory / "pcs-backend.bin").read_bytes(),
        "PCS bytes differ from proof",
    )
    require(
        bytes(proof["joint_opening_proof"]["schedule_selection"])
        == (directory / "pcs-schedule-selection.bin").read_bytes(),
        "PCS selection differs from proof",
    )
    return manifest, proof


def check_pair(root, target_path):
    target = json.loads(target_path.read_text())
    a, pa = validate(root / "tier21-abc", b"abc", target)
    b, pb = validate(root / "tier21-def", b"def", target)
    shape_keys = [
        "protocol",
        "trace_length",
        "ram_K",
        "rw_config",
        "one_hot_config",
        "trace_polynomial_order",
    ]
    require(
        {k: pa[k] for k in shape_keys} == {k: pb[k] for k in shape_keys},
        "Proof shapes differ",
    )
    require(a["cycles"] == b["cycles"], "Execution lengths differ")
    require(
        (root / "tier21-abc/verifier-preprocessing.bin").read_bytes()
        == (root / "tier21-def/verifier-preprocessing.bin").read_bytes(),
        "Verifier preprocessing differs",
    )
    require(
        a["artifacts_sha256"]["proof.bin"] != b["artifacts_sha256"]["proof.bin"],
        "Proofs must differ",
    )
    return {
        "schema": "website-jolt-akita-fixture-pair-v1",
        "outputs_match_standard_sha256": True,
        "same_shape": {k: pa[k] for k in shape_keys},
        "cycles": a["cycles"],
        "identical_verifier_preprocessing": True,
        "native_full_verification_recorded": True,
        "browser_execution": False,
        "circuit_verification": "not-run",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    print(json.dumps(check_pair(args.fixtures, args.target), indent=2, sort_keys=True))
