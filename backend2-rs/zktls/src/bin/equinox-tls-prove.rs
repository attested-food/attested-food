//! `equinox-tls-prove`: server-side TLSNotary session (in-process notary) for
//! an S3 report URL, MPC or proxy mode; writes the run-dir layout the bench
//! and verifier read (incl. onchain.json). Replaces the PoC
//! `equinox_fetch_pdf`. Prints nothing private.
//!
//!   equinox-tls-prove --url-file fixtures/s3_url.txt --mode proxy --out-dir fixtures/tls-proxy

use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;
use zktls::{
    notary::NotaryConfig,
    prover::{prove_url, ProverOptions},
    TlsMode,
};

#[derive(Parser)]
struct Args {
    /// File holding the S3 URL (read from a file so the private path never
    /// shows up in argv or logs).
    #[arg(long)]
    url_file: PathBuf,
    #[arg(long)]
    out_dir: PathBuf,
    /// mpc | proxy
    #[arg(long, default_value = "mpc")]
    mode: TlsMode,
    #[arg(long, default_value_t = 1 << 20)]
    max_recv: usize,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter(tracing_subscriber::EnvFilter::from_default_env()).init();
    let args = Args::parse();
    let url = std::fs::read_to_string(&args.url_file)?.trim().to_string();
    let notary = NotaryConfig::from_env()?;
    if notary.key.is_dev() {
        eprintln!("WARNING: using the public dev notary key");
    }
    let opts = ProverOptions { mode: args.mode, max_recv: args.max_recv, ..Default::default() };
    let s = prove_url(&url, &notary, &opts, &|stage, ms| eprintln!("[{ms:>8} ms] tls {stage:?} done")).await?;
    s.write_dir(&args.out_dir)?;
    println!("EQUINOX_TLS_RESULT {}", serde_json::to_string(&s.summary())?);
    Ok(())
}
