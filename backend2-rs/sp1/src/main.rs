//! `eurekha-sp1`: SP1 proof of the TLSNotary-attested Eurekha statement over a
//! `zktls` run dir (`body.pdf`, `blinder.hex`, `onchain.json`, `request.json`).
//!
//!   eurekha-sp1 vkey
//!   eurekha-sp1 execute --run ../zktls/runs/choco/proxy
//!   eurekha-sp1 prove --run ../zktls/runs/choco/proxy --out artifact.json
//!   eurekha-sp1 serve [--warm <run dir>]
//!
//! `serve` is the warm prover the server keeps running: setup once, then one
//! job per stdin line `{"run": <dir>, "out": <path>}`, one stdout reply line
//! per job prefixed `EUREKHA_SP1 ` (the prove reply, or `{"error"}`), after
//! `{"stage": "prove" | "verify"}` lines as the job advances. gnark
//! keeps the Groth16 R1CS and proving key in process globals after the first
//! proof, so only that one pays the load; `--warm` proves a saved run at start
//! (result discarded) so the first real job is warm too. It replies
//! `{"ready": ..}` once set up (and warmed).
//!
//! `prove` writes the artifact `EurekhaReportRegistry.submit(publicValues,
//! proof, notarySignature)` takes: Groth16 proof bytes (4-byte verifier
//! selector first), the committed public values, the notary signature over
//! `keccak256(header)`, and the program vkey. `SP1_PROVER` picks the prover
//! (`cpu` default, `cuda`). Prints nothing private.

use std::{path::PathBuf, time::Instant};

use anyhow::{bail, Context, Result};
use clap::{Parser, Subcommand};
use equinox_core::{
    eurekha,
    tlsn::{self, K256Recover, OnchainRequest, OnchainTlsn, RequestSecret},
};
use serde_json::json;
use sp1_sdk::blocking::{prelude::*, EnvProver, EnvProvingKey, ProverClient};

/// The guest ELF, built by `build.rs`.
const ELF: Elf = include_elf!("eurekha-sp1-guest");

#[derive(Parser)]
struct Args {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Print the program vkey (bytes32), what the registry pins.
    Vkey,
    /// Execute the guest only: cycles and public values.
    Execute {
        #[arg(long)]
        run: PathBuf,
    },
    /// Groth16 proof, verified before it is written.
    Prove {
        #[arg(long)]
        run: PathBuf,
        #[arg(long)]
        out: PathBuf,
    },
    /// Long-lived warm prover: jobs on stdin, replies on stdout.
    Serve {
        /// A run dir to prove once at start, so the Groth16 keys are loaded.
        #[arg(long)]
        warm: Option<PathBuf>,
    },
}

/// Prefix of every protocol line `serve` writes to stdout.
const REPLY: &str = "EUREKHA_SP1 ";

/// One Groth16 proof of `run`, verified, written to `out`; returns the summary
/// line. Reports its stages (`prove`, `verify`) to `stage`.
fn prove(
    stage: &dyn Fn(&str),
    client: &EnvProver,
    pk: &EnvProvingKey,
    setup_ms: u64,
    run: &PathBuf,
    out: &PathBuf,
) -> Result<serde_json::Value> {
    let input = load(run)?;
    let expected = input.preflight()?;
    let vkey = pk.verifying_key().bytes32();

    stage("prove");
    let t = Instant::now();
    let proof = client.prove(pk, input.stdin()).groth16().run()?;
    let prove_ms = t.elapsed().as_millis() as u64;
    let public_values = proof.public_values.to_vec();
    if public_values != expected {
        bail!("proof public values differ from the native run");
    }
    let bytes = proof.bytes();

    stage("verify");
    let t = Instant::now();
    sp1_verifier::Groth16Verifier::verify(&bytes, &public_values, &vkey, &sp1_verifier::GROTH16_VK_BYTES)
        .map_err(|e| anyhow::anyhow!("groth16 verify: {e:?}"))?;
    let verify_ms = t.elapsed().as_millis() as u64;

    let artifact = json!({
        "prover": "sp1",
        "mode": "groth16",
        "vkey": vkey,
        "publicValues": hx(&public_values),
        "proof": hx(&bytes),
        "notarySignature": hx(&input.t.signature),
        "timingsMs": { "setup": setup_ms, "prove": prove_ms, "verify": verify_ms },
    });
    std::fs::write(out, serde_json::to_string_pretty(&artifact)?)?;
    Ok(json!({ "out": out, "proofBytes": bytes.len(), "timingsMs": artifact["timingsMs"] }))
}

struct Input {
    t: OnchainTlsn,
    req: OnchainRequest,
    secret: RequestSecret,
    buf: Vec<u8>,
}

