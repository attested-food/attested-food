//! Proving jobs: `POST /prove` returns a job id at once, `GET /jobs/{id}`
//! reports the stage, the stage history, an estimate of progress and, when
//! done, the result. Jobs live in memory and are dropped [`JOB_TTL`] after
//! they finish (a restart loses them).
//!
//! The provers report stages, and results that exist before the final one
//! (`partial`, e.g. SP1's compressed STARK ahead of its Groth16 proof),
//! through a [`Progress`] handle. A partial's `proof` (the STARK is 1.7 MB of
//! base64) is not in the polled view, which every few seconds would download
//! it again; the view has `proofUrl`, `GET /jobs/{id}/partial/{name}`, instead.
//! Progress is an
//! estimate: neither SDK reports a fraction done, so it is the elapsed working
//! time over the sum of the stage durations of the last finished job of the
//! same mode (time spent waiting for the prove lock or the queue excluded).
//!
//! A one-time job ([`Jobs::create_once`], `POST /tls/session`) holds a secret
//! result: the first view that sees it done hands it out and clears it, and
//! an unread result is dropped [`ONCE_TTL`] after the job finishes.

use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use serde_json::{json, Value};

/// How long a finished job stays readable.
pub const JOB_TTL: Duration = Duration::from_secs(3600);

/// How long the unread result of a one-time job stays readable.
pub const ONCE_TTL: Duration = Duration::from_secs(600);

/// Stages that are waiting, not work: left out of the progress estimate
/// (prefixes; the lock stage names its holder).
const WAITING: [&str; 4] = ["queued", "waiting for prove lock", "waiting for sp1 worker", "waiting for zktls slot"];

/// Reports the current stage of one job. Cheap to clone; a no-op for
/// synchronous callers that have no job.
#[derive(Clone)]
pub struct Progress(Option<(Arc<Jobs>, String)>);

impl Progress {
    pub fn none() -> Self {
        Progress(None)
    }

    pub fn stage(&self, name: &str) {
        if let Some((jobs, id)) = &self.0 {
            jobs.stage(id, name);
        }
    }

    pub fn job(&self) -> Option<&str> {
        self.0.as_ref().map(|(_, id)| id.as_str())
    }

    /// A result available before the job finishes, under `partial.<name>`.
    pub fn partial(&self, name: &str, value: Value) {
        if let Some((jobs, id)) = &self.0 {
            if let Some(j) = jobs.jobs.lock().unwrap().get_mut(id) {
                j.partial.insert(name.into(), value);
            }
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
    partial: serde_json::Map<String, Value>,
    result: Option<Result<Value, String>>,
    /// One-time job: the result is handed out once, then cleared.
    once: bool,
    /// A one-time job's result was read (or expired) and is gone.
    consumed: bool,
}

impl Job {
    fn expired(&self) -> bool {
        let ttl = if self.once { ONCE_TTL } else { JOB_TTL };
        self.finished.is_some_and(|f| f.elapsed() >= ttl)
    }

    fn close_stage(&mut self) {
        if let Some(s) = self.stages.last_mut() {
            s.ms.get_or_insert(s.started.elapsed().as_millis() as u64);
        }
    }

    fn work_ms(&self) -> u64 {
        self.stages
            .iter()
            .filter(|s| !WAITING.iter().any(|w| s.name.starts_with(w)))
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
        self.insert(mode, format, preview, false)
    }

    /// A one-time job (see the module docs), with a 128-bit random id.
    pub fn create_once(&self, mode: &str) -> String {
        self.insert(mode, "", Value::Null, true)
    }

    fn insert(&self, mode: &str, format: &str, preview: Value, once: bool) -> String {
        let mut buf = [0u8; 16];
        let buf = &mut buf[..if once { 16 } else { 12 }];
        getrandom::getrandom(buf).expect("random job id");
        let id = hex::encode(buf);
        let now = Instant::now();
        let mut jobs = self.jobs.lock().unwrap();
        jobs.retain(|_, j| !j.expired());
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
                partial: Default::default(),
                result: None,
                once,
                consumed: false,
            },
        );
        id
    }

    /// Drop expired jobs (and with them unread one-time results).
    pub fn sweep(&self) {
        self.jobs.lock().unwrap().retain(|_, j| !j.expired());
    }

    /// Whether `id` is a one-time job.
    pub fn is_once(&self, id: &str) -> bool {
        self.jobs.lock().unwrap().get(id).is_some_and(|j| j.once)
    }

    pub fn progress(self: &Arc<Self>, id: &str) -> Progress {
        Progress(Some((self.clone(), id.to_string())))
    }

