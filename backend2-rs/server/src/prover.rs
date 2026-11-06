//! OpenVM 2.1 prover. One OS thread owns the `Sdk` (it is `!Send` through the
//! transpiler's `Rc`s), the transpiled guest and the keys, and serves jobs
//! from a channel, so the HTTP side never touches OpenVM types.
//!
//! The guest reveals `sha256(PublicValues::encode())` (OpenVM user public
//! values are a fixed 32 bytes); the server returns the encoded bytes and
//! checks they hash to what the guest revealed.

use std::{
    sync::{mpsc, Arc},
    time::{Duration, Instant},
};

use openvm_sdk::{
    config::{default_system_params, AggregationSystemParams, AppConfig},
    openvm_circuit::arch::instructions::exe::VmExe,
    types::{AppExecutionCommit, VersionedVmStarkProof},
    Sdk, StdIn, VerificationBaseline, F,
};
use openvm_sdk_config::SdkVmConfig;
use openvm_stark_backend::p3_field::PrimeField32;
use tokio::sync::oneshot;

mod guest {
    include!(concat!(env!("OUT_DIR"), "/guest.rs"));
}

/// App VM config the guest was written for (RV32IM, IO, SHA-2).
const OPENVM_TOML: &str = include_str!("../../guest/openvm.toml");

/// The backend's machine-wide `mkdir` lock: at most one heavy proof per host
/// (OpenVM peaks near 19 GB). Released on drop.
const PROVE_LOCK: &str = "/tmp/equinox-prove.lock.d";

struct ProveLock;

impl ProveLock {
    fn acquire() -> std::io::Result<Self> {
        let mut waited = false;
        loop {
            match std::fs::create_dir(PROVE_LOCK) {
                Ok(()) => return Ok(ProveLock),
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                    if !waited {
                        tracing::info!("waiting for {PROVE_LOCK} ...");
                        waited = true;
                    }
                    std::thread::sleep(Duration::from_secs(5));
                }
                Err(e) => return Err(e),
            }
        }
    }
}

impl Drop for ProveLock {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir(PROVE_LOCK);
    }
}

/// `0x || app_exe_commit || app_vm_commit`: the two commitments that pin the
/// program (and that OpenVM's EVM verifier takes).
#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProgramCommit {
    pub app_exe_commit: String,
    pub app_vm_commit: String,
}

#[derive(Debug, Default, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Timings {
    pub setup_ms: Option<u64>,
    pub keygen_ms: Option<u64>,
    pub execute_ms: Option<u64>,
    pub prove_ms: Option<u64>,
    pub verify_ms: Option<u64>,
}

#[derive(Debug)]
pub struct Proved {
    /// The 32 bytes the guest revealed.
    pub revealed: Vec<u8>,
    pub instructions: u64,
    /// bincode of `VersionedVmStarkProof`; empty for execute-only.
    pub proof: Vec<u8>,
    pub program: Option<ProgramCommit>,
    pub timings: Timings,
}

pub struct GuestInput {
    /// Report format byte the guest dispatches on: 0 Equinox, 1 Eurekha.
    pub format: u8,
    /// Analyte labels (Equinox only).
    pub labels: Vec<String>,
    /// `pdf || blinder`.
    pub buffer: Vec<u8>,
}

enum Job {
    Program(oneshot::Sender<Result<ProgramCommit, String>>),
    Run { input: GuestInput, stark: bool, reply: oneshot::Sender<Result<Proved, String>> },
    Verify { proof: Vec<u8>, reply: oneshot::Sender<Result<Vec<u8>, String>> },
}

/// Handle to the prover thread.
#[derive(Clone)]
pub struct Prover {
    tx: mpsc::Sender<Job>,
}

pub fn guest_built() -> Result<usize, String> {
    if guest::GUEST_ELF.is_empty() {
        Err(format!("openvm guest not built: {}", guest::BUILD_STATUS))
    } else {
        Ok(guest::GUEST_ELF.len())
    }
}

impl Prover {
    pub fn spawn() -> Self {
        let (tx, rx) = mpsc::channel::<Job>();
        std::thread::Builder::new()
            .name("openvm".into())
            .spawn(move || {
                let mut engine = Engine::default();
                for job in rx {
                    match job {
                        Job::Program(reply) => {
                            let _ = reply.send(engine.program());
                        }
                        Job::Run { input, stark, reply } => {
                            let _ = reply.send(engine.run(input, stark));
                        }
                        Job::Verify { proof, reply } => {
                            let _ = reply.send(engine.verify(&proof));
                        }
                    }
                }
            })
            .expect("spawn openvm thread");
        Prover { tx }
    }

    async fn call<T>(&self, job: impl FnOnce(oneshot::Sender<Result<T, String>>) -> Job) -> Result<T, String> {
        let (reply, rx) = oneshot::channel();
        self.tx.send(job(reply)).map_err(|_| "openvm thread gone".to_string())?;
        rx.await.map_err(|_| "openvm thread dropped the job".to_string())?
    }

    /// The pinned program's commitments (runs app + aggregation keygen once).
    pub async fn program(&self) -> Result<ProgramCommit, String> {
        self.call(Job::Program).await
    }

    /// Execute (and, with `stark`, prove and verify) the guest on `input`.
    pub async fn run(&self, input: GuestInput, stark: bool) -> Result<Proved, String> {
        self.call(|reply| Job::Run { input, stark, reply }).await
    }

