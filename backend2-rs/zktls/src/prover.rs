//! Server-side TLSNotary prover (the server sees the PDF; the browser prover
//! via tlsn-wasm is the private default). Runs the notary in-process over a
//! duplex, so one call does the TLS session + attestation + presentation, in
//! MPC mode (the prover dials the server, ~59 s and ~22 GB peak RSS on the
//! PoC Mac) or proxy mode (the notary dials the server and relays the TLS
//! bytes, the prover proves the plaintext in ZK). Ported from the PoC
//! `equinox_fetch_pdf`. Callers must serialize sessions.

use std::{future::IntoFuture, ops::Range, path::Path, time::Instant};

use anyhow::{bail, Context, Result};
use futures::io::{AsyncReadExt as _, AsyncWriteExt as _};
use http_body_util::Empty;
use hyper::{body::Bytes, Request, StatusCode, Uri};
use hyper_util::rt::TokioIo;
use serde::Serialize;
use sha2::{Digest, Sha256};
use tlsn::{
    attestation::{
        presentation::Presentation,
        request::{Request as AttestationRequest, RequestConfig},
        signing::SignatureAlgId,
        Attestation, CryptoProvider,
    },
    config::{
        prove::ProveConfig,
        prover::ProverConfig,
        tls::TlsClientConfig,
        tls_commit::{mpc::MpcTlsConfig, proxy::ProxyTlsConfig},
    },
    connection::{DnsName, HandshakeData, ServerName},
    hash::HashAlgId,
    prover::{state as prover_state, Prover, ProverOutput},
    transcript::{Direction, TranscriptCommitConfig, TranscriptCommitment, TranscriptCommitmentKind, TranscriptSecret},
    webpki::RootCertStore,
    Session, SessionHandle,
};
use tokio::{
    io::{AsyncRead, AsyncWrite},
    task::JoinHandle,
};
use tokio_util::compat::{Compat, FuturesAsyncReadCompatExt, TokioAsyncReadCompatExt};

pub use crate::policy::{response_layout, ResponseLayout};
use crate::{
    notary::{notarize, NotaryConfig},
    policy::plan,
    proxy::check_s3_url,
    RequestSecret, TlsMode,
};

const USER_AGENT: &str =
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36";

pub(crate) const SHA256_KIND: TranscriptCommitmentKind = TranscriptCommitmentKind::Hash { alg: HashAlgId::SHA256 };

#[derive(Clone, Debug)]
pub struct ProverOptions {
    pub mode: TlsMode,
    /// Max bytes the prover expects to receive (object + headers).
    pub max_recv: usize,
    pub max_sent: usize,
}

impl Default for ProverOptions {
    fn default() -> Self {
        ProverOptions { mode: TlsMode::Mpc, max_recv: 1 << 20, max_sent: 1 << 12 }
    }
}

/// Coarse TLS stages for progress events.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum TlsStage {
    /// MPC setup + TLS handshake + request/response.
    Session,
    /// Commitments proven to the notary, attestation signed.
    Notarize,
    /// Presentation built.
    Present,
}

/// Everything one session produces. `body`, `blinder` and `secrets` are
/// PRIVATE (the body holds the customer PII); the rest is public.
pub struct TlsSession {
    pub mode: TlsMode,
    pub host: String,
    /// `server` (this module) or `browser` (`crate::browser`).
    pub prover: &'static str,
    pub body: Vec<u8>,
    pub blinder: [u8; 16],
    /// bincode `Attestation`.
    pub attestation: Vec<u8>,
    /// bincode `Secrets` (private: lets the holder build new presentations).
    /// Empty for browser sessions (the notary built the presentation).
    pub secrets: Vec<u8>,
    /// bincode `Presentation` (public).
    pub presentation: Vec<u8>,
    pub body_commitment: [u8; 32],
    pub body_range: Range<usize>,
    /// The sent transcript and the blinders of its three commitments (`GET `,
    /// path, rest). PRIVATE: the path is the object key.
    pub request: RequestSecret,
    pub sent_len: usize,
    pub recv_len: usize,
    pub tls_version: String,
    pub timings: TlsTimings,
}

#[derive(Clone, Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TlsTimings {
    /// TLS session (MPC or proxy) + notarization.
    pub session_ms: u64,
    pub present_ms: u64,
    pub total_ms: u64,
}

