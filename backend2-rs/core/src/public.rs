//! The public values every backend commits, in one byte layout. It is the
//! bincode layout SP1's `io::commit` produced field by field in the PoC, so
//! the SP1 public values stay byte-identical, and the Solidity registry decodes
//! the same bytes:
//!
//! ```text
//! body_commitment  [u8; 32]   raw
//! pdf_len          u32        LE
//! report_no        string     u64 LE length || UTF-8 bytes
//! product          string
//! ulr              string
//! issue_date       string
//! row count        u32        LE
//! per row          label, units, method, value, rda, pct (6 strings)
//! ```

use alloc::{string::String, vec::Vec};

use crate::extract::{Output, Row};

#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct PublicValues {
    /// TLSNotary body commitment `SHA256(pdf || blinder)`.
    pub body_commitment: [u8; 32],
    /// Body length; must equal the attested Content-Length.
    pub pdf_len: u32,
    pub report_no: String,
    pub product: String,
    pub ulr: String,
    pub issue_date: String,
    pub rows: Vec<Row>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DecodeError {
    Truncated,
    BadUtf8,
    TrailingBytes,
}

impl core::fmt::Display for DecodeError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.write_str(match self {
            DecodeError::Truncated => "public values too short",
            DecodeError::BadUtf8 => "public values string is not UTF-8",
            DecodeError::TrailingBytes => "trailing bytes after public values",
        })
    }
}

impl From<Output> for PublicValues {
    fn from(o: Output) -> Self {
        PublicValues {
            body_commitment: o.body_commitment,
            pdf_len: o.pdf_len,
            report_no: o.report_no,
            product: o.product,
            ulr: o.ulr,
            issue_date: o.issue_date,
            rows: o.rows,
        }
    }
}

impl PublicValues {
    pub fn encode(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(512);
        out.extend_from_slice(&self.body_commitment);
        out.extend_from_slice(&self.pdf_len.to_le_bytes());
        for s in [&self.report_no, &self.product, &self.ulr, &self.issue_date] {
            put_str(&mut out, s);
        }
        out.extend_from_slice(&(self.rows.len() as u32).to_le_bytes());
        for r in &self.rows {
            for s in [&r.label, &r.units, &r.method, &r.value, &r.rda, &r.pct] {
                put_str(&mut out, s);
            }
        }
        out
    }

    pub fn decode(b: &[u8]) -> Result<Self, DecodeError> {
        let mut r = Reader(b);
        let body_commitment: [u8; 32] = r.take(32)?.try_into().map_err(|_| DecodeError::Truncated)?;
        let pdf_len = r.u32()?;
        let report_no = r.string()?;
        let product = r.string()?;
        let ulr = r.string()?;
        let issue_date = r.string()?;
        let n = r.u32()?;
        let mut rows = Vec::new();
        for _ in 0..n {
            rows.push(Row {
                label: r.string()?,
                units: r.string()?,
                method: r.string()?,
                value: r.string()?,
                rda: r.string()?,
                pct: r.string()?,
            });
        }
        if !r.0.is_empty() {
            return Err(DecodeError::TrailingBytes);
        }
        Ok(PublicValues { body_commitment, pdf_len, report_no, product, ulr, issue_date, rows })
    }
}

fn put_str(out: &mut Vec<u8>, s: &str) {
    out.extend_from_slice(&(s.len() as u64).to_le_bytes());
    out.extend_from_slice(s.as_bytes());
}

struct Reader<'a>(&'a [u8]);

impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], DecodeError> {
        if self.0.len() < n {
            return Err(DecodeError::Truncated);
        }
        let (a, b) = self.0.split_at(n);
        self.0 = b;
        Ok(a)
    }

    fn u32(&mut self) -> Result<u32, DecodeError> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().map_err(|_| DecodeError::Truncated)?))
    }

    fn string(&mut self) -> Result<String, DecodeError> {
        let n = u64::from_le_bytes(self.take(8)?.try_into().map_err(|_| DecodeError::Truncated)?);
        let n = usize::try_from(n).map_err(|_| DecodeError::Truncated)?;
        String::from_utf8(self.take(n)?.to_vec()).map_err(|_| DecodeError::BadUtf8)
    }
}
