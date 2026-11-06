//! Warm SP1 Groth16 prover: one long-lived `eurekha-sp1 serve` child (its own
//! workspace, `../sp1`, so sp1-sdk stays out of this server's lock). It sets
//! up once and gnark keeps the Groth16 proving key loaded after the first
//! proof, so only the first proof per process pays that load. The server
//! starts it at boot and, with `EUREKHA_SP1_WARM_RUN` (a `zktls` run dir),
//! warms it with a throwaway proof, both under the machine-wide prove lock.
//! A dead child is restarted on the next job.

use std::{
    io::{BufRead, BufReader, Write},
    path::PathBuf,
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::Mutex,
};

use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use serde_json::{json, Value};

use crate::{jobs::Progress, lock::ProveLock};

/// Prefix of the worker's protocol lines (`eurekha-sp1 serve`).
const REPLY: &str = "EUREKHA_SP1 ";

pub struct Worker {
    proc: Mutex<Option<Proc>>,
    /// What the last start replied (`ready`, `vkey`, `setupMs`, `warm`), or why it failed.
    status: Mutex<Value>,
}

struct Proc {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

fn bin() -> String {
    std::env::var("EUREKHA_SP1_BIN")
        .unwrap_or_else(|_| concat!(env!("CARGO_MANIFEST_DIR"), "/../sp1/target/release/eurekha-sp1").into())
}

impl Proc {
    /// Next reply, forwarding `{"stage"}` and `{"partial"}` lines to
    /// `progress`; `None` when the worker exited.
    fn reply(&mut self, progress: &Progress) -> Option<Value> {
        loop {
            let v = self.line()?;
            if let Some(s) = v["stage"].as_str() {
                progress.stage(s);
            } else if let Some(p) = v.get("partial") {
                partial(p, progress);
            } else {
                return Some(v);
            }
        }
    }

    /// Next protocol line; `None` when the worker exited.
    fn line(&mut self) -> Option<Value> {
        let mut line = String::new();
        loop {
            line.clear();
            if self.stdout.read_line(&mut line).ok()? == 0 {
                return None;
            }
            if let Some(j) = line.trim_end().strip_prefix(REPLY) {
                return serde_json::from_str(j).ok();
            }
        }
    }
}

/// `{"partial": { name, path, vkey, proveMs }}`: the compressed STARK, saved by
/// the worker in the job's run dir; published on the job with the proof inline
/// (base64 bincode `SP1ProofWithPublicValues`).
fn partial(p: &Value, progress: &Progress) {
    let (Some(name), Some(path)) = (p["name"].as_str(), p["path"].as_str()) else { return };
    match std::fs::read(path) {
        Ok(bytes) => progress.partial(
            name,
            json!({
                "proof": B64.encode(&bytes),
                "proofBytes": bytes.len(),
                "encoding": "base64 bincode SP1ProofWithPublicValues (sp1-sdk 6.10)",
                "vkey": p["vkey"],
                "proveMs": p["proveMs"],
            }),
        ),
        Err(e) => tracing::warn!("sp1 partial {path}: {e}"),
    }
}

impl Worker {
    pub fn new() -> Self {
        Worker { proc: Mutex::new(None), status: Mutex::new(json!({ "ready": false })) }
    }

    pub fn status(&self) -> Value {
        self.status.lock().unwrap().clone()
    }

    /// Start (and warm) the worker if it is not running. Blocks for setup and
    /// the warm-up proof; takes the prove lock for them.
    pub fn ensure_started(&self) -> Result<(), String> {
        let mut proc = self.proc.lock().unwrap();
        self.start_locked(&mut proc, &Progress::none())
    }

