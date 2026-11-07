#!/usr/bin/env python3
"""Patch reviewed upstream source in a disposable VM. Does not build or install."""

import argparse
import hashlib
from pathlib import Path
import subprocess

REVISION = "ad03c835f5f7e152b625543c488eec446e3206c0"
HASHES = {
    "transpiler/src/main.rs": "6d0ffc5037455bc45b6a5af42f8c52310b836e2f55186aab2ece01eacf684494",
    "examples/fibonacci/src/main.rs": "6e16e4dd64783c1dab4c187ea96fe735a32c82dcbd7f7f6a50f11bb0fcb65378",
    "jolt-core/src/poly/commitment/dory/commitment_scheme.rs": "6d3ed084928c54684a1025eaeb4efb0a5b99f76bb844e5868691878ffc469306",
}


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one source anchor: {old[:100]!r}")
    return text.replace(old, new, 1)


def patch_main(text):
    text = replace_once(
        text,
        "use ark_serialize::CanonicalDeserialize;",
        "mod export_fixture;\n\nuse ark_serialize::CanonicalDeserialize;",
    )
    text = replace_once(
        text,
        "    // =========================================================================\n    // Step 2: Convert proof to symbolic representation",
        """    assert!(args.trusted_advice.is_none(), "Fixture schema does not support advice");
    let fixture_dir = args.output_dir.as_ref().expect("Explicit output directory required");
    export_fixture::export(
        fixture_dir, &proof_bytes, &io_device_bytes, &preprocessing_bytes,
        &real_proof, &real_preprocessing,
    );

    // =========================================================================
    // Step 2: Convert proof to symbolic representation""",
    )
    return replace_once(
        text,
        "    // Save bundle to JSON (common to all targets)",
        """    let witness_values = var_alloc.witness_values();
    let mut indexed_witness = std::collections::BTreeMap::new();
    for (idx, name, target_field) in var_alloc.descriptions_with_fields() {
        let value = witness_values.get(&(*idx as usize))
            .unwrap_or_else(|| panic!("Missing witness {idx}: {name}"));
        indexed_witness.insert(idx.to_string(), serde_json::json!({
            "name": name, "field": format!("{target_field:?}"), "value": value
        }));
    }
    std::fs::write(output_dir.join("scalar-witness.json"),
        serde_json::to_vec_pretty(&indexed_witness).unwrap()).unwrap();

    // Save bundle to JSON (common to all targets)""",
    )


def patch_fibonacci(text):
    text = replace_once(
        text,
        '    let save_to_disk = std::env::args().any(|arg| arg == "--save");',
        """    let save_to_disk = std::env::args().any(|arg| arg == "--save");
    let input: u32 = std::env::var("JOLT_FIXTURE_FIB_N")
        .expect("Set JOLT_FIXTURE_FIB_N").parse().expect("Expected u32");""",
    )
    for old, new in [
        (
            "guest::trace_fib_to_file(trace_file, 50)",
            "guest::trace_fib_to_file(trace_file, input)",
        ),
        ("prove_fib(50)", "prove_fib(input)"),
        (
            "verify_fib(50, output, io_device.panic, proof)",
            "verify_fib(input, output, io_device.panic, proof)",
        ),
        (
            '    info!("valid: {is_valid}");',
            '    info!("valid: {is_valid}");\n    assert!(is_valid, "Native SDK verification rejected proof");',
        ),
    ]:
        text = replace_once(text, old, new)
    return text


def patch_pcs(text):
    return replace_once(
        text,
        '        let _span = trace_span!("DoryCommitmentScheme::verify").entered();',
        """        let _span = trace_span!("DoryCommitmentScheme::verify").entered();
        #[cfg(feature = "transcript-poseidon")]
        if let Some(directory) = std::env::var_os("JOLT_FIXTURE_PCS_CAPTURE") {
            let directory = std::path::PathBuf::from(directory);
            let poseidon = (transcript as &dyn std::any::Any)
                .downcast_ref::<crate::transcripts::PoseidonTranscript>()
                .expect("Fixture capture requires Poseidon");
            let mut state = poseidon.state.to_vec();
            state.extend_from_slice(&poseidon.n_rounds.to_le_bytes());
            std::fs::write(directory.join("transcript.bin"), state).unwrap();
            let point: Vec<ark_bn254::Fr> = opening_point.iter().map(|p| (*p).into()).collect();
            let mut bytes = Vec::new();
            point.serialize_compressed(&mut bytes).unwrap();
            std::fs::write(directory.join("opening_point.bin"), &bytes).unwrap();
            bytes.clear();
            opening.serialize_compressed(&mut bytes).unwrap();
            std::fs::write(directory.join("opening.bin"), &bytes).unwrap();
            bytes.clear();
            commitment.serialize_compressed(&mut bytes).unwrap();
            std::fs::write(directory.join("commitment.bin"), &bytes).unwrap();
        }""",
    )


def prepare(root):
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != REVISION:
        raise ValueError(f"Wrong upstream revision: {revision}")
    patches = [patch_main, patch_fibonacci, patch_pcs]
    outputs = {}
    for (relative, digest), patch in zip(HASHES.items(), patches):
        source = (root / relative).read_bytes()
        if hashlib.sha256(source).hexdigest() != digest:
            raise ValueError(f"Source changed, refusing to patch: {relative}")
        outputs[root / relative] = patch(source.decode())
    exporter = root / "transpiler/src/export_fixture.rs"
    if exporter.exists():
        raise ValueError(f"Refusing to overwrite {exporter}")
    exporter_source = Path(__file__).with_name("export_fixture.rs").read_bytes()
    for path, content in outputs.items():
        path.write_text(content)
    exporter.write_bytes(exporter_source)
    print("Prepared pinned upstream source. No build or proof generation performed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()
    prepare(args.upstream.resolve())
