//! The selective-disclosure policy, in one place for every side of a session:
//! which byte ranges a prover commits and reveals ([`plan`]), and what a
//! verifier requires of the revealed transcript ([`check_revealed`]): the
//! notary of a browser session checks it before signing, and
//! `presentation::verify` checks it again on the presentation.
//!
//! Sent: `GET ` | path | ` HTTP/1.1\r\n...`. Every part is committed
//! (SHA-256); the path is never revealed, the two other parts are.
//! Received: status line, Content-Type, Content-Length and the header
//! terminator are committed and revealed, the body is one private commitment.

use std::ops::Range;

use anyhow::{bail, ensure, Context, Result};

use crate::is_allowed_host;

pub struct ResponseLayout {
    pub status_line: Range<usize>,
    pub content_type: Range<usize>,
    pub content_length: Range<usize>,
    pub terminator: Range<usize>,
    pub body: Range<usize>,
}

/// Byte ranges in an HTTP/1.1 response with a Content-Length body. Header
/// ranges start at the CRLF before the header name and end after its own CRLF,
/// so a verifier sees whole lines; `terminator` is the CRLFCRLF that ends the
/// headers. The body is binary, so it is located by length.
pub fn response_layout(received: &[u8]) -> Result<ResponseLayout> {
    let sep = received.windows(4).position(|w| w == b"\r\n\r\n").context("no header terminator in response")?;
    let header_end = sep + 4;
    let mut lines = Vec::new();
    let mut start = 0;
    while start < sep + 2 {
        let end =
            start + received[start..].windows(2).position(|w| w == b"\r\n").context("unterminated header line")? + 2;
        lines.push(start..end);
        start = end;
    }
    let find = |name: &str| -> Result<Range<usize>> {
        let mut hits = lines.iter().skip(1).filter(|r| {
            let l = &received[(*r).clone()];
            l.len() > name.len() && l[..name.len()].eq_ignore_ascii_case(name.as_bytes())
        });
        let hit = hits.next().with_context(|| format!("no {name} header"))?.clone();
        if hits.next().is_some() {
            bail!("duplicate {name} header");
        }
        Ok(hit.start - 2..hit.end)
    };
    let content_type = find("content-type:")?;
    let content_length = find("content-length:")?;
    let cl_line = String::from_utf8_lossy(&received[content_length.clone()]).to_string();
    let n: usize = cl_line["\r\ncontent-length:".len()..].trim().parse()?;
    if header_end + n != received.len() {
        bail!("body length does not match Content-Length");
    }
    Ok(ResponseLayout {
        status_line: lines[0].clone(),
        content_type,
        content_length,
        terminator: sep..header_end,
        body: header_end..header_end + n,
    })
}

/// What a prover commits and reveals for one session.
pub struct Plan {
    /// `GET `, path, rest of the request: all committed, in this order.
    pub sent_commit: Vec<Range<usize>>,
    /// Revealed sent ranges (everything but the path).
    pub sent_reveal: Vec<Range<usize>>,
    /// Status line, Content-Type, Content-Length, terminator, body: committed.
    pub recv_commit: Vec<Range<usize>>,
    /// Revealed received ranges (everything committed but the body).
    pub recv_reveal: Vec<Range<usize>>,
    pub path: Range<usize>,
    pub body: Range<usize>,
}

/// The plan for a plaintext transcript. `expected_path` (when known) must be
/// exactly the request path.
pub fn plan(sent: &[u8], received: &[u8], expected_path: Option<&str>) -> Result<Plan> {
    ensure!(sent.starts_with(b"GET "), "unexpected request line");
    let path_start = 4;
    let path_end =
        path_start + sent[path_start..].iter().position(|&b| b == b' ').context("no space after request path")?;
    if let Some(p) = expected_path {
        ensure!(&sent[path_start..path_end] == p.as_bytes(), "request path not where expected in the sent transcript");
    }
    let layout = response_layout(received)?;
    let head = vec![layout.status_line, layout.content_type, layout.content_length, layout.terminator];
    let mut recv_commit = head.clone();
    recv_commit.push(layout.body.clone());
    Ok(Plan {
        sent_commit: vec![0..path_start, path_start..path_end, path_end..sent.len()],
        sent_reveal: vec![0..path_start, path_end..sent.len()],
        recv_commit,
        recv_reveal: head,
        path: path_start..path_end,
        body: layout.body,
    })
}

/// What the revealed transcript establishes.
#[derive(Clone, Debug)]
pub struct Revealed {
    pub content_length: usize,
    /// Body range in the received transcript.
    pub body: Range<usize>,
}

