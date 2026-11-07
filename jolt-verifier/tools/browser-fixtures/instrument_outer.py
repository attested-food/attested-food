#!/usr/bin/env python3
"""Instrument the compiled DigestTranscript alias, preserving every returned value."""

from pathlib import Path
import sys

from instrument import once

HELPERS = r"""
// Native fixture diagnostics only; all transcript values are observed unchanged.
fn fixture_digest_record(op: &str, before_round: u32, after_round: u32,
    before: &[u8; 32], after: &[u8; 32], payload: &[u8], raw: &[u8], field: &[u8]) {
    if let Some(directory) = std::env::var_os("JOLT_BROWSER_FIXTURE_CAPTURE") {
        use std::io::Write;
        let hex = |bytes: &[u8]| bytes.iter().map(|b| format!("{b:02x}")).collect::<String>();
        let path = std::path::PathBuf::from(directory).join("jolt-transcript.jsonl");
        let mut file = std::fs::OpenOptions::new().create(true).append(true).open(path).unwrap();
        writeln!(file, "{{\"op\":\"{op}\",\"round_before\":{before_round},\"round_after\":{after_round},\"state_before_hex\":\"{}\",\"state_after_hex\":\"{}\",\"payload_hex\":\"{}\",\"raw_hex\":\"{}\",\"field_le_hex\":\"{}\"}}", hex(before), hex(after), hex(payload), hex(raw), hex(field)).unwrap();
    }
}

/// Records semantic label words alongside their unchanged absorb events.
pub(crate) fn fixture_digest_label(op: &str, label: &[u8], count: Option<u64>) {
    if let Some(directory) = std::env::var_os("JOLT_BROWSER_FIXTURE_CAPTURE") {
        use std::io::Write;
        let label: String = label.iter().map(|b| format!("{b:02x}")).collect();
        let count = count.map_or_else(|| "null".to_owned(), |n| n.to_string());
        let path = std::path::PathBuf::from(directory).join("jolt-transcript.jsonl");
        let mut file = std::fs::OpenOptions::new().create(true).append(true).open(path).unwrap();
        writeln!(file, "{{\"op\":\"{op}\",\"label_hex\":\"{label}\",\"count\":{count}}}").unwrap();
    }
}
"""


def prepare(root):
    directory = root / ".wasm-deps/jolt/crates/jolt-transcript/src"
    digest = directory / "digest.rs"
    legacy = directory / "legacy.rs"
    a, b = digest.read_text(), legacy.read_text()
    if "fixture_digest_record" in a or "fixture_digest_label" in b:
        raise ValueError("Outer instrumentation already applied")
    a = once(
        a,
        "        self.challenge_bytes(out);",
        """        self.challenge_bytes(out);
        fixture_digest_record("raw_bytes", self.n_rounds, self.n_rounds,
            &self.state, &self.state, &[], out, &[]);""",
    )
    a = once(
        a,
        """        let hash: [u8; 32] = self.hasher().finalize().into();
        out.copy_from_slice(&hash);
        self.update_state(hash);""",
        """        let before = self.state;
        let round = self.n_rounds;
        let hash: [u8; 32] = self.hasher().finalize().into();
        out.copy_from_slice(&hash);
        self.update_state(hash);
        fixture_digest_record("squeeze", round, self.n_rounds,
            &before, &self.state, &[], &hash, &[]);""",
    )
    a = once(
        a,
        """        let hash: [u8; 32] = D::new().chain_update(padded).finalize().into();

        Self {""",
        """        let hash: [u8; 32] = D::new().chain_update(padded).finalize().into();
        fixture_digest_label("session", label, None);
        fixture_digest_record("init", 0, 0, &[0u8; 32], &hash, &padded, &[], &[]);

        Self {""",
    )
    a = once(
        a,
        """        let hash: [u8; 32] = self.hasher().chain_update(bytes).finalize().into();
        self.update_state(hash);""",
        """        let before = self.state;
        let round = self.n_rounds;
        let hash: [u8; 32] = self.hasher().chain_update(bytes).finalize().into();
        self.update_state(hash);
        fixture_digest_record("absorb", round, self.n_rounds,
            &before, &self.state, bytes, &[], &[]);""",
    )
    for method, event in [
        ("from_challenge_bytes", "decode_challenge"),
        ("from_scalar_challenge_bytes", "decode_scalar"),
    ]:
        a = once(
            a,
            f"        F::{method}(&buf)",
            f"""        let field = F::{method}(&buf);
        fixture_digest_record("{event}", self.n_rounds, self.n_rounds,
            &self.state, &self.state, &[], &buf, &field.to_bytes_le_vec());
        field""",
        )
    a = once(
        a,
        """    fn state(&self) -> [u8; 32] {
        self.state""",
        """    fn state(&self) -> [u8; 32] {
        fixture_digest_record("state", self.n_rounds, self.n_rounds,
            &self.state, &self.state, &[], &[], &[]);
        self.state""",
    )
    for kind, operation, arguments in [
        ("Label", "label", "self.0, None"),
        ("LabelWithCount", "label_count", "self.0, Some(self.1)"),
        ("U64Word", "u64", "&[], Some(self.0)"),
    ]:
        anchor = f"impl AppendToTranscript for {kind} {{\n    fn append_to_transcript<T: Transcript>(&self, transcript: &mut T) {{"
        b = once(
            b,
            anchor,
            anchor
            + f'\n        crate::digest::fixture_digest_label("{operation}", {arguments});',
        )
    a += HELPERS
    digest.write_text(a)
    legacy.write_text(b)
    print("Instrumented exact compiled DigestTranscript and semantic label encodings")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]).resolve())
