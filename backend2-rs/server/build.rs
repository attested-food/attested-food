//! Builds the OpenVM guest (`../guest`) without cargo-openvm: the nightly
//! toolchain's tier-3 `riscv32im-risc0-zkvm-elf` target with `-Z build-std`
//! and the rustc flags `openvm-build` uses. Writes `$OUT_DIR/guest.rs` with
//! `GUEST_ELF`; the server transpiles it and derives the program commitments
//! at start-up. When the toolchain is missing (or `OPENVM_SKIP_BUILD` is set)
//! the ELF is empty and the server reports the prover unavailable.

use std::{
    path::{Path, PathBuf},
    process::Command,
};

const TARGET: &str = "riscv32im-risc0-zkvm-elf";
const GUEST: &str = "equinox-openvm-guest";
/// Pinned so the program commitment is reproducible; any nightly with
/// `rust-src` works (`OPENVM_GUEST_TOOLCHAIN`), but another one gives another
/// commitment.
const TOOLCHAIN: &str = "nightly-2026-08-23";

fn main() {
    let out = PathBuf::from(std::env::var("OUT_DIR").unwrap());
    let manifest = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap());
    let guest_dir = manifest.join("../guest");
    for p in ["../guest/src", "../guest/Cargo.toml", "../guest/openvm.toml", "../core/src", "../core/Cargo.toml"] {
        println!("cargo:rerun-if-changed={p}");
    }
    for v in ["OPENVM_SKIP_BUILD", "OPENVM_GUEST_TOOLCHAIN"] {
        println!("cargo:rerun-if-env-changed={v}");
    }

    let result = if std::env::var_os("OPENVM_SKIP_BUILD").is_some_and(|v| !v.is_empty()) {
        Err("OPENVM_SKIP_BUILD is set".to_string())
    } else {
        build_guest(&guest_dir, &out)
    };
    let (elf, status) = match result {
        Ok(path) => {
            println!("cargo:warning={GUEST} built ({} bytes)", std::fs::metadata(&path).unwrap().len());
            (path, String::new())
        }
        Err(e) => {
            println!("cargo:warning={GUEST} not built: {e}");
            let path = out.join(format!("{GUEST}.empty"));
            std::fs::write(&path, []).unwrap();
            (path, e)
        }
    };
    let src = format!(
        "/// The guest RISC-V ELF; empty when the guest was not built.\n\
         pub const GUEST_ELF: &[u8] = include_bytes!({:?});\n\
         /// Why the guest was not built (empty when it was).\n\
         pub const BUILD_STATUS: &str = {:?};\n",
        elf.display().to_string(),
        status
    );
    std::fs::write(out.join("guest.rs"), src).unwrap();
}

/// `cargo +<toolchain> build` of the guest workspace, returning the ELF.
fn build_guest(guest_dir: &Path, out: &Path) -> Result<PathBuf, String> {
    let toolchain = std::env::var("OPENVM_GUEST_TOOLCHAIN").unwrap_or_else(|_| TOOLCHAIN.into());
    let target_dir = out.join("guest-target");
    // Panic locations embed source paths; remap them so the ELF and the
    // program commitment do not depend on the checkout, CARGO_HOME or rustup.
    let root = guest_dir.join("..").canonicalize().map_err(|e| format!("repo root: {e}"))?;
    let cargo_home =
        std::env::var("CARGO_HOME").unwrap_or_else(|_| format!("{}/.cargo", std::env::var("HOME").unwrap_or_default()));
    let sysroot = Command::new("rustup")
        .args(["run", &toolchain, "rustc", "--print", "sysroot"])
        .output()
        .map_err(|e| format!("rustup run {toolchain} rustc: {e}"))?;
    if !sysroot.status.success() {
        return Err(format!("toolchain {toolchain} not installed"));
    }
    let rust_src = format!("{}/lib/rustlib/src/rust", String::from_utf8_lossy(&sysroot.stdout).trim());
    let remaps = [
        format!("--remap-path-prefix={}=/backend2-rs", root.display()),
        format!("--remap-path-prefix={cargo_home}=/cargo"),
        format!("--remap-path-prefix={rust_src}=/rust"),
    ];
    let text = format!("link-arg=-Ttext={:#010x}", openvm_platform::memory::TEXT_START);
    let mut flags = vec![
        "-C",
        "passes=lower-atomic",
        "-C",
        &text,
        "-C",
        "link-arg=--fatal-warnings",
        "-C",
        "panic=abort",
        "--cfg",
        "getrandom_backend=\"custom\"",
    ];
    flags.extend(remaps.iter().map(String::as_str));
    let flags = flags.join("\x1f");
    let mut cmd = Command::new("rustup");
    // The outer cargo's toolchain, flags and profile must not leak in.
    for (k, _) in std::env::vars_os() {
        let k = k.to_string_lossy();
        if (k.starts_with("CARGO") && k != "CARGO_HOME") || k.starts_with("RUSTC") || k.starts_with("RUSTUP_TOOLCHAIN")
        {
            cmd.env_remove(k.as_ref());
        }
    }
    cmd.env_remove("RUSTFLAGS").env_remove("RUSTDOCFLAGS");
    cmd.args(["run", &toolchain, "cargo", "build", "--release", "--target", TARGET])
        .args(["-Z", "build-std=alloc,core,proc_macro,panic_abort,std"])
        .args(["-Z", "build-std-features=compiler-builtins-mem"])
        .arg("--manifest-path")
        .arg(guest_dir.join("Cargo.toml"))
        .arg("--target-dir")
        .arg(&target_dir)
        .env("CARGO_ENCODED_RUSTFLAGS", flags);
    // Inner cargo output must not reach this script's stdout (cargo directives).
    cmd.stdout(std::io::stderr());
    let status = cmd.status().map_err(|e| format!("rustup run {toolchain} cargo: {e}"))?;
    if !status.success() {
        return Err(format!("guest build with toolchain {toolchain} failed ({status})"));
    }
    Ok(target_dir.join(TARGET).join("release").join(GUEST))
}
