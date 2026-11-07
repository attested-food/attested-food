#!/usr/bin/env python3
"""Collect source and build provenance inside the disposable browser build VM."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile


def command(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def digest(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def collect(root, output):
    output.mkdir(parents=True, exist_ok=True)
    repos = {
        "browser-fork": root,
        "jolt": root / ".wasm-deps/jolt",
        "akita": root / ".wasm-deps/akita",
    }
    result = {
        "schema": "website-jolt-native-build-provenance-v1",
        "repos": {},
        "build_command": "RUSTUP_TOOLCHAIN=1.95 cargo build --locked --release --features native --bin browser-fixture -j 4",
        "prove_environment": {"RAYON_NUM_THREADS": "4"},
        "native_only": True,
        "browser_wasm_rebuilt": False,
    }
    for name, path in repos.items():
        patch = subprocess.check_output(
            [
                "git",
                "diff",
                "--binary",
                "--",
                "*.rs",
                "*.toml",
                "Cargo.lock",
                "*.sh",
                "*.patch",
            ],
            cwd=path,
        )
        (output / (name + ".patch")).write_bytes(patch)
        tracked = (
            subprocess.check_output(
                ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                cwd=path,
            )
            .decode()
            .split("\0")
        )
        sources = {}
        for relative in sorted(set(tracked)):
            file = path / relative
            if file.is_file() and (
                file.suffix in {".rs", ".toml", ".patch", ".sh"}
                or file.name
                in {"Cargo.lock", "FORK_REV", "UPSTREAM_REV", "UPSTREAM_PATCH"}
            ):
                sources[relative] = digest(file)
        untracked = (
            subprocess.check_output(
                ["git", "ls-files", "-z", "--others", "--exclude-standard"], cwd=path
            )
            .decode()
            .split("\0")
        )
        archive = name + "-untracked-source.tar.gz"
        with tarfile.open(output / archive, "w:gz") as stream:
            for relative in sorted(set(untracked) & set(sources)):
                stream.add(path / relative, arcname=relative, recursive=False)
        result["repos"][name] = {
            "head": command("git", "rev-parse", "HEAD", cwd=path),
            "source_files": sources,
            "patch": name + ".patch",
            "untracked_source_archive": archive,
        }
    installed = [
        path
        for part in ["guests/equinox", "guests/equinox-core"]
        for path in (root / part).rglob("*")
        if path.is_file() and path.suffix in {".rs", ".toml"}
    ]
    result["installed_guest_sources"] = {
        str(path.relative_to(root)): digest(path) for path in sorted(installed)
    }
    with tarfile.open(output / "installed-guest-source.tar.gz", "w:gz") as stream:
        for path in sorted(installed):
            stream.add(path, arcname=str(path.relative_to(root)), recursive=False)
    for name in [
        "Cargo.lock",
        "Cargo.toml",
        "src/engine.rs",
        "guests/equinox/src/lib.rs",
        "preprocessing/browser_fixture.rs",
    ]:
        destination = output / name.replace("/", "_")
        destination.write_bytes((root / name).read_bytes())
    env = dict(os.environ, RUSTUP_TOOLCHAIN="1.95")
    result["toolchain"] = {
        name: subprocess.check_output(
            [str(Path.home() / ".cargo/bin" / name), *flags], env=env, text=True
        ).strip()
        for name, flags in {
            "rustc": ["-Vv"],
            "cargo": ["-V"],
            "rustfmt": ["-V"],
        }.items()
    }
    result["binary"] = digest(root / "target/release/browser-fixture")
    result["assets"] = {
        name: digest(root / "frontend/public" / name)
        for name in ["equinox.elf", "equinox_program.bin", "akita_schedules.bin"]
    }
    (output / "build.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    collect(args.source.resolve(), args.output.resolve())
