//! Native fixture driver for the exact browser engine and shipped Equinox ELF.

#[path = "../src/engine.rs"]
mod engine;

use common::jolt_device::JoltDevice;
use jolt_inlines_keccak256 as _;
use jolt_inlines_secp256k1 as _;
use jolt_inlines_sha2 as _;
use serde::{de::DeserializeOwned, Serialize};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{error::Error, fs, path::Path};

fn decode<T: DeserializeOwned>(bytes: &[u8]) -> Result<T, Box<dyn Error>> {
    let (value, consumed) = bincode::serde::decode_from_slice(bytes, bincode::config::standard())?;
    if consumed != bytes.len() {
        return Err("Trailing bytes".into());
    }
    Ok(value)
}
fn encode(value: &impl Serialize) -> Result<Vec<u8>, Box<dyn Error>> {
    Ok(bincode::serde::encode_to_vec(
        value,
        bincode::config::standard(),
    )?)
}
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn hash(bytes: &[u8]) -> String {
    hex(&Sha256::digest(bytes))
}
fn json_file(path: &Path, value: &impl Serialize) -> Result<(), Box<dyn Error>> {
    serde_json::to_writer_pretty(fs::File::create(path)?, value)?;
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 5 {
        return Err("Usage: browser-fixture ASSETS TIER INPUT OUTPUT_DIRECTORY".into());
    }
    let assets = Path::new(&args[1]);
    let tier: u8 = args[2].parse()?;
    if ![20, 21, 31, 33].contains(&tier) {
        return Err("Unsupported website tier".into());
    }
    let buf = fs::read(&args[3])?;
    let directory = Path::new(&args[4]);
    fs::create_dir(directory)?;
    let mut inputs = postcard::to_allocvec(&tier)?;
    inputs.extend(postcard::to_allocvec(&buf.as_slice())?);
    inputs.extend(postcard::to_allocvec(&Vec::<String>::new())?);
    let schedules = fs::read(assets.join("akita_schedules.bin"))?;
    let program = fs::read(assets.join("equinox_program.bin"))?;
    let elf = fs::read(assets.join("equinox.elf"))?;
    let ctx = engine::ProverContext::new(&schedules, &program, &elf)?;
    println!(
        "Proving website equinox tier {tier}, {} input bytes",
        buf.len()
    );
    let out = engine::prove(&ctx, &inputs)?;
    let prep = engine::decode_verifier_preprocessing(&out.verifier_preprocessing_bytes)?;
    std::env::set_var("JOLT_BROWSER_FIXTURE_CAPTURE", directory);
    let verified = engine::verify(&prep, &out.proof_bytes, &out.io_bytes);
    std::env::remove_var("JOLT_BROWSER_FIXTURE_CAPTURE");
    verified?;
    let proof: engine::Proof = decode(&out.proof_bytes)?;
    let io: JoltDevice = decode(&out.io_bytes)?;
    let output: Vec<u8> = postcard::from_bytes(&io.outputs)?;

    let mut pcs = serde_json::to_value(&proof.joint_opening_proof)?;
    let bytes = pcs["backend_proof"]
        .as_array_mut()
        .ok_or("Missing Akita backend proof")?;
    let first = bytes.first_mut().ok_or("Empty Akita proof")?;
    *first = json!(first.as_u64().ok_or("Non-byte PCS value")? ^ 1);
    let mut bad_pcs = proof.clone();
    bad_pcs.joint_opening_proof = serde_json::from_value(pcs)?;
    let pcs_error = engine::verify(&prep, &encode(&bad_pcs)?, &out.io_bytes)
        .err()
        .ok_or("PCS tamper accepted")?;
    let mut bad_io = io.clone();
    if bad_io.outputs.is_empty() {
        return Err("No output".into());
    }
    let last = bad_io.outputs.len() - 1;
    bad_io.outputs[last] ^= 1;
    let output_error = engine::verify(&prep, &out.proof_bytes, &encode(&bad_io)?)
        .err()
        .ok_or("Output tamper accepted")?;
    let mut bad_input = io.clone();
    bad_input.inputs[0] ^= 1;
    let input_error = engine::verify(&prep, &out.proof_bytes, &encode(&bad_input)?)
        .err()
        .ok_or("Input tamper accepted")?;
    for (name, bytes) in [
        ("proof.bin", out.proof_bytes.as_slice()),
        ("program-io.bin", out.io_bytes.as_slice()),
        (
            "verifier-preprocessing.bin",
            out.verifier_preprocessing_bytes.as_slice(),
        ),
        ("input.bin", inputs.as_slice()),
        ("segment-input.bin", buf.as_slice()),
        ("outputs-postcard.bin", io.outputs.as_slice()),
        ("outputs.bin", output.as_slice()),
    ] {
        fs::write(directory.join(name), bytes)?;
    }
    json_file(&directory.join("proof.json"), &proof)?;
    json_file(&directory.join("program-io.json"), &io)?;
    json_file(&directory.join("verifier-preprocessing.json"), &prep)?;
    json_file(
        &directory.join("manifest.json"),
        &json!({
            "schema":"website-jolt-akita-fixture-v1", "tier":tier,
            "producer":"native-exact-browser-engine", "browser_execution":false,
            "native_full_verification":true, "circuit_verification":"not-run",
            "tamper_rejections":{"pcs":pcs_error,"output":output_error,"input":input_error},
            "cycles":out.unpadded_cycles,"padded_cycles":out.padded_cycles,
            "timings_ms":{"trace":out.timings.trace,"setup":out.timings.setup,"prove":out.timings.prove},
            "assets_sha256":{"equinox.elf":hash(&elf),"equinox_program.bin":hash(&program),"akita_schedules.bin":hash(&schedules)},
            "artifacts_sha256":{"proof.bin":hash(&out.proof_bytes),"program-io.bin":hash(&out.io_bytes),
              "verifier-preprocessing.bin":hash(&out.verifier_preprocessing_bytes),"input.bin":hash(&inputs),"outputs.bin":hash(&output)},
            "outputs_hex":hex(&output)
        }),
    )?;
    println!("Accepted full proof and rejected PCS, output and input mutations. {} cycles; proof {} bytes; output {}", out.unpadded_cycles, out.proof_bytes.len(), hex(&output));
    Ok(())
}