impl TlsSession {
    /// Public summary (what `/tls/prove` returns and `tlsn_result.json` holds).
    pub fn summary(&self) -> serde_json::Value {
        serde_json::json!({
            "host": self.host,
            "mode": self.mode,
            "prover": self.prover,
            "bodyLen": self.body.len(),
            "bodyRange": [self.body_range.start, self.body_range.end],
            "bodyCommitmentHex": hex::encode(self.body_commitment),
            "commitmentAlg": "sha256(body || blinder16)",
            "sentLen": self.sent_len,
            "recvLen": self.recv_len,
            "attestationBytes": self.attestation.len(),
            "presentationBytes": self.presentation.len(),
            "notarySigAlg": "secp256k1eth",
            "tlsVersion": self.tls_version,
            "timings": self.timings,
        })
    }

    /// Write the PoC run-dir layout (body.pdf, blinder.hex, attestation.bin,
    /// secrets.bin when present, presentation.bin, commitment.json,
    /// tlsn_result.json, onchain.json) plus request.json (private request
    /// opening).
    pub fn write_dir(&self, dir: &Path) -> Result<()> {
        std::fs::create_dir_all(dir)?;
        std::fs::write(dir.join("body.pdf"), &self.body)?;
        std::fs::write(dir.join("attestation.bin"), &self.attestation)?;
        if !self.secrets.is_empty() {
            std::fs::write(dir.join("secrets.bin"), &self.secrets)?;
        }
        std::fs::write(dir.join("presentation.bin"), &self.presentation)?;
        let onchain = crate::onchain::export(&self.presentation)?.to_json();
        std::fs::write(dir.join("onchain.json"), serde_json::to_string_pretty(&onchain)?)?;
        std::fs::write(dir.join("blinder.hex"), hex::encode(self.blinder))?;
        std::fs::write(dir.join("request.json"), serde_json::to_string_pretty(&self.request)?)?;
        std::fs::write(
            dir.join("commitment.json"),
            serde_json::to_string_pretty(&serde_json::json!({
                "direction": "Received",
                "range": [self.body_range.start, self.body_range.end],
                "alg": "sha256",
                "formula": "SHA256(body || blinder), blinder = 16 bytes",
                "commitmentHex": hex::encode(self.body_commitment),
            }))?,
        )?;
        std::fs::write(dir.join("tlsn_result.json"), serde_json::to_string_pretty(&self.summary())?)?;
        Ok(())
    }
}

/// Fetch `url` (must be an allowlisted S3 report URL) through a TLSNotary
/// session with an in-process notary.
pub async fn prove_url(
    url: &str,
    notary: &NotaryConfig,
    opts: &ProverOptions,
    on_stage: &(dyn Fn(TlsStage, u64) + Send + Sync),
) -> Result<TlsSession> {
    check_s3_url(url)?;
    if !notary.accepts(opts.mode) {
        bail!("the notary does not accept {} mode", opts.mode);
    }
    let total = Instant::now();
    let (notary_socket, prover_socket) = tokio::io::duplex(1 << 23);
    let ncfg = notary.clone();
    let notary_task = tokio::spawn(async move { notarize(notary_socket, &ncfg).await });
    let out = prover(prover_socket, url, opts, on_stage, total).await;
    let notary_res = notary_task.await?;
    let mut out = out?;
    notary_res?;
    out.timings.total_ms = total.elapsed().as_millis() as u64;
    Ok(out)
}

/// One finished TLS session on the prover side, nothing proven yet.
pub(crate) struct Fetched<S> {
    pub prover: Prover<prover_state::Committed>,
    pub handle: SessionHandle,
    pub driver: JoinHandle<tlsn::Result<Compat<S>>>,
    pub host: String,
    /// Origin-form request path (private: holds the customer name).
    pub path: String,
}