    fn stage(&self, id: &str, name: &str) {
        if let Some(j) = self.jobs.lock().unwrap().get_mut(id) {
            if j.stages.last().is_some_and(|s| s.name == name) {
                return;
            }
            j.close_stage();
            j.stages.push(Stage { name: name.into(), started: Instant::now(), ms: None });
        }
    }

    /// Set the preview once it is known (after a server-side zktls fetch).
    pub fn set_preview(&self, id: &str, preview: Value) {
        if let Some(j) = self.jobs.lock().unwrap().get_mut(id) {
            j.preview = preview;
        }
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

    /// A partial result in full, `proof` included.
    pub fn partial_of(&self, id: &str, name: &str) -> Option<Value> {
        self.jobs.lock().unwrap().get(id)?.partial.get(name).cloned()
    }

    /// The job's view. For a one-time job that is done, the first call carries
    /// the result and clears it; later calls have `resultConsumed: true`.
    pub fn view(&self, id: &str) -> Option<Value> {
        let mut all = self.jobs.lock().unwrap();
        if all.get(id)?.once && all.get(id)?.expired() {
            all.remove(id);
            return None;
        }
        let j = all.get_mut(id)?;
        let handed = match (j.once && !j.consumed, &j.result) {
            (true, Some(Ok(_))) => {
                j.consumed = true;
                j.result.replace(Ok(Value::Null)).and_then(Result::ok)
            }
            _ => None,
        };
        let j = &*j;
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
        let mut view = json!({
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
            "partial": j
                .partial
                .iter()
                .map(|(name, v)| {
                    let mut v = v.clone();
                    if let Some(o) = v.as_object_mut() {
                        if o.remove("proof").is_some() {
                            o.insert("proofUrl".into(), json!(format!("/jobs/{id}/partial/{name}")));
                        }
                    }
                    (name.clone(), v)
                })
                .collect::<serde_json::Map<_, _>>(),
            "result": handed.as_ref().or(j.result.as_ref().and_then(|r| r.as_ref().ok())),
            "error": j.result.as_ref().and_then(|r| r.as_ref().err()),
        });
        if j.consumed && handed.is_none() {
            view["resultConsumed"] = json!(true);
        }
        Some(view)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn once_read() {
        let jobs = Jobs::default();
        let id = jobs.create_once("tls-session");
        assert_eq!(id.len(), 32);
        assert!(jobs.view(&id).unwrap()["result"].is_null());
        jobs.finish(&id, Ok(json!({ "blinder": "secret" })));
        let first = jobs.view(&id).unwrap();
        assert_eq!(first["status"], "done");
        assert_eq!(first["result"]["blinder"], "secret");
        for _ in 0..2 {
            let v = jobs.view(&id).unwrap();
            assert_eq!(v["status"], "done");
            assert!(v["result"].is_null());
            assert_eq!(v["resultConsumed"], true);
            assert!(!v.to_string().contains("secret"));
        }
        // Ordinary jobs keep their result.
        let p = jobs.create("stark", "eurekha", Value::Null);
        assert_eq!(p.len(), 24);
        jobs.finish(&p, Ok(json!(1)));
        assert_eq!(jobs.view(&p).unwrap()["result"], 1);
        assert_eq!(jobs.view(&p).unwrap()["result"], 1);
        assert!(jobs.view(&p).unwrap().get("resultConsumed").is_none());
    }

    #[test]
    fn once_ttl() {
        let jobs = Jobs::default();
        let (unread, fresh) = (jobs.create_once("tls-session"), jobs.create_once("tls-session"));
        let p = jobs.create("stark", "eurekha", Value::Null);
        for id in [&unread, &fresh, &p] {
            jobs.finish(id, Ok(json!({ "blinder": "secret" })));
        }
        let Some(past) = Instant::now().checked_sub(ONCE_TTL) else { return };
        for id in [&unread, &p] {
            jobs.jobs.lock().unwrap().get_mut(id).unwrap().finished = Some(past);
        }
        assert!(jobs.view(&unread).is_none());
        assert!(!jobs.is_once(&unread));
        assert_eq!(jobs.view(&fresh).unwrap()["result"]["blinder"], "secret");
        // A /prove job outlives ONCE_TTL.
        jobs.sweep();
        assert_eq!(jobs.view(&p).unwrap()["result"]["blinder"], "secret");
        // sweep() drops an expired one-time job without a view.
        let id = jobs.create_once("tls-session");
        jobs.finish(&id, Ok(json!(1)));
        jobs.jobs.lock().unwrap().get_mut(&id).unwrap().finished = Some(past);
        jobs.sweep();
        assert!(!jobs.is_once(&id));
    }
}