    /// Verify a STARK against the pinned program; returns the revealed bytes.
    pub async fn verify(&self, proof: Vec<u8>) -> Result<Vec<u8>, String> {
        self.call(|reply| Job::Verify { proof, reply }).await
    }
}

/// Lives on the prover thread only.
#[derive(Default)]
struct Engine {
    setup: Option<(Sdk, Arc<VmExe<F>>)>,
    baseline: Option<(VerificationBaseline, ProgramCommit)>,
}

fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}

fn ms(t: Instant) -> Option<u64> {
    Some(t.elapsed().as_millis() as u64)
}

impl Engine {
    /// SDK with the app VM config, and the transpiled guest.
    fn ensure_setup(&mut self) -> Result<(), String> {
        if self.setup.is_none() {
            guest_built()?;
            let vm = SdkVmConfig::from_toml(OPENVM_TOML).map_err(err)?;
            let app = AppConfig { app_vm_config: vm, system_params: default_system_params() };
            let sdk = Sdk::new(app, AggregationSystemParams::default()).map_err(err)?;
            let exe = sdk.convert_to_exe(guest::GUEST_ELF.to_vec()).map_err(err)?;
            self.setup = Some((sdk, exe));
        }
        Ok(())
    }

    fn sdk(&self) -> &Sdk {
        &self.setup.as_ref().expect("setup").0
    }

    fn exe(&self) -> Arc<VmExe<F>> {
        self.setup.as_ref().expect("setup").1.clone()
    }

    /// App and aggregation keygen, the verification baseline and the program
    /// commitments. Built once; several GB and tens of seconds.
    fn ensure_baseline(&mut self) -> Result<(), String> {
        self.ensure_setup()?;
        if self.baseline.is_none() {
            let prover = self.sdk().prover(self.exe()).map_err(err)?;
            let baseline = prover.generate_baseline();
            let c = AppExecutionCommit {
                app_exe_commit: baseline.app_exe_commit().into(),
                app_vm_commit: prover.app_vm_commit().into(),
            };
            let commit = ProgramCommit {
                app_exe_commit: hex::encode(c.app_exe_commit.as_slice()),
                app_vm_commit: hex::encode(c.app_vm_commit.as_slice()),
            };
            self.baseline = Some((baseline, commit));
        }
        Ok(())
    }

    fn program(&mut self) -> Result<ProgramCommit, String> {
        self.ensure_baseline()?;
        Ok(self.baseline.as_ref().unwrap().1.clone())
    }

    fn stdin(input: &GuestInput) -> StdIn {
        let mut s = StdIn::default();
        s.write(&input.format);
        if input.format == 0 {
            s.write(&input.labels);
        }
        s.write_bytes(&input.buffer);
        s
    }

    fn run(&mut self, input: GuestInput, stark: bool) -> Result<Proved, String> {
        let mut timings = Timings::default();
        let t = Instant::now();
        self.ensure_setup()?;
        timings.setup_ms = ms(t);

        let t = Instant::now();
        let (revealed, (_cost, instructions)) = self
            .sdk()
            .execute_metered_cost(self.exe(), Self::stdin(&input))
            .map_err(|e| format!("openvm execute: {e}"))?;
        timings.execute_ms = ms(t);
        if !stark {
            return Ok(Proved { revealed, instructions, proof: Vec::new(), program: None, timings });
        }

        let _lock = ProveLock::acquire().map_err(|e| format!("prove lock: {e}"))?;
        let t = Instant::now();
        self.ensure_baseline()?;
        timings.keygen_ms = ms(t);

        let t = Instant::now();
        let mut prover = self.sdk().prover(self.exe()).map_err(err)?;
        let (proof, _) = prover.prove(Self::stdin(&input), &[]).map_err(|e| format!("openvm prove: {e}"))?;
        let proof = bincode::serialize(&VersionedVmStarkProof::new(proof).map_err(err)?).map_err(err)?;
        timings.prove_ms = ms(t);

        let t = Instant::now();
        let proved_revealed = self.verify(&proof)?;
        timings.verify_ms = ms(t);
        if proved_revealed != revealed {
            return Err("proof reveals different bytes than the execution".into());
        }
        let program = Some(self.baseline.as_ref().unwrap().1.clone());
        Ok(Proved { revealed, instructions, proof, program, timings })
    }

    /// Decode and verify a STARK against the pinned program; returns the 32
    /// bytes the guest revealed.
    fn verify(&mut self, proof: &[u8]) -> Result<Vec<u8>, String> {
        self.ensure_baseline()?;
        let v: VersionedVmStarkProof = bincode::deserialize(proof).map_err(|e| format!("decode proof: {e}"))?;
        let agg_vk = (*self.sdk().agg_vk()).clone();
        let baseline = &self.baseline.as_ref().unwrap().0;
        let proof = v.decode_using_vk(&agg_vk, baseline).map_err(|e| format!("decode proof: {e}"))?;
        let revealed: Vec<u8> = proof
            .user_pvs_proof
            .public_values
            .iter()
            .map(|f| u8::try_from(f.as_canonical_u32()).unwrap_or(0xff))
            .collect();
        Sdk::verify_proof(agg_vk, baseline.clone(), &proof).map_err(|e| format!("verify: {e}"))?;
        Ok(revealed)
    }
}
