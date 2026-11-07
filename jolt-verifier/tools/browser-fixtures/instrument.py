#!/usr/bin/env python3
"""Add read-only native witness logging to the pinned, patched browser sources."""

from pathlib import Path
import sys


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Missing or ambiguous source anchor: {old[:90]}")
    return text.replace(old, new, 1)


def logger(filename):
    return """
// Native fixture diagnostics only; does not alter transcript state.
fn fixture_record(kind: &str, bytes: &[u8]) {
    if let Some(directory) = std::env::var_os("JOLT_BROWSER_FIXTURE_CAPTURE") {
        use std::io::Write;
        let path = std::path::PathBuf::from(directory).join("FILENAME");
        let mut file = std::fs::OpenOptions::new().create(true).append(true).open(path).unwrap();
        let hex: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
        writeln!(file, "{kind}\\t{hex}").unwrap();
    }
}
""".replace(
        "FILENAME", filename
    )


def prepare(root):
    outer = root / ".wasm-deps/jolt/crates/jolt-transcript/src/legacy.rs"
    nested = root / ".wasm-deps/akita/crates/akita-transcript/src/sponge.rs"
    batch = root / ".wasm-deps/jolt/crates/jolt-akita/src/native_batching.rs"
    a, b, c = outer.read_text(), nested.read_text(), batch.read_text()
    for source in (a, b, c):
        if "JOLT_BROWSER_FIXTURE_CAPTURE" in source:
            raise ValueError("Instrumentation already applied")
    a = once(
        a,
        "    fn new(label: &'static [u8]) -> Self {",
        '    fn new(label: &\'static [u8]) -> Self {\n        fixture_record("init", label);',
    )
    a = once(
        a,
        "    fn append_bytes(&mut self, bytes: &[u8]) {",
        '    fn append_bytes(&mut self, bytes: &[u8]) {\n        fixture_record("absorb", bytes);',
    )
    a = once(
        a,
        "        F::from_challenge_bytes(&buf)",
        '        fixture_record("challenge", &buf);\n        F::from_challenge_bytes(&buf)',
    )
    a = once(
        a,
        "        F::from_scalar_challenge_bytes(&buf)",
        '        fixture_record("challenge_scalar", &buf);\n        F::from_scalar_challenge_bytes(&buf)',
    )
    a += logger("jolt-transcript.tsv")
    b = once(
        b,
        "    pub fn bind_instance_bytes(&mut self, instance_bytes: &[u8]) {",
        '    pub fn bind_instance_bytes(&mut self, instance_bytes: &[u8]) {\n        fixture_record("session", &self.session_label);\n        fixture_record("instance", instance_bytes);',
    )
    b = once(
        b,
        "    pub fn absorb_bytes(&mut self, _label: Label, bytes: &[u8]) {",
        '    pub fn absorb_bytes(&mut self, _label: Label, bytes: &[u8]) {\n        fixture_record("absorb", bytes);',
    )
    b = once(
        b,
        "        out\n    }\n\n    /// Squeeze one native transcript block.",
        '        fixture_record("squeeze_bytes", &out);\n        out\n    }\n\n    /// Squeeze one native transcript block.',
    )
    b = once(
        b,
        """    pub fn squeeze_block(&mut self, _label: Label) -> [u8; SQUEEZE_CHUNK_LEN] {
        match self.state_mut() {
            TranscriptState::Prover(state) => state.verifier_message(),
            TranscriptState::Verifier(state) => state.verifier_message(),
        }
    }""",
        """    pub fn squeeze_block(&mut self, _label: Label) -> [u8; SQUEEZE_CHUNK_LEN] {
        let out: [u8; SQUEEZE_CHUNK_LEN] = match self.state_mut() {
            TranscriptState::Prover(state) => state.verifier_message(),
            TranscriptState::Verifier(state) => state.verifier_message(),
        };
        fixture_record("squeeze_block", &out);
        out
    }""",
    )
    b += logger("akita-transcript.tsv")
    prefix, marker, verifier = c.partition("    pub(crate) fn verify_trace_batch<T>(")
    if not marker:
        raise ValueError("Missing native verifier seam")
    verifier = once(
        verifier,
        """        let mut akita_transcript =
            bind_grouped_statement_transcripts(transcript, setup, selection, precommitted, main)?;""",
        """        if let Some(directory) = std::env::var_os("JOLT_BROWSER_FIXTURE_CAPTURE") {
            let directory = std::path::PathBuf::from(directory);
            std::fs::write(directory.join("pcs-decoded.txt"), format!("{backend_proof:#?}")).unwrap();
            std::fs::write(directory.join("pcs-boundary.txt"), format!("point={backend_main_point:#?}\\nevaluations={:#?}\\ncommitment={:#?}", main.evaluations, main.commitment)).unwrap();
        }
        let mut akita_transcript =
            bind_grouped_statement_transcripts(transcript, setup, selection, precommitted, main)?;""",
    )
    c = prefix + marker + verifier
    for path, source in [(outer, a), (nested, b), (batch, c)]:
        path.write_text(source)
    print("Added native read-only transcript and decoded-PCS diagnostics")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]).resolve())
