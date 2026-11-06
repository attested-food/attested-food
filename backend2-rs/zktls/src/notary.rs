//! The notary (tlsn verifier) half of a session, over any byte stream, in MPC
//! or proxy mode (the prover picks, the notary accepts what
//! [`NotaryConfig::modes`] allows). In proxy mode the notary itself dials the
//! one allowlisted server and relays the TLS bytes; it still only sees
//! ciphertext.
//!
//! [`notarize`] (server-side prover, in-process duplex): the prover sends a
//! bincode `attestation::request::Request`, half-closes; the notary answers
//! with a bincode `Attestation` and closes. Ported from `equinox_fetch_pdf`.
//! The backend's browser protocol (`notarize_browser`) is not copied.

use anyhow::{bail, Context, Result};
use futures::io::{AsyncReadExt as _, AsyncWriteExt as _};
use tlsn::{
    attestation::{
        request::Request as AttestationRequest, signing::Secp256k1EthSigner, Attestation, AttestationConfig,
        CryptoProvider, Extension,
    },
    config::verifier::VerifierConfig,
    connection::{CertBinding, ConnectionInfo, ServerName, TranscriptLength},
    transcript::{ContentType, Record, TlsTranscript, TranscriptCommitment},
    verifier::{VerifierCommitStart, VerifierOutput},
    webpki::RootCertStore,
    Session,
};
use tokio::io::{AsyncRead, AsyncWrite};
use tokio_util::compat::{Compat, TokioAsyncReadCompatExt};

use crate::{is_allowed_host, proxy::is_allowed_target, NotaryKey, TlsMode, SERVER_NAME_EXT_ID, SESSION_EXT_ID};

/// What the notary accepts.
#[derive(Clone)]
pub struct NotaryConfig {
    pub key: NotaryKey,
    /// Commit protocols the notary accepts.
    pub modes: Vec<TlsMode>,
}

impl NotaryConfig {
    /// `EQUINOX_NOTARY_KEY` (see [`NotaryKey::from_env`]) and
    /// `EQUINOX_NOTARY_MODES` (comma-separated, default `mpc,proxy`).
    pub fn from_env() -> Result<Self> {
        let modes = match std::env::var("EQUINOX_NOTARY_MODES") {
            Ok(m) => m.split(',').map(str::parse).collect::<Result<Vec<TlsMode>>>()?,
            Err(_) => vec![TlsMode::Mpc, TlsMode::Proxy],
        };
        Ok(NotaryConfig { key: NotaryKey::from_env()?, modes })
    }

    pub fn accepts(&self, mode: TlsMode) -> bool {
        self.modes.contains(&mode)
    }
}

/// A finished, verified tlsn session, before anything is signed.
struct Verified<S> {
    mode: TlsMode,
    output: VerifierOutput,
    tls: TlsTranscript,
    /// The byte stream, back from the session driver.
    socket: Compat<S>,
}

/// Run the verifier half until the prover's statements are verified, then
/// close the tlsn session and hand back the stream.
async fn verify_session<S>(socket: S, config: &NotaryConfig) -> Result<Verified<S>>
where
    S: AsyncWrite + AsyncRead + Send + Sync + Unpin + 'static,
{
    let session = Session::new(socket.compat());
    let (driver, mut handle) = session.split();
    let driver_task = tokio::spawn(driver);

    let verifier_config = VerifierConfig::builder().root_store(RootCertStore::mozilla()).build()?;

    let (mode, verifier) = match handle.new_verifier(verifier_config)?.commit().await? {
        VerifierCommitStart::Mpc(verifier) if config.accepts(TlsMode::Mpc) => {
            (TlsMode::Mpc, verifier.accept().await?.run().await?)
        }
        VerifierCommitStart::Proxy(verifier) if config.accepts(TlsMode::Proxy) => {
            // The notary dials the server: only ever the allowlisted bucket.
            let name = verifier.config().server_name().as_str().to_string();
            let target = format!("{name}:443");
            if !is_allowed_host(&name) || !is_allowed_target(&target) {
                verifier.reject(Some("server is not allowlisted by this notary")).await?;
                bail!("proxy-mode prover asked for a server that is not allowlisted");
            }
            let tcp = tokio::net::TcpStream::connect(&target).await.context("notary: connect to the server")?;
            tcp.set_nodelay(true)?;
            (TlsMode::Proxy, verifier.accept().await?.run(tcp.compat()).await?)
        }
        VerifierCommitStart::Mpc(verifier) => {
            verifier.reject(Some("MPC-TLS not accepted by this notary")).await?;
            bail!("prover asked for MPC-TLS");
        }
        VerifierCommitStart::Proxy(verifier) => {
            verifier.reject(Some("proxy mode not accepted by this notary")).await?;
            bail!("prover asked for proxy mode");
        }
    };

    let verifier = verifier.verify().await?;
    if !verifier.request().server_identity() {
        verifier.reject(Some("the server identity must be proven")).await?.close().await?;
        bail!("prover did not prove the server identity");
    }
    let (output, verifier) = verifier.accept().await?;
    let tls = verifier.tls_transcript().clone();
    verifier.close().await?;

    handle.close();
    let socket = driver_task.await??;
    Ok(Verified { mode, output, tls, socket })
}