    fn start_locked(&self, proc: &mut Option<Proc>, progress: &Progress) -> Result<(), String> {
        if let Some(p) = proc.as_mut() {
            if p.child.try_wait().map_err(|e| e.to_string())?.is_none() {
                return Ok(());
            }
            *proc = None;
        }
        let bin = bin();
        let mut cmd = Command::new(&bin);
        cmd.arg("serve").stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
        if let Ok(run) = std::env::var("EUREKHA_SP1_WARM_RUN") {
            cmd.arg("--warm").arg(run);
        }
        progress.stage("starting sp1 worker");
        let label =
            if std::env::var_os("EUREKHA_SP1_WARM_RUN").is_some() { "sp1 start + warm-up" } else { "sp1 start" };
        let _lock = ProveLock::acquire(label, progress).map_err(|e| format!("prove lock: {e}"))?;
        let mut child = cmd.spawn().map_err(|e| format!("start {bin}: {e}"))?;
        let mut p = Proc {
            stdin: child.stdin.take().expect("piped stdin"),
            stdout: BufReader::new(child.stdout.take().expect("piped stdout")),
            child,
        };
        let ready = p.reply(&Progress::none()).ok_or_else(|| format!("{bin} exited during setup"))?;
        tracing::info!(%ready, "sp1 worker ready");
        *self.status.lock().unwrap() = ready;
        *proc = Some(p);
        Ok(())
    }

    /// Groth16 proof of `eurekha-attested`: writes a private `zktls`-style run
    /// dir, sends it to the worker under the prove lock, returns its artifact.
    /// The run dir (it holds the PDF) is removed afterwards.
    pub fn prove(
        &self,
        pdf: &[u8],
        blinder: &[u8],
        onchain: &str,
        request: &str,
        progress: &Progress,
    ) -> Result<Value, String> {
        let mut id = [0u8; 8];
        getrandom::getrandom(&mut id).map_err(|e| e.to_string())?;
        let dir = std::env::temp_dir().join(format!("eurekha-sp1-{}", hex::encode(id)));
        let res = self.prove_in(&dir, pdf, blinder, onchain, request, progress);
        let _ = std::fs::remove_dir_all(&dir);
        res
    }

    fn prove_in(
        &self,
        dir: &PathBuf,
        pdf: &[u8],
        blinder: &[u8],
        onchain: &str,
        request: &str,
        progress: &Progress,
    ) -> Result<Value, String> {
        std::fs::create_dir(dir).map_err(|e| format!("run dir: {e}"))?;
        let blinder = hex::encode(blinder);
        let files: [(&str, &[u8]); 4] = [
            ("body.pdf", pdf),
            ("blinder.hex", blinder.as_bytes()),
            ("onchain.json", onchain.as_bytes()),
            ("request.json", request.as_bytes()),
        ];
        for (name, bytes) in files {
            std::fs::write(dir.join(name), bytes).map_err(|e| format!("{name}: {e}"))?;
        }
        let out = dir.join("artifact.json");

        // One job at a time per worker; the start-up warm-up also holds it.
        let mut proc = match self.proc.try_lock() {
            Ok(p) => p,
            Err(_) => {
                progress.stage("waiting for sp1 worker");
                self.proc.lock().unwrap()
            }
        };
        self.start_locked(&mut proc, progress)?;
        let label = format!("job {} sp1-groth16", progress.job().unwrap_or("-"));
        let _lock = ProveLock::acquire(&label, progress).map_err(|e| format!("prove lock: {e}"))?;
        let p = proc.as_mut().expect("started");
        let job = json!({ "run": dir, "out": out });
        if writeln!(p.stdin, "{job}").and_then(|_| p.stdin.flush()).is_err() {
            *proc = None;
            return Err("sp1 worker exited; it restarts on the next job".into());
        }
        let Some(reply) = p.reply(progress) else {
            *proc = None;
            return Err("sp1 worker exited during the proof; it restarts on the next job".into());
        };
        if let Some(e) = reply["error"].as_str() {
            return Err(format!("eurekha-sp1: {e}"));
        }
        let artifact = std::fs::read(&out).map_err(|e| format!("artifact: {e}"))?;
        serde_json::from_slice(&artifact).map_err(|e| format!("artifact: {e}"))
    }
}
