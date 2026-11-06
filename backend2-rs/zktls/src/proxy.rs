//! URL policy and the TCP side of the WebSocket -> TCP proxy that browser
//! provers (tlsn-wasm) dial, because a browser cannot open raw TCP. The proxy
//! only ever sees TLS ciphertext. `WS /proxy?host=` adapts the WebSocket to a
//! byte stream and calls [`bridge_tcp`] (`crate::ws::serve_proxy`).

use anyhow::{bail, Result};
use tokio::io::{AsyncRead, AsyncWrite};

/// `host:port` targets the proxy may dial. Nothing else, ever. The notary only
/// ever signs for the buckets; titan is here so a browser can resolve the QR
/// link over its own TLS session without the server seeing the redirect.
pub const ALLOWED_PROXY_TARGETS: &[&str] =
    &["equinox-labs-latest.s3.amazonaws.com:443", "eurekhalabs.s3.amazonaws.com:443", "titan.equinoxlab.com:443"];

/// The QR payload prefix of an Equinox "Download Report" link.
pub const TITAN_PREFIX: &str = "https://titan.equinoxlab.com/report/with_letter_head/download/";

/// The shape titan's 302 must point at.
pub const S3_PREFIX: &str = "https://equinox-labs-latest.s3.amazonaws.com/equinox/titan/newReports/";

/// Eurekha Labs report objects (`mock-pdfs/scripts/upload.sh`).
pub const EUREKHA_S3_PREFIX: &str = "https://eurekhalabs.s3.amazonaws.com/reports/";

pub fn is_allowed_target(host_port: &str) -> bool {
    ALLOWED_PROXY_TARGETS.contains(&host_port)
}

/// A titan download URL: fixed prefix, then a token of URL-safe characters.
pub fn check_titan_url(url: &str) -> Result<()> {
    let Some(token) = url.strip_prefix(TITAN_PREFIX) else { bail!("not an Equinox titan download URL") };
    if token.is_empty() || !token.bytes().all(|c| c.is_ascii_alphanumeric() || b"-_.~%=+/".contains(&c)) {
        bail!("bad titan token");
    }
    Ok(())
}

/// An S3 report object URL: the one a titan link redirects to
/// (`.../newReports/<name>/.../*.pdf`) or a Eurekha one (`.../reports/.../*.pdf`).
pub fn check_s3_url(url: &str) -> Result<()> {
    let Some(rest) = url.strip_prefix(S3_PREFIX).or_else(|| url.strip_prefix(EUREKHA_S3_PREFIX)) else {
        bail!("not an allowlisted S3 report URL")
    };
    if !rest.ends_with(".pdf") || rest.contains("..") || rest.contains('?') || rest.contains('#') {
        bail!("unexpected S3 report path shape");
    }
    Ok(())
}

/// Pipe `client` to a TCP connection to `host_port` (allowlisted) until either
/// side closes. Returns (bytes client -> server, bytes server -> client).
pub async fn bridge_tcp<S: AsyncRead + AsyncWrite + Unpin>(mut client: S, host_port: &str) -> Result<(u64, u64)> {
    if !is_allowed_target(host_port) {
        bail!("proxy target {host_port} is not allowlisted");
    }
    let mut tcp = tokio::net::TcpStream::connect(host_port).await?;
    tcp.set_nodelay(true)?;
    Ok(tokio::io::copy_bidirectional(&mut client, &mut tcp).await?)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn url_policy() {
        assert!(check_titan_url(&format!("{TITAN_PREFIX}abc123")).is_ok());
        assert!(check_titan_url("https://titan.equinoxlab.com.evil/report/with_letter_head/download/x").is_err());
        assert!(check_titan_url(TITAN_PREFIX).is_err());
        assert!(check_s3_url(&format!("{S3_PREFIX}name/2026/November/x.pdf")).is_ok());
        assert!(check_s3_url(&format!("{S3_PREFIX}name/../x.pdf")).is_err());
        assert!(check_s3_url("https://other-bucket.s3.amazonaws.com/equinox/titan/newReports/x.pdf").is_err());
        assert!(check_s3_url(&format!("{EUREKHA_S3_PREFIX}2026/x-0123.pdf")).is_ok());
        assert!(check_s3_url("https://eurekhalabs.s3.amazonaws.com/private/x.pdf").is_err());
        assert!(is_allowed_target("equinox-labs-latest.s3.amazonaws.com:443"));
        assert!(is_allowed_target("titan.equinoxlab.com:443"));
        assert!(!is_allowed_target("titan.equinoxlab.com:80"));
        assert!(!is_allowed_target("equinox-labs-latest.s3.amazonaws.com:80"));
        assert!(!is_allowed_target("127.0.0.1:22"));
    }
}