/// Sign an attestation for a verified session: connection info and server
/// ephemeral key from the notary's own view of the TLS transcript, the
/// commitments the prover proved, and the two `equinox.*` extensions.
fn sign(
    config: &NotaryConfig,
    request: AttestationRequest,
    tls: &TlsTranscript,
    server_name: Option<&ServerName>,
    commitments: Vec<TranscriptCommitment>,
    session: &str,
) -> Result<Attestation> {
    let Some(ServerName::Dns(name)) = server_name else {
        bail!("prover did not prove the server identity");
    };
    if !is_allowed_host(name.as_str()) {
        bail!("server {} is not allowlisted", name.as_str());
    }

    let signer = Box::new(Secp256k1EthSigner::new(&config.key.0)?);
    let mut provider = CryptoProvider::default();
    provider.signer.set_signer(signer);

    let mut att_config_builder = AttestationConfig::builder();
    att_config_builder.supported_signature_algs(Vec::from_iter(provider.signer.supported_algs()));
    let att_config = att_config_builder.build()?;

    let CertBinding::V1_2(binding) = tls.certificate_binding() else {
        bail!("unsupported cert binding version");
    };
    let mut builder = Attestation::builder(&att_config).accept_request(request)?;
    builder
        .connection_info(ConnectionInfo {
            time: tls.time(),
            version: tls.version(),
            transcript_length: TranscriptLength {
                sent: app_data_len(tls.sent()) as u32,
                received: app_data_len(tls.recv()) as u32,
            },
        })
        .server_ephemeral_key(binding.server_ephemeral_key.clone())
        .transcript_commitments(commitments);
    builder.extension(Extension { id: SERVER_NAME_EXT_ID.to_vec(), value: name.as_str().as_bytes().to_vec() });
    builder.extension(Extension { id: SESSION_EXT_ID.to_vec(), value: session.as_bytes().to_vec() });
    Ok(builder.build(&provider)?)
}

/// Notarize a server-side prover's session on `socket`. Returns the
/// attestation it signed.
pub async fn notarize<S: AsyncWrite + AsyncRead + Send + Sync + Unpin + 'static>(
    socket: S,
    config: &NotaryConfig,
) -> Result<Attestation> {
    let Verified { mode, output, tls, mut socket } = verify_session(socket, config).await?;

    let mut request_bytes = Vec::new();
    socket.read_to_end(&mut request_bytes).await?;
    let request: AttestationRequest = bincode::deserialize(&request_bytes)?;

    let session = format!("{mode}/server");
    let attestation =
        sign(config, request, &tls, output.server_name.as_ref(), output.transcript_commitments, &session)?;

    socket.write_all(&bincode::serialize(&attestation)?).await?;
    socket.close().await?;
    Ok(attestation)
}

fn app_data_len(records: &[Record]) -> usize {
    records
        .iter()
        .filter_map(
            |record| if let ContentType::ApplicationData = record.typ { Some(record.ciphertext.len()) } else { None },
        )
        .sum()
}
