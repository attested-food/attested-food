use sp1_build::build_program_with_args;

fn main() {
    // Guest-only release profile: the inner `cargo build` that sp1-build spawns
    // inherits this process's env, so fat LTO / one codegen unit apply to the
    // zkVM ELF without slowing down the host build.
    std::env::set_var("CARGO_PROFILE_RELEASE_LTO", "fat");
    std::env::set_var("CARGO_PROFILE_RELEASE_CODEGEN_UNITS", "1");
    std::env::set_var("CARGO_PROFILE_RELEASE_OPT_LEVEL", "3");
    println!("cargo:rerun-if-changed=../core/src");
    println!("cargo:rerun-if-changed=../core/Cargo.toml");
    // Panic locations embed source paths, so without remapping the ELF (and the
    // program vkey pinned on-chain) would depend on where the repo is checked out.
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("..").canonicalize().expect("backend2-rs root");
    let cargo_home =
        std::env::var("CARGO_HOME").unwrap_or_else(|_| format!("{}/.cargo", std::env::var("HOME").expect("HOME")));
    let rustflags = vec![
        format!("--remap-path-prefix={}=/backend2-rs", root.display()),
        format!("--remap-path-prefix={cargo_home}=/cargo"),
    ];
    build_program_with_args("guest", sp1_build::BuildArgs { rustflags, ..Default::default() })
}
