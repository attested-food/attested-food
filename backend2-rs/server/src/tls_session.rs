//! `POST /tls/session`: a TLSNotary session of one report URL for a client
//! that proves on its own. JSON `{ "url" }` in, `202 { jobId, status,
//! statusUrl }` out; `GET /jobs/{id}` (mode `tls-session`, stage `zktls
//! fetch`) carries, when done, `result { onchain, request, blinder, bodySha256,
//! bodyLen, notary }`, once.
//!
//! The URL is a capability (its key is the link to the unredacted report): it
//! passes [`report_url::check_url`] before any network activity, is never
//! logged, and is scrubbed from errors. The result (`request` holds the key,
//! `blinder` opens the body commitment) lives in a one-time job
//! ([`Jobs::create_once`]). Abuse: one session at a time server-wide
//! ([`zktls::slot`]), at most [`MAX_PENDING`] queued or running, [`RATE`] per
//! client IP per [`WINDOW`], a [`MAX_BODY`] body, `application/json` only (so
//! a cross-origin browser request always preflights), and CORS limited to
//! `ALLOWED_ORIGINS` (comma-separated; default [`DEFAULT_ORIGINS`]). The
//! client IP is the peer, or behind nginx (peer on loopback) `X-Real-IP`, else
//! the last `X-Forwarded-For` entry.

use std::{
    collections::{HashMap, VecDeque},
    net::{IpAddr, Ipv6Addr, SocketAddr},
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, LazyLock, Mutex,
    },
    time::{Duration, Instant},
};

use axum::{
    extract::{ConnectInfo, Request, State},
    http::{header, HeaderMap, HeaderValue, Method, StatusCode},
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use equinox_core::{sha::sha256, tlsn};
use serde::Deserialize;
use serde_json::json;
use tower_http::cors::{AllowOrigin, CorsLayer};

use crate::{
    bad,
    jobs::Jobs,
    report_url,
    zktls::{self, Session},
    ApiError,
};

/// Largest request body.
pub const MAX_BODY: usize = 4096;
/// Sessions per client IP per [`WINDOW`].
pub const RATE: usize = 5;
pub const WINDOW: Duration = Duration::from_secs(600);
/// Sessions queued or running at once, server-wide.
pub const MAX_PENDING: usize = 4;

pub const DEFAULT_ORIGINS: &str = "https://prover.openlabel.fyi,http://localhost:5173,http://localhost:5180,\
     http://localhost:4173,http://127.0.0.1:5173,http://127.0.0.1:5180,http://127.0.0.1:4173";

/// Browser origins allowed to start a session and read its job.
pub static ORIGINS: LazyLock<Vec<HeaderValue>> = LazyLock::new(|| {
    std::env::var("ALLOWED_ORIGINS")
        .unwrap_or_else(|_| DEFAULT_ORIGINS.into())
        .split(',')
        .map(str::trim)
        .filter(|o| !o.is_empty() && *o != "*")
        .filter_map(|o| HeaderValue::from_str(o).ok())
        .collect()
});

/// No `Origin` (not a browser) or an allowed one.
pub fn origin_allowed(headers: &HeaderMap) -> bool {
    headers.get(header::ORIGIN).is_none_or(|o| ORIGINS.contains(o))
}

/// Runs one session for an already checked URL. Blocking.
pub type Fetch = Arc<dyn Fn(&str) -> Result<Session, String> + Send + Sync>;

#[derive(Clone)]
pub struct Config {
    jobs: Arc<Jobs>,
    fetch: Fetch,
    limit: Arc<RateLimit>,
    pending: Arc<AtomicUsize>,
}

impl Config {
    pub fn new(jobs: Arc<Jobs>, fetch: Fetch) -> Self {
        Config { jobs, fetch, limit: Default::default(), pending: Default::default() }
    }
}

/// The real [`Fetch`]: a proxy-mode session, its attestation checked against
/// the pinned notary and bound to the fetched body.
pub fn fetch_checked(url: &str) -> Result<Session, String> {
    let s = zktls::fetch(url)?;
    let notary = crate::notary_address().map_err(|e| e.1)?;
    let (t, _) = tlsn::from_onchain_json(&s.onchain)?;
    let body = tlsn::check(&t, &notary, &tlsn::K256Recover).map_err(|e| format!("attestation rejected: {e:?}"))?;
    let commitment = sha256(&equinox_core::input_buffer(&s.body, &s.blinder));
    tlsn::bind_body(&body, &commitment, s.body.len() as u64).map_err(|e| format!("attestation rejected: {e:?}"))?;
    Ok(s)
}

/// The `/tls/session` route with its own CORS.
pub fn router<S: Clone + Send + Sync + 'static>(cfg: Config) -> Router<S> {
    let cors = CorsLayer::new()
        .allow_origin(AllowOrigin::list(ORIGINS.iter().cloned()))
        .allow_methods([Method::POST])
        .allow_headers([header::CONTENT_TYPE])
        .max_age(Duration::from_secs(600));
    Router::new().route("/tls/session", post(session)).layer(cors).with_state(cfg)
}

