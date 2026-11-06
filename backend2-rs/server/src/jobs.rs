//! Proving jobs: `POST /prove` returns a job id at once, `GET /jobs/{id}`
//! reports the stage, the stage history, an estimate of progress and, when
//! done, the result. Jobs live in memory and are dropped [`JOB_TTL`] after
//! they finish (a restart loses them).
//!
//! The provers report stages through a [`Progress`] handle. Progress is an
//! estimate: neither SDK reports a fraction done, so it is the elapsed working
//! time over the sum of the stage durations of the last finished job of the
//! same mode (time spent waiting for the prove lock or the queue excluded).

use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use serde_json::{json, Value};

/// How long a finished job stays readable.
pub const JOB_TTL: Duration = Duration::from_secs(3600);

/// Stages that are waiting, not work: left out of the progress estimate.
const WAITING: [&str; 2] = ["queued", "waiting for prove lock"];

/// Reports the current stage of one job. Cheap to clone; a no-op for
/// synchronous callers that have no job.
#[derive(Clone)]
pub struct Progress(Option<Arc<dyn Fn(&str) + Send + Sync>>);

impl Progress {
    pub fn none() -> Self {
        Progress(None)
    }

    pub fn stage(&self, name: &str) {
        if let Some(f) = &self.0 {
            f(name);
        }
    }
}

struct Stage {
    name: String,
    started: Instant,
    ms: Option<u64>,
}

struct Job {
    mode: String,
    format: String,
    created: Instant,
    created_unix: u64,
    stages: Vec<Stage>,
    finished: Option<Instant>,
    /// What is known before proving: the public values the proof will commit.
    preview: Value,
    result: Option<Result<Value, String>>,
}

impl Job {
    fn close_stage(&mut self) {
        if let Some(s) = self.stages.last_mut() {
            s.ms.get_or_insert(s.started.elapsed().as_millis() as u64);
        }
    }

    fn work_ms(&self) -> u64 {
        self.stages
            .iter()
            .filter(|s| !WAITING.contains(&s.name.as_str()))
            .map(|s| s.ms.unwrap_or_else(|| s.started.elapsed().as_millis() as u64))
            .sum()
    }
}

#[derive(Default)]
pub struct Jobs {
    jobs: Mutex<HashMap<String, Job>>,
    /// mode -> working time of its last successful job.
    last_ms: Mutex<HashMap<String, u64>>,
}

impl Jobs {
    /// A new job in stage `queued`; returns its id.
    pub fn create(&self, mode: &str, format: &str, preview: Value) -> String {
        let mut id = [0u8; 12];
        getrandom::getrandom(&mut id).expect("random job id");
        let id = hex::encode(id);
        let now = Instant::now();
        let mut jobs = self.jobs.lock().unwrap();
        jobs.retain(|_, j| j.finished.is_none_or(|f| f.elapsed() < JOB_TTL));
        jobs.insert(
            id.clone(),
            Job {
                mode: mode.into(),
                format: format.into(),
                created: now,
                created_unix: SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |d| d.as_secs()),
                stages: vec![Stage { name: "queued".into(), started: now, ms: None }],
                finished: None,
                preview,
                result: None,
            },
        );
        id
    }

    pub fn progress(self: &Arc<Self>, id: &str) -> Progress {
        let (jobs, id) = (self.clone(), id.to_string());
        Progress(Some(Arc::new(move |name: &str| {
            let mut all = jobs.jobs.lock().unwrap();
            if let Some(j) = all.get_mut(&id) {
                if j.stages.last().is_some_and(|s| s.name == name) {
                    return;
                }
                j.close_stage();
                j.stages.push(Stage { name: name.into(), started: Instant::now(), ms: None });
            }
        })))
    }

    pub fn finish(&self, id: &str, result: Result<Value, String>) {
        let mut all = self.jobs.lock().unwrap();
        if let Some(j) = all.get_mut(id) {
            j.close_stage();
            j.finished = Some(Instant::now());
            if result.is_ok() {
                self.last_ms.lock().unwrap().insert(j.mode.clone(), j.work_ms());
            }
            j.result = Some(result);
        }
    }

    pub fn view(&self, id: &str) -> Option<Value> {
        let all = self.jobs.lock().unwrap();
        let j = all.get(id)?;
        let status = match &j.result {
            None if j.stages.len() == 1 => "queued",
            None => "running",
            Some(Ok(_)) => "done",
            Some(Err(_)) => "failed",
        };
        let stages: Vec<Value> = j
            .stages
            .iter()
            .map(|s| match s.ms {
                Some(ms) => json!({ "name": s.name, "ms": ms }),
                None => json!({ "name": s.name, "elapsedMs": s.started.elapsed().as_millis() as u64 }),
            })
            .collect();
        let expected = self.last_ms.lock().unwrap().get(&j.mode).copied();
        let work = j.work_ms();
        let progress = match (&j.result, expected) {
            (Some(Ok(_)), _) => json!({ "fraction": 1.0 }),
            (None, Some(e)) if e > 0 => json!({
                "fraction": (work as f64 / e as f64).min(0.99),
                "etaMs": e.saturating_sub(work),
                "basis": "last finished job of this mode",
            }),
            _ => Value::Null,
        };
        let end = j.finished.unwrap_or_else(Instant::now);
        Some(json!({
            "id": id,
            "mode": j.mode,
            "format": j.format,
            "status": status,
            "stage": j.stages.last().map(|s| s.name.clone()),
            "stages": stages,
            "createdAt": j.created_unix,
            "elapsedMs": end.duration_since(j.created).as_millis() as u64,
            "progress": progress,
            "preview": j.preview,
            "result": j.result.as_ref().and_then(|r| r.as_ref().ok()),
            "error": j.result.as_ref().and_then(|r| r.as_ref().err()),
        }))
    }
}