/// `GET url` through a tlsn session on `socket` (MPC: the prover dials the
/// server; proxy: the notary does). The response body is never read through
/// hyper, so the server's close ends the session, not the client's: in proxy
/// mode at tlsn rev 24b10ba a client close while connected is a hard error.
pub(crate) async fn fetch<S: AsyncWrite + AsyncRead + Send + Sync + Unpin + 'static>(
    socket: S,
    url: &str,
    opts: &ProverOptions,
) -> Result<Fetched<S>> {
    let uri: Uri = url.parse().context("parse url")?;
    let authority = uri.authority().context("url has no host")?;
    let host = authority.host().to_string();
    let port = authority.port_u16().unwrap_or(443);
    let path_and_query = uri.path_and_query().map(|pq| pq.as_str().to_string()).unwrap_or_else(|| "/".into());

    let session = Session::new(socket.compat());
    let (driver, mut handle) = session.split();
    let driver = tokio::spawn(driver);

    let tls_config = TlsClientConfig::builder()
        .server_name(ServerName::Dns(host.as_str().try_into()?))
        .root_store(RootCertStore::mozilla())
        .build()?;
    let prover = handle.new_prover(ProverConfig::builder().build()?)?;
    let (tls_connection, prover_task) = match opts.mode {
        TlsMode::Mpc => {
            let prover = prover
                .commit(MpcTlsConfig::builder().max_sent_data(opts.max_sent).max_recv_data(opts.max_recv).build()?)
                .await?;
            let client_socket = tokio::net::TcpStream::connect((host.as_str(), port)).await?;
            client_socket.set_nodelay(true)?;
            let (conn, prover) = prover.connect(tls_config, client_socket.compat())?;
            (conn, tokio::spawn(prover.into_future()))
        }
        TlsMode::Proxy => {
            // The notary dials the server; TLS runs over a mux stream to it.
            let prover = prover
                .commit(ProxyTlsConfig::builder().server_name(DnsName::try_from(host.as_str())?).build()?)
                .await?;
            let (conn, prover) = prover.connect(tls_config)?;
            (conn, tokio::spawn(prover.into_future()))
        }
    };
    let tls_connection = TokioIo::new(tls_connection.compat());

    let (mut request_sender, connection) = hyper::client::conn::http1::handshake(tls_connection).await?;
    tokio::spawn(connection);

    let request = Request::builder()
        .uri(path_and_query.as_str())
        .header("Host", &host)
        .header("Accept", "*/*")
        .header("Accept-Encoding", "identity")
        .header("Connection", "close")
        .header("User-Agent", USER_AGENT)
        .method("GET")
        .body(Empty::<Bytes>::new())?;

    tracing::info!("GET https://{host}/<private path> via {}-TLS", opts.mode);
    let response = request_sender.send_request(request).await?;
    let status = response.status();
    if status != StatusCode::OK {
        bail!("server returned {status}, expected 200");
    }

    let prover = prover_task.await??;
    Ok(Fetched { prover, handle, driver, host, path: path_and_query })
}