/// Sliding-window count of sessions per client.
#[derive(Default)]
struct RateLimit(Mutex<HashMap<IpAddr, VecDeque<Instant>>>);

impl RateLimit {
    fn allow(&self, ip: IpAddr, now: Instant) -> bool {
        let mut all = self.0.lock().unwrap();
        all.retain(|_, q| {
            while q.front().is_some_and(|t| now.duration_since(*t) >= WINDOW) {
                q.pop_front();
            }
            !q.is_empty()
        });
        let q = all.entry(ip).or_default();
        if q.len() >= RATE {
            return false;
        }
        q.push_back(now);
        true
    }
}

/// Client IP for the rate limit; IPv6 by its /64.
fn client_ip(peer: Option<IpAddr>, h: &HeaderMap) -> IpAddr {
    let forwarded = || {
        let header = |n: &str| h.get(n).and_then(|v| v.to_str().ok());
        header("x-real-ip")
            .and_then(|s| s.trim().parse().ok())
            .or_else(|| header("x-forwarded-for")?.rsplit(',').next()?.trim().parse().ok())
    };
    let ip = match peer {
        Some(p) if p.is_loopback() => forwarded().unwrap_or(p),
        Some(p) => p,
        None => IpAddr::from([0, 0, 0, 0]),
    };
    match ip {
        IpAddr::V6(v6) => IpAddr::V6(Ipv6Addr::from(u128::from(v6) & !((1u128 << 64) - 1))),
        v4 => v4,
    }
}

/// Counts a session in [`Config::pending`] until dropped.
struct Pending(Arc<AtomicUsize>);

impl Drop for Pending {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::SeqCst);
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SessionRequest {
    url: String,
}

fn err(code: StatusCode, msg: &str) -> ApiError {
    ApiError(code, msg.into())
}