fn load(run: &PathBuf) -> Result<Input> {
    let read = |f: &str| std::fs::read(run.join(f)).with_context(|| format!("read {f}"));
    let (t, req) = tlsn::from_onchain_json(std::str::from_utf8(&read("onchain.json")?)?).map_err(anyhow::Error::msg)?;
    let secret: RequestSecret = serde_json::from_slice(&read("request.json")?).context("request.json")?;
    let mut buf = read("body.pdf")?;
    buf.extend_from_slice(&hex::decode(String::from_utf8(read("blinder.hex")?)?.trim())?);
    Ok(Input { t, req, secret, buf })
}

impl Input {
    /// Native run of the statement; also checks the notary signature (the
    /// guest leaves it to the verifier), so a forged attestation is never proven.
    fn preflight(&self) -> Result<Vec<u8>> {
        let signed = eurekha::run_attested(&self.buf, &self.t, &self.req, &self.secret, &notary()?, &K256Recover);
        signed.map_err(|e| anyhow::anyhow!("attestation rejected: {e:?}"))?;
        let out = eurekha::run_attested_unsigned(&self.buf, &self.t, &self.req, &self.secret)
            .map_err(|e| anyhow::anyhow!("attestation rejected: {e:?}"))?;
        Ok(out.encode())
    }

    fn stdin(&self) -> SP1Stdin {
        let mut s = SP1Stdin::new();
        s.write(&self.t);
        s.write(&self.req);
        s.write(&self.secret);
        s.write_slice(&self.buf);
        s
    }
}

/// `NOTARY_ADDRESS` (hex), default the public dev notary (key `[1u8; 32]`).
fn notary() -> Result<[u8; 20]> {
    let h = std::env::var("NOTARY_ADDRESS").unwrap_or_else(|_| "1a642f0e3c3af545e7acbd38b07251b3990914f1".into());
    hex::decode(h.trim().trim_start_matches("0x"))?
        .try_into()
        .map_err(|_| anyhow::anyhow!("NOTARY_ADDRESS is not 20 bytes"))
}

fn hx(b: &[u8]) -> String {
    format!("0x{}", hex::encode(b))
}

fn main() -> Result<()> {
    let args = Args::parse();
    let client = ProverClient::from_env();
    match args.cmd {
        Cmd::Vkey => {
            let pk = client.setup(ELF)?;
            println!("{}", pk.verifying_key().bytes32());
        }
        Cmd::Execute { run } => {
            let input = load(&run)?;
            let expected = input.preflight()?;
            let t = Instant::now();
            let (pv, report) = client.execute(ELF, input.stdin()).run()?;
            if report.exit_code != 0 {
                bail!("guest exited with code {}", report.exit_code);
            }
            if pv.as_slice() != expected.as_slice() {
                bail!("guest public values differ from the native run");
            }
            println!(
                "{}",
                json!({
                    "cycles": report.total_instruction_count(),
                    "executeMs": t.elapsed().as_millis() as u64,
                    "publicValues": hx(pv.as_slice()),
                })
            );
        }
        Cmd::Prove { run, out } => {
            let t = Instant::now();
            let pk = client.setup(ELF)?;
            println!("{}", prove(&|_| {}, &client, &pk, t.elapsed().as_millis() as u64, &run, &out)?);
        }
        Cmd::Serve { warm } => {
            let t = Instant::now();
            let pk = client.setup(ELF)?;
            let setup_ms = t.elapsed().as_millis() as u64;
            let mut ready = json!({ "ready": true, "vkey": pk.verifying_key().bytes32(), "setupMs": setup_ms });
            if let Some(run) = warm {
                let t = Instant::now();
                let out = std::env::temp_dir().join(format!("eurekha-sp1-warm-{}.json", std::process::id()));
                ready["warm"] = match prove(&|_| {}, &client, &pk, setup_ms, &run, &out) {
                    Ok(_) => json!({ "ms": t.elapsed().as_millis() as u64 }),
                    Err(e) => json!({ "error": format!("{e:#}") }),
                };
                let _ = std::fs::remove_file(out);
            }
            println!("{REPLY}{ready}");
            for line in std::io::stdin().lines() {
                let job = (|| -> Result<serde_json::Value> {
                    let j: serde_json::Value = serde_json::from_str(&line?)?;
                    let path = |k: &str| j[k].as_str().map(PathBuf::from).with_context(|| format!("job has no {k}"));
                    let stage = |s: &str| println!("{REPLY}{}", json!({ "stage": s }));
                    prove(&stage, &client, &pk, 0, &path("run")?, &path("out")?)
                })();
                let reply = job.unwrap_or_else(|e| json!({ "error": format!("{e:#}") }));
                println!("{REPLY}{reply}");
            }
        }
    }
    Ok(())
}
