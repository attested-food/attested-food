//! Turns a TLSNotary presentation into the attestation pieces the contract and
//! the in-guest verifier check: the BCS header the notary signed, its 65-byte
//! recoverable signature, every Merkle leaf of the attestation body (sorted by
//! field id), and the BCS preimages of the two leaves that get opened: the
//! notary-signed `equinox.server_name` extension and the SHA-256 body
//! commitment. Ported from the PoC `export_onchain`. Also the request leaves
//! ([`OnchainRequest`]): `ConnectionInfo` and the three sent commitments.
//!
//! Leaves are recomputed as `SHA256(domain || bcs(field))` with
//! `domain = blake3(type name)[..16]` as in tlsn-attestation, and the Merkle
//! root is rebuilt and checked against the signed header before returning.

use std::ops::Range;

use anyhow::{ensure, Context, Result};
use serde::{de::DeserializeOwned, Serialize};
use sha2::{Digest, Sha256};
use tlsn::{
    attestation::{
        connection::ServerCertCommitment,
        presentation::{Presentation, PresentationOutput},
        signing::VerifyingKey,
        CryptoProvider, Extension,
    },
    connection::{ConnectionInfo, ServerEphemKey},
    transcript::{Direction, TranscriptCommitment},
};

use crate::{OnchainRequest, OnchainTlsn, SERVER_NAME_EXT_ID};

pub fn domain(name: &str) -> [u8; 16] {
    blake3::hash(name.as_bytes()).as_bytes()[..16].try_into().unwrap()
}

fn leaf<T: Serialize + DeserializeOwned>(name: &str, v: &serde_json::Value) -> Result<(Vec<u8>, [u8; 32])> {
    let data: T = serde_json::from_value(v.clone())?;
    let pre = bcs::to_bytes(&data)?;
    let mut h = Sha256::new();
    h.update(domain(name));
    h.update(&pre);
    Ok((pre, h.finalize().into()))
}

/// Export plus the notary key, for callers that want the PoC `onchain.json`.
pub struct Export {
    pub tlsn: OnchainTlsn,
    pub request: OnchainRequest,
    /// Compressed SEC1 notary key.
    pub notary_pubkey: Vec<u8>,
}

