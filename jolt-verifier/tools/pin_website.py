#!/usr/bin/env python3
"""Record the website's committed Jolt client, guest sources and local prover assets.

This inventories files as data. It does not run or rebuild the prover and does
not establish that a binary was produced from the recorded source.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

TIERS = {"shaChunk": 20, "shaFinish": 21, "extract": 31, "tls": 33}
GUEST_CONFIG = {
    "heap_size": 8388608,
    "stack_size": 262144,
    "max_input_size": 500000,
    "max_output_size": 4096,
    "max_trace_length": 2097152,
}
PAGE_FILES = (
    "frontend/src/lib/jolt.ts",
    "frontend/src/pages/Prove.tsx",
    "frontend/static/vendor/prove-worker.js",
    "frontend/scripts/vendor-jolt.sh",
)
REQUIRED_ASSETS = (
    "worker.js",
    "gpu-proxy.js",
    "equinox.elf",
    "equinox_program.bin",
    "akita_schedules.bin",
    "pkg/jolt_wasm_prover.js",
    "pkg/jolt_wasm_prover_bg.wasm",
    "wgsl/fp128.wgsl",
)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def source_files(root, revision, names):
    result = {}
    for name in names:
        raw = git(root, "show", f"{revision}:{name}")
        result[name] = {"sha256": digest(raw), "bytes": len(raw)}
    return result


def inventory_assets(directory):
    root = directory.resolve(strict=True)
    for relative in REQUIRED_ASSETS:
        if not (root / relative).is_file():
            raise ValueError(f"Missing website prover asset: {relative}")
    result = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(
            p.startswith(".") for p in path.relative_to(root).parts
        ):
            continue
        if not path.resolve(strict=True).is_relative_to(root):
            raise ValueError(f"Asset escapes its directory: {path}")
        result[path.relative_to(root).as_posix()] = {
            "sha256": file_digest(path),
            "bytes": path.stat().st_size,
        }
    return result


def pin(website, poc, page_ref):
    page_revision = (
        git(website, "rev-parse", "--verify", f"{page_ref}^{{commit}}").decode().strip()
    )
    poc_revision = git(poc, "rev-parse", "HEAD").decode().strip()
    client = git(website, "show", f"{page_revision}:frontend/src/lib/jolt.ts").decode()
    match = re.search(r"const TIER\s*=\s*\{([^}]+)\}", client)
    observed = dict(re.findall(r"(\w+)\s*:\s*(\d+)", match.group(1))) if match else {}
    if {name: int(value) for name, value in observed.items()} != TIERS:
        raise ValueError("Website Jolt tier configuration differs from this target")
    guest = git(poc, "show", f"{poc_revision}:guests/jolt/src/lib.rs").decode()
    attribute = re.search(r"#\[jolt::provable\((.*?)\)\]\s*fn equinox", guest, re.S)
    configuration = (
        dict(re.findall(r"(\w+)\s*=\s*(\d+)", attribute.group(1))) if attribute else {}
    )
    if {key: int(value) for key, value in configuration.items()} != GUEST_CONFIG:
        raise ValueError(
            "Website Jolt guest memory configuration differs from this target"
        )
    paths = (
        git(
            poc,
            "ls-tree",
            "-r",
            "--name-only",
            poc_revision,
            "--",
            "core",
            "extractor",
            "guests/jolt",
            "scripts/install-core.sh",
        )
        .decode()
        .splitlines()
    )
    sources = source_files(poc, poc_revision, paths)
    fork = git(poc, "show", f"{poc_revision}:guests/jolt/FORK_REV").decode().strip()
    return {
        "schema": "website-jolt-target-v1",
        "scope": "Individual Jolt segment proofs produced by the website /prove page",
        "website": {
            "commit": page_revision,
            "sources": source_files(website, page_revision, PAGE_FILES),
        },
        "build_sources": {
            "poc_commit": poc_revision,
            "wasm_prover_fork_commit": fork,
            "sources": sources,
        },
        "guest": {
            "name": "equinox",
            "allowed_tiers": TIERS,
            "memory_configuration": GUEST_CONFIG,
        },
        "assets": inventory_assets(website / "frontend/static/vendor/jolt"),
        "verification": {
            "source_to_asset_rebuild_checked": False,
            "native_fixtures_checked": False,
            "complete_circom_verifier": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--website", type=Path, required=True)
    parser.add_argument("--poc", type=Path, required=True)
    parser.add_argument("--page-ref", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = pin(args.website.resolve(), args.poc.resolve(), args.page_ref)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
