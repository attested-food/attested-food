//! `equinox-openvm-server`: an Equinox lab-report PDF in, an OpenVM STARK
//! proof of the chosen test values out.
//!
//! - `GET  /health`: is the guest built.
//! - `GET  /program`: the pinned program's commitments (runs keygen once).
//! - `POST /prove?mode=stark|execute`: multipart `pdf` (file), optional
//!   `labels` (comma-separated analytes) and `blinder` (32 hex chars; random
//!   if absent). Runs the extraction natively first (rejects a bad PDF and
//!   anything that would publish customer PII), then executes the guest and,
//!   for `stark`, proves, verifies and returns the proof.
//! - `POST /verify`: JSON `{ proof, publicValues }` (base64, hex).
//!
//! `BIND` (default `127.0.0.1:8793`), `RUST_LOG`.

mod prover;

use std::{panic::AssertUnwindSafe, time::Instant};

use axum::{
    extract::{DefaultBodyLimit, Multipart, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use equinox_core::{PublicValues, BLINDER_LEN, DEFAULT_LABELS};
use prover::{GuestInput, ProgramCommit, Prover, Timings};
use serde::{Deserialize, Serialize};
use serde_json::json;
use tower_http::{cors::CorsLayer, trace::TraceLayer};

struct ApiError(StatusCode, String);

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.0, Json(json!({ "error": self.1 }))).into_response()
    }
}

fn bad(msg: impl Into<String>) -> ApiError {
    ApiError(StatusCode::BAD_REQUEST, msg.into())
}

fn internal(msg: impl Into<String>) -> ApiError {
    ApiError(StatusCode::INTERNAL_SERVER_ERROR, msg.into())
}

/// `PublicValues` as JSON with the 32-byte body commitment in hex.
fn pv_json(pv: &PublicValues) -> serde_json::Value {
    let mut v = serde_json::to_value(pv).unwrap_or_default();
    v["body_commitment"] = json!(hex::encode(pv.body_commitment));
    v
}

#[derive(Deserialize)]
struct ProveQuery {
    #[serde(default = "default_mode")]
    mode: String,
}