async fn session(State(cfg): State<Config>, req: Request) -> Result<Response, ApiError> {
    if !origin_allowed(req.headers()) {
        return Err(err(StatusCode::FORBIDDEN, "origin not allowed"));
    }
    let peer = req.extensions().get::<ConnectInfo<SocketAddr>>().map(|c| c.0.ip());
    if !cfg.limit.allow(client_ip(peer, req.headers()), Instant::now()) {
        return Err(err(StatusCode::TOO_MANY_REQUESTS, "rate limited: at most 5 TLS sessions per 10 minutes"));
    }
    let json = req
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .is_some_and(|v| v.split(';').next().is_some_and(|m| m.trim().eq_ignore_ascii_case("application/json")));
    if !json {
        return Err(err(StatusCode::UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json"));
    }
    let body = axum::body::to_bytes(req.into_body(), MAX_BODY)
        .await
        .map_err(|_| err(StatusCode::PAYLOAD_TOO_LARGE, "body over 4 KB"))?;
    // serde's message could quote the URL: answer with a fixed one.
    let url = serde_json::from_slice::<SessionRequest>(&body)
        .map_err(|_| bad(r#"body must be JSON { "url": "<report URL>" }"#))?
        .url;
    report_url::check_url(&url).map_err(bad)?;
    if cfg.pending.fetch_add(1, Ordering::SeqCst) >= MAX_PENDING {
        cfg.pending.fetch_sub(1, Ordering::SeqCst);
        return Err(err(StatusCode::SERVICE_UNAVAILABLE, "too many TLS sessions in progress, try again shortly"));
    }
    let pending = Pending(cfg.pending.clone());
    let id = cfg.jobs.create_once("tls-session");
    let (jobs, jid, fetch) = (cfg.jobs.clone(), id.clone(), cfg.fetch.clone());
    tokio::spawn(async move {
        let _pending = pending;
        let progress = jobs.progress(&jid);
        let slot = zktls::slot(&progress).await;
        progress.stage("zktls fetch");
        let r = tokio::task::spawn_blocking(move || {
            let r = fetch(&url).map_err(|e| zktls::scrub(e, &url));
            drop(url);
            r
        })
        .await
        .map_err(|e| e.to_string())
        .and_then(|r| r);
        drop(slot);
        let r = r.and_then(|s| {
            let notary = crate::notary_address().map_err(|e| e.1)?;
            Ok(json!({
                "onchain": s.onchain,
                "request": s.request,
                "blinder": hex::encode(s.blinder),
                "bodySha256": hex::encode(sha256(&s.body)),
                "bodyLen": s.body.len(),
                "notary": hex::encode(notary),
            }))
        });
        if let Err(e) = &r {
            tracing::warn!(job = %jid, "tls session failed: {e}");
        }
        jobs.finish(&jid, r);
    });
    let body = json!({ "jobId": id, "status": "queued", "statusUrl": format!("/jobs/{id}") });
    Ok((StatusCode::ACCEPTED, Json(body)).into_response())
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::AtomicUsize;

    use axum::{body::Body, http::Request};
    use tower::ServiceExt;

    use super::*;

    const URL: &str = "https://eurekhalabs.s3.amazonaws.com/reports/2026/x-0123.pdf";

    fn fake(calls: Arc<AtomicUsize>, fail: bool) -> Fetch {
        Arc::new(move |url: &str| {
            calls.fetch_add(1, Ordering::SeqCst);
            match fail {
                true => Err(format!("zktls session failed: GET {url} returned 403")),
                false => Ok(Session {
                    body: b"%PDF-1.4 fake".to_vec(),
                    blinder: [7; 16],
                    onchain: r#"{"header":"00"}"#.into(),
                    request: r#"{"request":"GET /reports/2026/x-0123.pdf"}"#.into(),
                }),
            }
        })
    }

    fn post(body: &str, peer: [u8; 4], headers: &[(&str, &str)]) -> Request<Body> {
        let mut b = Request::post("/tls/session").header("content-type", "application/json");
        for (k, v) in headers {
            b = b.header(*k, *v);
        }
        let mut req = b.body(Body::from(body.to_string())).unwrap();
        req.extensions_mut().insert(ConnectInfo(SocketAddr::from((peer, 4000))));
        req
    }

    async fn call(app: &Router, req: Request<Body>) -> (StatusCode, HeaderMap, serde_json::Value) {
        let res = app.clone().oneshot(req).await.unwrap();
        let (status, headers) = (res.status(), res.headers().clone());
        let bytes = axum::body::to_bytes(res.into_body(), 1 << 20).await.unwrap();
        (status, headers, serde_json::from_slice(&bytes).unwrap_or_default())
    }

    async fn done(jobs: &Jobs, id: &str) -> serde_json::Value {
        for _ in 0..200 {
            if jobs.is_once(id) {
                let v = jobs.view(id).unwrap();
                if v["status"] == "done" || v["status"] == "failed" {
                    return v;
                }
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
        panic!("job did not finish");
    }

    fn url_body(url: &str) -> String {
        json!({ "url": url }).to_string()
    }

    #[tokio::test]
    async fn session_once() {
        let (jobs, calls) = (Arc::new(Jobs::default()), Arc::new(AtomicUsize::new(0)));
        let app: Router = router(Config::new(jobs.clone(), fake(calls.clone(), false)));
        let (s, _, v) = call(&app, post(&url_body(URL), [1, 2, 3, 4], &[])).await;
        assert_eq!(s, StatusCode::ACCEPTED);
        let id = v["jobId"].as_str().unwrap().to_string();
        assert_eq!(id.len(), 32);
        assert_eq!(v["statusUrl"], format!("/jobs/{id}"));
        let v = done(&jobs, &id).await;
        assert_eq!(v["mode"], "tls-session");
        // Other tests share the session slot: there may be a wait stage first.
        assert!(v["stages"].as_array().unwrap().iter().any(|s| s["name"] == "zktls fetch"), "{v}");
        let r = &v["result"];
        assert_eq!(r["blinder"], "07".repeat(16));
        assert_eq!(r["bodySha256"], hex::encode(sha256(b"%PDF-1.4 fake")));
        assert_eq!(r["bodyLen"], 13);
        assert_eq!(r["notary"], crate::DEV_NOTARY);
        assert!(r["request"].as_str().unwrap().contains("x-0123"));
        assert!(v.get("resultConsumed").is_none());
        // Read once: the second view has no result.
        let again = jobs.view(&id).unwrap();
        assert_eq!(again["status"], "done");
        assert!(again["result"].is_null());
        assert_eq!(again["resultConsumed"], true);
        assert!(!again.to_string().contains("x-0123"));
        assert_eq!(calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn rejects_before_fetch() {
        let (jobs, calls) = (Arc::new(Jobs::default()), Arc::new(AtomicUsize::new(0)));
        let app: Router = router(Config::new(jobs, fake(calls.clone(), false)));
        let evil = "https://eurekhalabs.s3.amazonaws.com@evil.com/reports/x.pdf";
        let (s, _, v) = call(&app, post(&url_body(evil), [1, 1, 1, 1], &[])).await;
        assert_eq!(s, StatusCode::BAD_REQUEST);
        assert!(!v.to_string().contains("evil"));
        let (s, _, v) = call(&app, post(r#"{"url": 1, "x": "secret-key"}"#, [1, 1, 1, 2], &[])).await;
        assert_eq!(s, StatusCode::BAD_REQUEST);
        assert!(!v.to_string().contains("secret-key"));
        let big = url_body(&format!("{URL}{}", "a".repeat(MAX_BODY)));
        let (s, _, _) = call(&app, post(&big, [1, 1, 1, 3], &[])).await;
        assert_eq!(s, StatusCode::PAYLOAD_TOO_LARGE);
        let mut req = post(&url_body(URL), [1, 1, 1, 4], &[]);
        req.headers_mut().insert(header::CONTENT_TYPE, HeaderValue::from_static("text/plain"));
        assert_eq!(call(&app, req).await.0, StatusCode::UNSUPPORTED_MEDIA_TYPE);
        let (s, _, _) = call(&app, post(&url_body(URL), [1, 1, 1, 5], &[("origin", "https://evil.com")])).await;
        assert_eq!(s, StatusCode::FORBIDDEN);
        assert_eq!(calls.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn fetch_error_hides_url() {
        let (jobs, calls) = (Arc::new(Jobs::default()), Arc::new(AtomicUsize::new(0)));
        let app: Router = router(Config::new(jobs.clone(), fake(calls, true)));
        let (_, _, v) = call(&app, post(&url_body(URL), [1, 2, 3, 4], &[])).await;
        let v = done(&jobs, v["jobId"].as_str().unwrap()).await;
        assert_eq!(v["status"], "failed");
        assert!(!v.to_string().contains("x-0123"), "{v}");
    }

    #[tokio::test]
    async fn cors() {
        let app: Router = router(Config::new(Default::default(), fake(Default::default(), false)));
        let preflight = |origin: &'static str| {
            Request::options("/tls/session")
                .header("origin", origin)
                .header("access-control-request-method", "POST")
                .header("access-control-request-headers", "content-type")
                .body(Body::empty())
                .unwrap()
        };
        let (_, h, _) = call(&app, preflight("http://localhost:5173")).await;
        assert_eq!(h.get("access-control-allow-origin").unwrap(), "http://localhost:5173");
        let (_, h, _) = call(&app, preflight("https://evil.com")).await;
        assert!(h.get("access-control-allow-origin").is_none());
    }

    #[tokio::test]
    async fn rate_limit() {
        let app: Router = router(Config::new(Default::default(), fake(Default::default(), false)));
        // Each request finishes at once, so MAX_PENDING is not the limit here.
        for i in 0..RATE {
            let (s, _, _) = call(&app, post(&url_body(URL), [127, 0, 0, 1], &[("x-real-ip", "9.9.9.9")])).await;
            assert_eq!(s, StatusCode::ACCEPTED, "request {i}");
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
        let (s, _, _) = call(&app, post(&url_body(URL), [127, 0, 0, 1], &[("x-real-ip", "9.9.9.9")])).await;
        assert_eq!(s, StatusCode::TOO_MANY_REQUESTS);
        // Another client behind nginx, and a spoofed header from a non-loopback peer.
        let (s, _, _) =
            call(&app, post(&url_body(URL), [127, 0, 0, 1], &[("x-forwarded-for", "1.1.1.1, 8.8.8.8")])).await;
        assert_eq!(s, StatusCode::ACCEPTED);
        let (s, _, _) = call(&app, post(&url_body(URL), [5, 5, 5, 5], &[("x-real-ip", "9.9.9.9")])).await;
        assert_eq!(s, StatusCode::ACCEPTED);
    }

    #[test]
    fn client_ips() {
        let mut h = HeaderMap::new();
        h.insert("x-real-ip", HeaderValue::from_static("9.9.9.9"));
        assert_eq!(client_ip(Some([127, 0, 0, 1].into()), &h), IpAddr::from([9, 9, 9, 9]));
        assert_eq!(client_ip(Some([5, 5, 5, 5].into()), &h), IpAddr::from([5, 5, 5, 5]));
        let v6: IpAddr = "2001:db8::1".parse().unwrap();
        assert_eq!(client_ip(Some(v6), &HeaderMap::new()), "2001:db8::".parse::<IpAddr>().unwrap());
    }
}
