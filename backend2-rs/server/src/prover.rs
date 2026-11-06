//! OpenVM 2.1 prover. One OS thread owns the `Sdk` (it is `!Send` through the
//! transpiler's `Rc`s), the transpiled guest and the keys, and serves jobs
//! from a channel, so the HTTP side never touches OpenVM types.
//!
//! The guest reveals `sha256(PublicValues::encode())` (OpenVM user public
//! values are a fixed 32 bytes); the server returns the encoded bytes and
//! checks they hash to what the guest revealed.

use std::{
    sync::{mpsc, Arc},
    time::Instant,
};

use equinox_core::tlsn::{OnchainRequest, OnchainTlsn, RequestSecret};
use openvm_sdk::{
    config::{default_system_params, AggregationSystemParams, AppConfig},
    openvm_circuit::arch::instructions::exe::VmExe,
    types::{AppExecutionCommit, VersionedVmStarkProof},
    Sdk, StdIn, VerificationBaseline, F,
};
use openvm_sdk_config::SdkVmConfig;
use openvm_stark_backend::p3_field::PrimeField32;
use tokio::sync::oneshot;

use crate::{jobs::Progress, lock::ProveLock};

mod guest {
    include!(concat!(env!("OUT_DIR"), "/guest.rs"));
}

/// App VM config the guest was written for (RV32IM, IO, SHA-2).
const OPENVM_TOML: &str = include_str!("../../guest/openvm.toml");

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
    /// bincode of `VersionedVmStarkProof`.
    pub proof: Vec<u8>,
    pub program: Option<ProgramCommit>,
    pub timings: Timings,
}

pub struct GuestInput {
    /// Report format byte the guest dispatches on: 0 Equinox, 1 Eurekha,
    /// 2 Eurekha with its TLSNotary attestation (signature checked by the
    /// verifier), 3 the same with the signature checked in the guest.
    pub format: u8,
    /// Analyte labels (Equinox only).
    pub labels: Vec<String>,
    /// Formats 2 and 3.
    pub attested: Option<Attested>,
    /// `pdf || blinder`.
    pub buffer: Vec<u8>,
}

/// The attestation inputs of formats 2 and 3, in the order the guest reads
/// them (`notary` in format 3 only).
pub struct Attested {
    pub notary: [u8; 20],
    pub tlsn: OnchainTlsn,
    pub request: OnchainRequest,
    pub secret: RequestSecret,
}

enum Job {
    /// Keygen ahead of the first job, only if the prove lock is free now.
    Warm,
    Program(oneshot::Sender<Result<ProgramCommit, String>>),
    Run {
        input: GuestInput,
        progress: Progress,
        reply: oneshot::Sender<Result<Proved, String>>,
    },
    Verify {
        proof: Vec<u8>,
        reply: oneshot::Sender<Result<Vec<u8>, String>>,
    },
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
                        Job::Warm => engine.warm(),
                        Job::Program(reply) => {
                            let _ = reply.send(engine.program());
                        }
                        Job::Run { input, progress, reply } => {
                            let _ = reply.send(engine.run(input, &progress));
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

    /// Start keygen now if the prove lock is free; otherwise the first job
    /// (or `/program`) does it once it holds the lock.
    pub fn warm(&self) {
        let _ = self.tx.send(Job::Warm);
    }

    /// The pinned program's commitments (runs app + aggregation keygen once).
    pub async fn program(&self) -> Result<ProgramCommit, String> {
        self.call(Job::Program).await
    }

    /// Execute, prove and verify the guest on `input` (STARK).
    pub async fn run(&self, input: GuestInput, progress: Progress) -> Result<Proved, String> {
        self.call(|reply| Job::Run { input, progress, reply }).await
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
    /// commitments. Built once; several GB and tens of seconds, so it takes the
    /// prove lock unless the caller (`run`) already holds it.
    fn ensure_baseline(&mut self, locked: bool) -> Result<(), String> {
        self.ensure_setup()?;
        if self.baseline.is_none() {
            let _lock = match locked {
                true => None,
                false => Some(
                    ProveLock::acquire("openvm keygen", &Progress::none()).map_err(|e| format!("prove lock: {e}"))?,
                ),
            };
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

    fn warm(&mut self) {
        if self.baseline.is_some() {
            return;
        }
        match ProveLock::try_acquire("openvm keygen") {
            Ok(Some(_lock)) => match self.ensure_baseline(true) {
                Ok(()) => tracing::info!("openvm keys ready"),
                Err(e) => tracing::warn!("openvm keygen: {e}"),
            },
            Ok(None) => tracing::info!("prove lock busy: openvm keygen deferred to the first job"),
            Err(e) => tracing::warn!("prove lock: {e}"),
        }
    }

    fn program(&mut self) -> Result<ProgramCommit, String> {
        self.ensure_baseline(false)?;
        Ok(self.baseline.as_ref().unwrap().1.clone())
    }

    fn stdin(input: &GuestInput) -> StdIn {
        let mut s = StdIn::default();
        s.write(&input.format);
        if input.format == 0 {
            s.write(&input.labels);
        }
        if let Some(a) = &input.attested {
            if input.format == 3 {
                s.write(&a.notary);
            }
            s.write(&a.tlsn);
            s.write(&a.request);
            s.write(&a.secret);
        }
        s.write_bytes(&input.buffer);
        s
    }

    fn run(&mut self, input: GuestInput, progress: &Progress) -> Result<Proved, String> {
        let mut timings = Timings::default();
        let label = format!("job {} openvm stark", progress.job().unwrap_or("-"));
        let _lock = ProveLock::acquire(&label, progress).map_err(|e| format!("prove lock: {e}"))?;
        let t = Instant::now();
        progress.stage("execute");
        self.ensure_setup()?;
        timings.setup_ms = ms(t);

        let t = Instant::now();
        let (revealed, (_cost, instructions)) = self
            .sdk()
            .execute_metered_cost(self.exe(), Self::stdin(&input))
            .map_err(|e| format!("openvm execute: {e}"))?;
        timings.execute_ms = ms(t);
        let t = Instant::now();
        if self.baseline.is_none() {
            progress.stage("keygen");
        }
        self.ensure_baseline(true)?;
        timings.keygen_ms = ms(t);

        progress.stage("prove");
        let t = Instant::now();
        let mut prover = self.sdk().prover(self.exe()).map_err(err)?;
        let (proof, _) = prover.prove(Self::stdin(&input), &[]).map_err(|e| format!("openvm prove: {e}"))?;
        let proof = bincode::serialize(&VersionedVmStarkProof::new(proof).map_err(err)?).map_err(err)?;
        timings.prove_ms = ms(t);

        progress.stage("verify");
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
        // Inside `run` the baseline exists, so this never re-takes the held lock.
        self.ensure_baseline(false)?;
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