fn default_mode() -> String {
    "stark".into()
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ProveResponse {
    mode: String,
    /// `equinox` or `eurekha`.
    format: String,
    /// Decoded public values (hashes in hex). Equinox: report number, product,
    /// ULR, issue date, chosen rows, body commitment. Eurekha: body
    /// commitment, redacted-PDF hash and spans, every non-customer key-value
    /// pair and result row.
    public_values: serde_json::Value,
    /// Eurekha: the redacted PDF (base64), the file whose sha256 is committed.
    #[serde(skip_serializing_if = "Option::is_none")]
    redacted_pdf: Option<String>,
    public_values_hex: String,
    /// What the guest revealed: `sha256(public_values)`.
    revealed: String,
    blinder: String,
    instructions: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    program: Option<ProgramCommit>,
    /// base64 of bincode `VersionedVmStarkProof` (stark mode).
    #[serde(skip_serializing_if = "Option::is_none")]
    proof: Option<String>,
    proof_bytes: usize,
    timings_ms: TimingsOut,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct TimingsOut {
    preflight: u64,
    #[serde(flatten)]
    prover: Timings,
    total: u64,
}

/// Fields of the `/prove` form.
struct Form {
    format: Format,
    pdf: Vec<u8>,
    labels: Vec<String>,
    blinder: [u8; BLINDER_LEN],
}

async fn read_form(mut mp: Multipart) -> Result<Form, ApiError> {
    let (mut pdf, mut labels, mut blinder, mut format) = (None, Vec::new(), None, Format::Equinox);
    while let Some(field) = mp.next_field().await.map_err(|e| bad(format!("multipart: {e}")))? {
        match field.name() {
            Some("pdf") => pdf = Some(field.bytes().await.map_err(|e| bad(format!("pdf: {e}")))?.to_vec()),
            Some("labels") => {
                let s = field.text().await.map_err(|e| bad(format!("labels: {e}")))?;
                labels = s.split(',').map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).collect();
            }
            Some("format") => {
                format = match field.text().await.map_err(|e| bad(format!("format: {e}")))?.trim() {
                    "equinox" => Format::Equinox,
                    "eurekha" => Format::Eurekha,
                    f => return Err(bad(format!("unknown format {f:?} (equinox | eurekha)"))),
                }
            }
            Some("blinder") => {
                let s = field.text().await.map_err(|e| bad(format!("blinder: {e}")))?;
                let b = hex::decode(s.trim().trim_start_matches("0x")).map_err(|e| bad(format!("blinder: {e}")))?;
                blinder = Some(b.try_into().map_err(|_| bad(format!("blinder must be {BLINDER_LEN} bytes")))?);
            }
            _ => {}
        }
    }
    let pdf = pdf.ok_or_else(|| bad("missing `pdf` file field"))?;
    if labels.is_empty() {
        labels = DEFAULT_LABELS.iter().map(|s| s.to_string()).collect();
    }
    let blinder = match blinder {
        Some(b) => b,
        None => {
            let mut b = [0u8; BLINDER_LEN];
            getrandom::getrandom(&mut b).map_err(|e| internal(format!("random blinder: {e}")))?;
            b
        }
    };
    Ok(Form { format, pdf, labels, blinder })
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Format {
    Equinox,
    Eurekha,
}

impl Format {
    fn byte(self) -> u8 {
        self as u8
    }

    fn name(self) -> &'static str {
        match self {
            Format::Equinox => "equinox",
            Format::Eurekha => "eurekha",
        }
    }
}

/// What the native preflight produces: the bytes the guest must commit, their
/// JSON view, and (Eurekha) the redacted PDF.
struct Preflight {
    public_values: Vec<u8>,
    json: serde_json::Value,
    redacted_pdf: Option<Vec<u8>>,
}

fn catch<T>(f: impl FnOnce() -> T) -> Result<T, ApiError> {
    std::panic::catch_unwind(AssertUnwindSafe(f)).map_err(|e| {
        let msg = e
            .downcast_ref::<&str>()
            .map(|s| s.to_string())
            .or_else(|| e.downcast_ref::<String>().cloned())
            .unwrap_or_else(|| "extraction panicked".into());
        bad(format!("PDF rejected: {msg}"))
    })
}

/// Native run of the same code the guest proves: rejects a PDF the guest would
/// reject (before seconds of proving) and checks no customer PII is published.
fn preflight(format: Format, buffer: &[u8], labels: &[String]) -> Result<Preflight, ApiError> {
    match format {
        Format::Equinox => {
            let out = catch(|| equinox_core::run(buffer, labels))?;
            let pii = out.pii.clone();
            let pv = PublicValues::from(out);
            let bytes = pv.encode();
            let lc = String::from_utf8_lossy(&bytes).to_lowercase();
            if pii.iter().any(|w| lc.contains(w.as_str())) {
                return Err(bad("customer PII found in public values"));
            }
            Ok(Preflight { public_values: bytes, json: pv_json(&pv), redacted_pdf: None })
        }
        Format::Eurekha => {
            // eurekha::run asserts the PII-line leak check itself.
            let out = catch(|| equinox_core::eurekha::run(buffer))?;
            let mut redacted = buffer[..out.pdf_len as usize].to_vec();
            for &(s, e) in &out.spans {
                redacted[s as usize..e as usize].fill(b'0');
            }
            let mut json = serde_json::to_value(&out).unwrap_or_default();
            json["body_commitment"] = json!(hex::encode(out.body_commitment));
            json["redacted_sha256"] = json!(hex::encode(out.redacted_sha256));
            Ok(Preflight { public_values: out.encode(), json, redacted_pdf: Some(redacted) })
        }
    }
}

async fn prove(
    State(prover): State<Prover>,
    Query(q): Query<ProveQuery>,
    mp: Multipart,
) -> Result<Json<ProveResponse>, ApiError> {
    let stark = match q.mode.as_str() {
        "stark" => true,
        "execute" => false,
        m => return Err(bad(format!("unknown mode {m:?} (stark | execute)"))),
    };
    let form = read_form(mp).await?;
    let total = Instant::now();
    let buffer = equinox_core::input_buffer(&form.pdf, &form.blinder);

    let t = Instant::now();
    let format = form.format;
    let (buffer, labels, pre) = tokio::task::spawn_blocking(move || {
        let pre = preflight(format, &buffer, &form.labels)?;
        Ok::<_, ApiError>((buffer, form.labels, pre))
    })
    .await
    .map_err(|e| internal(e.to_string()))??;
    let public_values = pre.public_values;
    let preflight_ms = t.elapsed().as_millis() as u64;
    tracing::info!(format = format.name(), pdf_bytes = form.pdf.len(), preflight_ms, "preflight ok");

    let proved = prover.run(GuestInput { format: format.byte(), labels, buffer }, stark).await.map_err(internal)?;
    if proved.revealed != equinox_core::sha::sha256(&public_values) {
        return Err(internal("guest revealed digest is not sha256(public values)"));
    }
    tracing::info!(instructions = proved.instructions, proof_bytes = proved.proof.len(), "done");
    Ok(Json(ProveResponse {
        mode: q.mode,
        format: format.name().into(),
        public_values: pre.json,
        redacted_pdf: pre.redacted_pdf.map(|b| B64.encode(b)),
        public_values_hex: hex::encode(&public_values),
        revealed: hex::encode(&proved.revealed),
        blinder: hex::encode(form.blinder),
        instructions: proved.instructions,
        program: proved.program,
        proof_bytes: proved.proof.len(),
        proof: stark.then(|| B64.encode(&proved.proof)),
        timings_ms: TimingsOut {
            preflight: preflight_ms,
            prover: proved.timings,
            total: total.elapsed().as_millis() as u64,
        },
    }))
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct VerifyRequest {
    proof: String,
    public_values: String,
}

async fn verify(
    State(prover): State<Prover>,
    Json(req): Json<VerifyRequest>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let proof = B64.decode(req.proof.trim()).map_err(|e| bad(format!("proof: {e}")))?;
    let pv = hex::decode(req.public_values.trim().trim_start_matches("0x"))
        .map_err(|e| bad(format!("publicValues: {e}")))?;
    let revealed = prover.verify(proof).await.map_err(bad)?;
    if revealed != equinox_core::sha::sha256(&pv) {
        return Err(bad("proof does not commit to these public values"));
    }
    // Equinox public values decode; Eurekha ones are returned as committed.
    let decoded = PublicValues::decode(&pv).map(|d| pv_json(&d)).unwrap_or(serde_json::Value::Null);
    Ok(Json(json!({ "valid": true, "publicValues": decoded, "program": prover.program().await.map_err(internal)? })))
}

async fn program(State(prover): State<Prover>) -> Result<Json<ProgramCommit>, ApiError> {
    prover.program().await.map(Json).map_err(internal)
}

async fn health() -> Json<serde_json::Value> {
    match prover::guest_built() {
        Ok(n) => Json(json!({ "ok": true, "guestElfBytes": n })),
        Err(e) => Json(json!({ "ok": false, "error": e })),
    }
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            // OpenVM logs every AIR at info; keep this server's and HTTP lines only.
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "warn,equinox_openvm_server=info,tower_http=info".into()),
        )
        .init();
    let prover = Prover::spawn();
    let app = Router::new()
        .route("/health", get(health))
        .route("/program", get(program))
        .route("/prove", post(prove))
        .route("/verify", post(verify))
        // A report PDF is a few hundred KB; a base64 proof under 1 MB.
        .layer(DefaultBodyLimit::max(16 << 20))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(prover);
    let bind = std::env::var("BIND").unwrap_or_else(|_| "127.0.0.1:8793".into());
    let listener = tokio::net::TcpListener::bind(&bind).await.expect("bind");
    tracing::info!("listening on http://{bind}");
    axum::serve(listener, app).await.expect("serve");
}
