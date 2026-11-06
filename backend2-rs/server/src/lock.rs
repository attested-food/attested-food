//! The machine-wide prove lock. Every heavy step (OpenVM keygen and proving,
//! SP1 start-up and proving) takes it right before it starts and drops it
//! right after, so the server holds it only while it is working, and waits
//! (never skips) while a build, benchmark or other prover holds it.
//!
//! Two kinds:
//!
//! - `PROVE_FLOCK=<file>`: an exclusive `flock` on that file, the protocol of
//!   the GPU box's `heavy` (`~/locks/cpugpu.lock`). While holding, the server
//!   writes its holder line to the sibling `.holder` file; while waiting, it
//!   registers in the sibling `waiting/` dir, so `heavy status` lists it. The
//!   waiting job's stage names the current holder.
//! - otherwise the Equinox backend's `mkdir` lock [`PROVE_LOCK`].

use std::{
    os::fd::AsRawFd,
    path::{Path, PathBuf},
    sync::mpsc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use crate::jobs::Progress;

/// The backend's machine-wide `mkdir` lock: at most one heavy proof per host
/// (OpenVM peaks near 19 GB).
const PROVE_LOCK: &str = "/tmp/equinox-prove.lock.d";

/// How often a waiting job re-reads who holds the lock.
const POLL: Duration = Duration::from_secs(2);

/// Held until dropped.
pub(crate) enum ProveLock {
    Dir,
    Flock { _file: std::fs::File, holder: Option<PathBuf> },
}

/// `HH:MM:SS` UTC, as `heavy` writes it.
fn now_utc() -> String {
    let s = SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |d| d.as_secs()) % 86_400;
    format!("{:02}:{:02}:{:02}", s / 3600, s / 60 % 60, s % 60)
}

impl ProveLock {
    /// Waits until held. `label` names the work in the holder line (e.g.
    /// `job <id> sp1-groth16`, `openvm keygen`); while waiting, `progress`
    /// gets the stage `waiting for prove lock (held by ...)`.
    pub(crate) fn acquire(label: &str, progress: &Progress) -> std::io::Result<Self> {
        match std::env::var_os("PROVE_FLOCK") {
            Some(path) => Self::flock(Path::new(&path), label, progress),
            None => Self::dir(progress),
        }
    }

    /// The lock if it is free right now; `None` if someone holds it.
    pub(crate) fn try_acquire(label: &str) -> std::io::Result<Option<Self>> {
        let Some(path) = std::env::var_os("PROVE_FLOCK") else {
            return match std::fs::create_dir(PROVE_LOCK) {
                Ok(()) => Ok(Some(ProveLock::Dir)),
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => Ok(None),
                Err(e) => Err(e),
            };
        };
        let path = Path::new(&path);
        let file = std::fs::OpenOptions::new().create(true).append(true).open(path)?;
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Ok(None);
        }
        let holder = path.extension().is_some_and(|e| e == "lock").then(|| path.with_extension("holder"));
        if let Some(h) = &holder {
            let _ = std::fs::write(h, format!("backend2-rs {label} pid={} since={}\n", std::process::id(), now_utc()));
        }
        Ok(Some(ProveLock::Flock { _file: file, holder }))
    }

    fn dir(progress: &Progress) -> std::io::Result<Self> {
        let mut waited = false;
        loop {
            match std::fs::create_dir(PROVE_LOCK) {
                Ok(()) => return Ok(ProveLock::Dir),
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                    if !waited {
                        tracing::info!("waiting for {PROVE_LOCK} ...");
                        progress.stage("waiting for prove lock");
                        waited = true;
                    }
                    std::thread::sleep(POLL);
                }
                Err(e) => return Err(e),
            }
        }
    }

    fn flock(path: &Path, label: &str, progress: &Progress) -> std::io::Result<Self> {
        let file = std::fs::OpenOptions::new().create(true).append(true).open(path)?;
        let is_heavy = path.extension().is_some_and(|e| e == "lock");
        let holder = is_heavy.then(|| path.with_extension("holder"));
        let me = format!("backend2-rs {label} pid={}", std::process::id());

        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            // A blocking flock in a helper thread keeps the kernel's queue
            // order with `heavy`'s waiters; this thread reports who holds it.
            // `heavy status` reads `waiting/<pid>`; one entry per process, so
            // only the waiter whose line is there removes it.
            let waiting = is_heavy.then(|| path.with_file_name("waiting").join(std::process::id().to_string()));
            let line = format!("{me} since={}\n", now_utc());
            if let Some(w) = &waiting {
                let _ = std::fs::write(w, &line);
            }
            tracing::info!("{label}: waiting for {} ...", path.display());
            let fd = file.as_raw_fd();
            let (tx, rx) = mpsc::channel();
            std::thread::spawn(move || {
                let r = unsafe { libc::flock(fd, libc::LOCK_EX) };
                let _ = tx.send(if r == 0 { Ok(()) } else { Err(std::io::Error::last_os_error()) });
            });
            let res = loop {
                let held_by = holder
                    .as_ref()
                    .and_then(|h| std::fs::read_to_string(h).ok())
                    .map(|s| s.split(" cmd=").next().unwrap_or("").trim().to_string())
                    .filter(|s| !s.is_empty());
                progress.stage(&match held_by {
                    Some(h) => format!("waiting for prove lock (held by {h})"),
                    None => "waiting for prove lock".into(),
                });
                match rx.recv_timeout(POLL) {
                    Ok(r) => break r,
                    Err(mpsc::RecvTimeoutError::Timeout) => {}
                    Err(mpsc::RecvTimeoutError::Disconnected) => {
                        break Err(std::io::Error::other("lock waiter thread died"));
                    }
                }
            };
            if let Some(w) = waiting.as_ref().filter(|w| std::fs::read_to_string(w).is_ok_and(|s| s == line)) {
                let _ = std::fs::remove_file(w);
            }
            res?;
        }
        if let Some(h) = &holder {
            let _ = std::fs::write(h, format!("{me} since={}\n", now_utc()));
        }
        tracing::info!("{label}: holding {}", path.display());
        Ok(ProveLock::Flock { _file: file, holder })
    }
}

impl Drop for ProveLock {
    fn drop(&mut self) {
        match self {
            ProveLock::Dir => {
                let _ = std::fs::remove_dir(PROVE_LOCK);
            }
            ProveLock::Flock { holder, .. } => {
                if let Some(h) = holder {
                    let _ = std::fs::write(h, "");
                }
            }
        }
    }
}