pub fn export(presentation_bytes: &[u8]) -> Result<Export> {
    let p: Presentation = bincode::deserialize(presentation_bytes).context("decode presentation")?;
    let PresentationOutput { attestation, .. } =
        p.verify(&CryptoProvider::default()).map_err(|e| anyhow::anyhow!("{e}"))?;
    let b = serde_json::to_value(&attestation.body)?;

    // (field id, leaf hash, preimage, kind)
    let mut fields: Vec<(u64, [u8; 32], Vec<u8>, &str)> = Vec::new();
    let mut push = |f: &serde_json::Value, r: (Vec<u8>, [u8; 32]), kind: &'static str| {
        fields.push((f["id"].as_u64().unwrap_or(u64::MAX), r.1, r.0, kind));
    };
    push(&b["verifying_key"], leaf::<VerifyingKey>("VerifyingKey", &b["verifying_key"]["data"])?, "vk");
    push(
        &b["connection_info"],
        leaf::<ConnectionInfo>("tlsn_core::connection::ConnectionInfo", &b["connection_info"]["data"])?,
        "conn",
    );
    push(
        &b["server_ephemeral_key"],
        leaf::<ServerEphemKey>("tlsn_core::connection::ServerEphemKey", &b["server_ephemeral_key"]["data"])?,
        "ephem",
    );
    push(
        &b["cert_commitment"],
        leaf::<ServerCertCommitment>("ServerCertCommitment", &b["cert_commitment"]["data"])?,
        "cert",
    );
    for e in b["extensions"].as_array().context("extensions")? {
        push(e, leaf::<Extension>("Extension", &e["data"])?, "ext");
    }
    for c in b["transcript_commitments"].as_array().context("commitments")? {
        push(c, leaf::<TranscriptCommitment>("tlsn_core::transcript::TranscriptCommitment", &c["data"])?, "tc");
    }
    fields.sort_by_key(|f| f.0);
    ensure!(fields.iter().enumerate().all(|(i, f)| f.0 == i as u64), "field ids not dense");

    let leaves: Vec<[u8; 32]> = fields.iter().map(|f| f.1).collect();
    let header = bcs::to_bytes(&attestation.header)?;
    let signed_root: Vec<u8> = attestation.header.root.value.into();
    ensure!(
        equinox_core::tlsn::merkle_root(&leaves) == signed_root.as_slice(),
        "recomputed Merkle root != signed root"
    );

    let ext = fields
        .iter()
        .find(|f| {
            f.3 == "ext" && bcs::from_bytes::<Extension>(&f.2).map(|e| e.id == SERVER_NAME_EXT_ID).unwrap_or(false)
        })
        .context("server_name extension")?;
    let conn: ConnectionInfo = serde_json::from_value(b["connection_info"]["data"].clone())?;
    let recv_len = conn.transcript_length.received as usize;
    // The body commitment is the received-direction one that ends the transcript.
    let body = fields
        .iter()
        .find(|f| {
            f.3 == "tc"
                && match bcs::from_bytes::<TranscriptCommitment>(&f.2) {
                    Ok(TranscriptCommitment::Hash(h)) => {
                        let idx: Vec<Range<usize>> = h.idx.iter().collect();
                        h.direction == Direction::Received
                            && idx.len() == 1
                            && idx[0].end == recv_len
                            && idx[0].start > 0
                    }
                    _ => false,
                }
        })
        .context("body commitment")?;

    let conn_field = fields.iter().find(|f| f.3 == "conn").context("connection info")?;
    let mut sent: Vec<(u64, usize, Vec<u8>)> = fields
        .iter()
        .filter(|f| f.3 == "tc")
        .filter_map(|f| match bcs::from_bytes::<TranscriptCommitment>(&f.2) {
            Ok(TranscriptCommitment::Hash(h)) if h.direction == Direction::Sent => {
                Some((f.0, h.idx.iter().next()?.start, f.2.clone()))
            }
            _ => None,
        })
        .collect();
    sent.sort_by_key(|s| s.1);
    ensure!(sent.len() == 3, "expected three sent commitments (GET, path, rest)");

    let sig = attestation.signature.data.clone();
    ensure!(sig.len() == 65, "expected a 65-byte secp256k1eth signature");
    Ok(Export {
        tlsn: OnchainTlsn {
            header,
            signature: sig,
            leaves,
            ext_index: ext.0 as u32,
            ext_preimage: ext.2.clone(),
            body_index: body.0 as u32,
            body_preimage: body.2.clone(),
        },
        request: OnchainRequest {
            conn_index: conn_field.0 as u32,
            conn_preimage: conn_field.2.clone(),
            sent_index: sent.iter().map(|s| s.0 as u32).collect(),
            sent_preimage: sent.into_iter().map(|s| s.2).collect(),
        },
        notary_pubkey: attestation.body.verifying_key().data.clone(),
    })
}

impl Export {
    /// The PoC `onchain.json` shape (0x-hex strings), which the Foundry test
    /// and `contracts/script/deploy-and-verify.sh` read.
    pub fn to_json(&self) -> serde_json::Value {
        let hx = |b: &[u8]| format!("0x{}", hex::encode(b));
        let t = &self.tlsn;
        serde_json::json!({
            "header": hx(&t.header),
            "headerRootOffset": t.header.len() - 32,
            "signature": hx(&t.signature),
            "leaves": t.leaves.iter().map(|l| hx(l)).collect::<Vec<_>>(),
            "extIndex": t.ext_index,
            "extPreimage": hx(&t.ext_preimage),
            "bodyIndex": t.body_index,
            "bodyPreimage": hx(&t.body_preimage),
            "domainExtension": hx(&domain("Extension")),
            "domainTranscriptCommitment": hx(&domain("tlsn_core::transcript::TranscriptCommitment")),
            "notaryPubKey": hx(&self.notary_pubkey),
            "connIndex": self.request.conn_index,
            "connPreimage": hx(&self.request.conn_preimage),
            "sentIndices": self.request.sent_index,
            "sentPreimages": self.request.sent_preimage.iter().map(|p| hx(p)).collect::<Vec<_>>(),
        })
    }
}