async fn prover<S: AsyncWrite + AsyncRead + Send + Sync + Unpin + 'static>(
    socket: S,
    url: &str,
    opts: &ProverOptions,
    on_stage: &(dyn Fn(TlsStage, u64) + Send + Sync),
    t0: Instant,
) -> Result<TlsSession> {
    let session_t = Instant::now();
    let Fetched { mut prover, handle, driver: driver_task, host, path: path_and_query } =
        fetch(socket, url, opts).await?;
    on_stage(TlsStage::Session, t0.elapsed().as_millis() as u64);

    let sent = prover.transcript().sent().to_vec();
    let received = prover.transcript().received().to_vec();
    let sent_len = sent.len();
    let recv_len = received.len();

    let p = plan(&sent, &received, Some(&path_and_query))?;
    let body = received[p.body.clone()].to_vec();

    let mut builder = TranscriptCommitConfig::builder(prover.transcript());
    builder.default_kind(SHA256_KIND);
    for r in &p.sent_commit {
        builder.commit_sent(r)?;
    }
    for r in &p.recv_commit {
        builder.commit_recv(r)?;
    }
    let transcript_commit = builder.build()?;

    let mut rc_builder = RequestConfig::builder();
    rc_builder
        .signature_alg(SignatureAlgId::SECP256K1ETH)
        .hash_alg(HashAlgId::SHA256)
        .transcript_commit(transcript_commit);
    let request_config = rc_builder.build()?;

    let mut pc_builder = ProveConfig::builder(prover.transcript());
    pc_builder.server_identity();
    if let Some(config) = request_config.transcript_commit() {
        pc_builder.transcript_commit(config.clone());
    }
    let disclosure_config = pc_builder.build()?;

    let ProverOutput { transcript_commitments, transcript_secrets, .. } = prover.prove(&disclosure_config).await?;

    let is_body = |dir: Direction, idx: Vec<Range<usize>>| dir == Direction::Received && idx == vec![p.body.clone()];
    let body_commitment: [u8; 32] = transcript_commitments
        .iter()
        .find_map(|c| match c {
            TranscriptCommitment::Hash(h) if is_body(h.direction, h.idx.iter().collect()) => {
                Some(h.hash.value.as_bytes().to_vec())
            }
            _ => None,
        })
        .context("body commitment missing")?
        .try_into()
        .map_err(|_| anyhow::anyhow!("body commitment is not 32 bytes"))?;
    let blinder: [u8; 16] = transcript_secrets
        .iter()
        .find_map(|s| match s {
            TranscriptSecret::Hash(h) if is_body(h.direction, h.idx.iter().collect()) => {
                Some(h.blinder.as_bytes().to_vec())
            }
            _ => None,
        })
        .context("body blinder missing")?
        .try_into()
        .map_err(|_| anyhow::anyhow!("blinder is not 16 bytes"))?;
    let blinders = p
        .sent_commit
        .iter()
        .map(|r| {
            transcript_secrets
                .iter()
                .find_map(|s| match s {
                    TranscriptSecret::Hash(h)
                        if h.direction == Direction::Sent && h.idx.iter().collect::<Vec<_>>() == vec![r.clone()] =>
                    {
                        <[u8; 16]>::try_from(h.blinder.as_bytes()).ok()
                    }
                    _ => None,
                })
                .with_context(|| format!("no blinder for sent {r:?}"))
        })
        .collect::<Result<Vec<_>>>()?;
    let request_secret = RequestSecret { request: sent.clone(), blinders };

    // Self-check of the exact commitment formula the guest recomputes.
    let mut hasher = Sha256::new();
    hasher.update(&body);
    hasher.update(blinder);
    let digest: [u8; 32] = hasher.finalize().into();
    if digest != body_commitment {
        bail!("SHA256(body || blinder) does not match the body commitment");
    }

    let prover_transcript = prover.transcript().clone();
    let tls_transcript = prover.tls_transcript().clone();
    let tls_version = format!("{:?}", tls_transcript.version());
    prover.close().await?;

    let mut att_req_builder = AttestationRequest::builder(&request_config);
    att_req_builder
        .server_name(ServerName::Dns(host.as_str().try_into()?))
        .handshake_data(HandshakeData {
            certs: tls_transcript.server_cert_chain().context("server cert chain present")?.to_vec(),
            sig: tls_transcript.server_signature().context("server signature present")?.clone(),
            binding: tls_transcript.certificate_binding().clone(),
        })
        .transcript(prover_transcript)
        .transcript_commitments(transcript_secrets, transcript_commitments);
    let (request, secrets) = att_req_builder.build(&CryptoProvider::default())?;

    handle.close();
    let mut socket = driver_task.await??;
    socket.write_all(&bincode::serialize(&request)?).await?;
    socket.close().await?;
    let mut attestation_bytes = Vec::new();
    socket.read_to_end(&mut attestation_bytes).await?;
    let attestation: Attestation = bincode::deserialize(&attestation_bytes)?;

    let provider = CryptoProvider::default();
    if request.validate(&attestation, &provider).is_err() {
        bail!("attestation does not match the request");
    }
    let session_ms = session_t.elapsed().as_millis() as u64;
    on_stage(TlsStage::Notarize, t0.elapsed().as_millis() as u64);

    // Presentation: server identity + the revealed ranges only.
    let present_t = Instant::now();
    let mut tp = secrets.transcript_proof_builder();
    for r in &p.sent_reveal {
        tp.reveal_sent(r)?;
    }
    for r in &p.recv_reveal {
        tp.reveal_recv(r)?;
    }
    let transcript_proof = tp.build()?;
    let mut pb = attestation.presentation_builder(&provider);
    pb.identity_proof(secrets.identity_proof()).transcript_proof(transcript_proof);
    let presentation: Presentation = pb.build()?;
    let presentation_bytes = bincode::serialize(&presentation)?;
    let present_ms = present_t.elapsed().as_millis() as u64;
    on_stage(TlsStage::Present, t0.elapsed().as_millis() as u64);

    Ok(TlsSession {
        mode: opts.mode,
        host,
        prover: "server",
        body,
        blinder,
        attestation: attestation_bytes,
        secrets: bincode::serialize(&secrets)?,
        presentation: presentation_bytes,
        body_commitment,
        body_range: p.body,
        request: request_secret,
        sent_len,
        recv_len,
        tls_version,
        timings: TlsTimings { session_ms, present_ms, total_ms: 0 },
    })
}