/// The verifier's policy over a partially revealed transcript (`sent` and
/// `recv` hold zeros outside the authenticated ranges): status 200,
/// Content-Type application/pdf, the Content-Length line, the header
/// terminator right before the body, no body byte revealed; request `GET`,
/// path hidden, rest of the request revealed with `Host` = an allowlisted bucket.
pub fn check_revealed(
    sent: &[u8],
    recv: &[u8],
    sent_auth: &[Range<usize>],
    recv_auth: &[Range<usize>],
) -> Result<Revealed> {
    let (sent_len, recv_len) = (sent.len(), recv.len());
    let authed = |set: &[Range<usize>], r: Range<usize>| set.iter().any(|a| a.start <= r.start && r.end <= a.end);

    let status = b"HTTP/1.1 200 OK\r\n";
    ensure!(authed(recv_auth, 0..status.len()) && recv.starts_with(status), "status is not 200");
    let line = |name: &[u8]| -> Result<Vec<u8>> {
        let mut found = None;
        for i in 0..recv.len().saturating_sub(name.len()) {
            if recv[i..i + name.len()].eq_ignore_ascii_case(name) {
                let end = i + 2 + recv[i + 2..].windows(2).position(|w| w == b"\r\n").context("no CRLF")? + 2;
                if authed(recv_auth, i..end) {
                    ensure!(found.is_none(), "duplicate revealed header");
                    found = Some(recv[i + name.len()..end - 2].to_vec());
                }
            }
        }
        found.context("header not revealed")
    };
    let ctype = line(b"\r\ncontent-type:")?;
    ensure!(String::from_utf8_lossy(&ctype).trim() == "application/pdf", "Content-Type is not application/pdf");
    let clen: usize = String::from_utf8_lossy(&line(b"\r\ncontent-length:")?).trim().parse()?;
    ensure!(clen > 0 && clen + 4 <= recv_len, "bad Content-Length");
    let body = recv_len - clen..recv_len;
    ensure!(
        authed(recv_auth, body.start - 4..body.start) && &recv[body.start - 4..body.start] == b"\r\n\r\n",
        "header terminator not revealed right before the body"
    );
    ensure!(!recv_auth.iter().any(|a| a.end > body.start), "part of the body is revealed");

    ensure!(authed(sent_auth, 0..4) && sent.starts_with(b"GET "), "request is not a GET");
    let rest = sent_auth.iter().find(|a| a.start > 4).context("request tail not revealed")?;
    ensure!(rest.end == sent_len, "request tail not fully revealed");
    let path = 4..rest.start;
    ensure!(!sent_auth.iter().any(|a| a.start < path.end && path.start < a.end), "path revealed");
    let tail = String::from_utf8_lossy(&sent[rest.clone()]).to_lowercase();
    ensure!(tail.starts_with(" http/1.1\r\n"), "bad request line");
    let host = tail.split("\r\n").filter_map(|l| l.strip_prefix("host:")).map(str::trim).collect::<Vec<_>>();
    ensure!(matches!(host[..], [h] if is_allowed_host(h)), "Host header is not one allowlisted bucket");
    Ok(Revealed { content_length: clen, body })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn session() -> (Vec<u8>, Vec<u8>) {
        let sent = format!(
            "GET /equinox/titan/newReports/NAME/x.pdf HTTP/1.1\r\nhost: {}\r\nconnection: close\r\n\r\n",
            crate::SERVER_NAMES[0]
        );
        let mut recv = b"HTTP/1.1 200 OK\r\nx-amz-id: secret\r\nContent-Type: application/pdf\r\nContent-Length: 9\r\nServer: AmazonS3\r\n\r\n".to_vec();
        recv.extend_from_slice(b"%PDF-1.4!");
        (sent.into_bytes(), recv)
    }

    /// Zero everything outside `auth`, as a verifier sees it.
    fn redact(b: &[u8], auth: &[Range<usize>]) -> Vec<u8> {
        (0..b.len()).map(|i| if auth.iter().any(|a| a.contains(&i)) { b[i] } else { 0 }).collect()
    }

    #[test]
    fn plan_then_check() {
        let (sent, recv) = session();
        let p = plan(&sent, &recv, Some("/equinox/titan/newReports/NAME/x.pdf")).unwrap();
        assert_eq!(&recv[p.body.clone()], b"%PDF-1.4!");
        let (s, r) = (redact(&sent, &p.sent_reveal), redact(&recv, &p.recv_reveal));
        assert!(!s.windows(4).any(|w| w == b"NAME"));
        assert!(!r.windows(6).any(|w| w == b"secret"));
        let rev = check_revealed(&s, &r, &p.sent_reveal, &p.recv_reveal).unwrap();
        assert_eq!((rev.content_length, rev.body), (9, p.body.clone()));

        // Revealing the path or any body byte is refused.
        let mut leak = p.sent_reveal.clone();
        leak.push(p.path.clone());
        assert!(check_revealed(&sent, &r, &leak, &p.recv_reveal).is_err());
        let mut leak = p.recv_reveal.clone();
        leak.push(p.body.start..p.body.start + 1);
        assert!(check_revealed(&s, &recv, &p.sent_reveal, &leak).is_err());
        // A hidden Content-Type is refused.
        let hidden: Vec<_> = p.recv_reveal.iter().filter(|r| **r != p.recv_reveal[1]).cloned().collect();
        assert!(check_revealed(&s, &redact(&recv, &hidden), &p.sent_reveal, &hidden).is_err());
        assert!(plan(&sent, &recv, Some("/other.pdf")).is_err());
    }
}
