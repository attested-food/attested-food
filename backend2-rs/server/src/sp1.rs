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

use serde_json::{json, Value};

use crate::prover::ProveLock;

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
    /// Next protocol line; `None` when the worker exited.
    fn reply(&mut self) -> Option<Value> {
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
        self.start_locked(&mut proc)
    }

    fn start_locked(&self, proc: &mut Option<Proc>) -> Result<(), String> {
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
        let _lock = ProveLock::acquire().map_err(|e| format!("prove lock: {e}"))?;
        let mut child = cmd.spawn().map_err(|e| format!("start {bin}: {e}"))?;
        let mut p = Proc {
            stdin: child.stdin.take().expect("piped stdin"),
            stdout: BufReader::new(child.stdout.take().expect("piped stdout")),
            child,
        };
        let ready = p.reply().ok_or_else(|| format!("{bin} exited during setup"))?;
        tracing::info!(%ready, "sp1 worker ready");
        *self.status.lock().unwrap() = ready;
        *proc = Some(p);
        Ok(())
    }

    /// Groth16 proof of `eurekha-attested`: writes a private `zktls`-style run
    /// dir, sends it to the worker under the prove lock, returns its artifact.
    /// The run dir (it holds the PDF) is removed afterwards.
    pub fn prove(&self, pdf: &[u8], blinder: &[u8], onchain: &str, request: &str) -> Result<Value, String> {
        let mut id = [0u8; 8];
        getrandom::getrandom(&mut id).map_err(|e| e.to_string())?;
        let dir = std::env::temp_dir().join(format!("eurekha-sp1-{}", hex::encode(id)));
        let res = self.prove_in(&dir, pdf, blinder, onchain, request);
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

        let mut proc = self.proc.lock().unwrap();
        self.start_locked(&mut proc)?;
        let _lock = ProveLock::acquire().map_err(|e| format!("prove lock: {e}"))?;
        let p = proc.as_mut().expect("started");
        let job = json!({ "run": dir, "out": out });
        if writeln!(p.stdin, "{job}").and_then(|_| p.stdin.flush()).is_err() {
            *proc = None;
            return Err("sp1 worker exited; it restarts on the next job".into());
        }
        let Some(reply) = p.reply() else {
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
