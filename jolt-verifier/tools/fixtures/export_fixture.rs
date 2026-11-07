//! Export non-ZK Poseidon/Dory fixtures before symbolic execution.

use ark_bn254::{Fq, Fq12, Fq2, G1Projective, G2Projective};
use ark_ff::PrimeField;
use ark_serialize::{CanonicalDeserialize, CanonicalSerialize};
use common::jolt_device::JoltDevice;
use jolt_core::curve::Bn254Curve;
use jolt_core::poly::commitment::dory::{ArkGT, DoryCommitmentScheme};
use jolt_core::zkvm::verifier::{JoltVerifier, JoltVerifierPreprocessing};
use jolt_core::zkvm::RV64IMACProof;
use serde_json::{json, Value};
use std::path::Path;

type Preprocessing = JoltVerifierPreprocessing<ark_bn254::Fr, Bn254Curve, DoryCommitmentScheme>;

fn scalar<F: PrimeField>(value: F) -> String {
    value.into_bigint().to_string()
}

fn fq2(value: Fq2) -> [String; 2] {
    [scalar(value.c0), scalar(value.c1)]
}

fn gt(value: Fq12) -> Value {
    json!([
        [fq2(value.c0.c0), fq2(value.c0.c1), fq2(value.c0.c2)],
        [fq2(value.c1.c0), fq2(value.c1.c1), fq2(value.c1.c2)]
    ])
}

fn g1(value: G1Projective) -> Value {
    json!({"x": scalar(value.x), "y": scalar(value.y), "z": scalar(value.z)})
}

fn g2(value: G2Projective) -> Value {
    json!({"x": fq2(value.x), "y": fq2(value.y), "z": fq2(value.z)})
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn canonical(value: &impl CanonicalSerialize) -> String {
    let mut bytes = Vec::new();
    value.serialize_compressed(&mut bytes).unwrap();
    hex(&bytes)
}

fn decode<T: CanonicalDeserialize>(bytes: &[u8]) -> T {
    let mut reader = bytes;
    let value = T::deserialize_compressed(&mut reader).expect("Invalid canonical input");
    assert!(reader.is_empty(), "Trailing canonical input bytes");
    value
}

fn verify(pp: &Preprocessing, proof: RV64IMACProof, io: JoltDevice) -> bool {
    JoltVerifier::new(pp, proof, io, None, None)
        .and_then(|verifier| verifier.verify())
        .is_ok()
}

pub fn export(
    directory: &Path,
    proof_bytes: &[u8],
    io_bytes: &[u8],
    preprocessing_bytes: &[u8],
    proof: &RV64IMACProof,
    pp: &Preprocessing,
) {
    assert!(!cfg!(feature = "zk"), "Only the non-ZK schema is supported");
    let pcs = &proof.joint_opening_proof;
    assert!(pcs.e2.is_none() && pcs.y_com.is_none());
    assert!(pcs.sigma1_proof.is_none() && pcs.sigma2_proof.is_none());
    assert!(pcs.scalar_product_proof.is_none());
    assert!(
        proof.untrusted_advice_commitment.is_none(),
        "Advice is not supported"
    );
    assert!(pcs.nu <= pcs.sigma);
    assert_eq!(pcs.first_messages.len(), pcs.sigma);
    assert_eq!(pcs.second_messages.len(), pcs.sigma);
    std::fs::create_dir_all(directory).unwrap();
    let capture = directory.join("native-pcs-boundary");
    std::fs::create_dir(&capture).expect("Capture directory must be fresh");
    std::env::set_var("JOLT_FIXTURE_PCS_CAPTURE", &capture);
    let accepted = verify(pp, decode(proof_bytes), decode(io_bytes));
    std::env::remove_var("JOLT_FIXTURE_PCS_CAPTURE");
    assert!(accepted, "Full native verifier rejected original proof");

    let mut bad_pcs: RV64IMACProof = decode(proof_bytes);
    bad_pcs.joint_opening_proof.vmv_message.c.0 += Fq12::from(1u64);
    assert!(
        !verify(pp, bad_pcs, decode(io_bytes)),
        "PCS mutation accepted"
    );
    let mut bad_claim: RV64IMACProof = decode(proof_bytes);
    bad_claim.opening_claims.0.values_mut().next().unwrap().1 += ark_bn254::Fr::from(1u64);
    assert!(
        !verify(pp, bad_claim, decode(io_bytes)),
        "Claim mutation accepted"
    );
    let mut bad_io: JoltDevice = decode(io_bytes);
    assert!(!bad_io.inputs.is_empty(), "Expected Fibonacci input");
    bad_io.inputs[0] ^= 1;
    assert!(
        !verify(pp, decode(proof_bytes), bad_io),
        "IO mutation accepted"
    );

    let read = |name| std::fs::read(capture.join(name)).unwrap();
    let opening_point: Vec<ark_bn254::Fr> = decode(&read("opening_point.bin"));
    let opening: ark_bn254::Fr = decode(&read("opening.bin"));
    let commitment: ArkGT = decode(&read("commitment.bin"));
    let state = read("transcript.bin");
    assert_eq!(state.len(), 36);
    let n_rounds = u32::from_le_bytes(state[32..].try_into().unwrap());
    let setup = &pp.generators;
    let first: Vec<_> = pcs
        .first_messages
        .iter()
        .map(|m| {
            json!({
                "d1_left": gt(m.d1_left.0), "d1_right": gt(m.d1_right.0),
                "d2_left": gt(m.d2_left.0), "d2_right": gt(m.d2_right.0),
                "e1_beta": g1(m.e1_beta.0), "e2_beta": g2(m.e2_beta.0)
            })
        })
        .collect();
    let second: Vec<_> = pcs
        .second_messages
        .iter()
        .map(|m| {
            json!({
                "c_plus": gt(m.c_plus.0), "c_minus": gt(m.c_minus.0),
                "e1_plus": g1(m.e1_plus.0), "e1_minus": g1(m.e1_minus.0),
                "e2_plus": g2(m.e2_plus.0), "e2_minus": g2(m.e2_minus.0)
            })
        })
        .collect();
    let gt_vec = |values: &[ArkGT]| values.iter().map(|value| gt(value.0)).collect::<Vec<_>>();
    let io: JoltDevice = decode(io_bytes);
    let output = json!({
        "schema": "jolt-dory-fixture-v1",
        "upstream_commit": "ad03c835f5f7e152b625543c488eec446e3206c0",
        "transcript": "poseidon", "pcs": "dory-pcs-0.3.0", "zk": false,
        "native_checks": {"original": true, "pcs_tamper_rejected": true,
            "claim_tamper_rejected": true, "io_tamper_rejected": true},
        "circuit_verification": "not-performed-by-exporter",
        "shape": {"trace_length": proof.trace_length, "ram_K": proof.ram_K,
            "rw_config_canonical": canonical(&proof.rw_config),
            "one_hot_config_canonical": canonical(&proof.one_hot_config),
            "dory_layout_canonical": canonical(&proof.dory_layout),
            "commitments": proof.commitments.len(), "nu": pcs.nu, "sigma": pcs.sigma},
        "program_io": {"inputs_hex": hex(&io.inputs), "outputs_hex": hex(&io.outputs),
            "panic": io.panic},
        "commitments": proof.commitments.iter().map(|c| gt(c.0)).collect::<Vec<_>>(),
        "opening_claims": proof.opening_claims.0.iter().map(|(id, (_, claim))|
            json!({"id_canonical": canonical(id), "value": scalar(*claim)})).collect::<Vec<_>>(),
        "joint_opening_proof": {"nu": pcs.nu, "sigma": pcs.sigma,
            "vmv_message": {"c": gt(pcs.vmv_message.c.0), "d2": gt(pcs.vmv_message.d2.0),
                "e1": g1(pcs.vmv_message.e1.0)},
            "first_messages": first, "second_messages": second,
            "final_message": {"e1": g1(pcs.final_message.e1.0), "e2": g2(pcs.final_message.e2.0)},
            "canonical_hex": canonical(pcs)},
        "verifier_setup": {"delta_1l": gt_vec(&setup.delta_1l), "delta_1r": gt_vec(&setup.delta_1r),
            "delta_2l": gt_vec(&setup.delta_2l), "delta_2r": gt_vec(&setup.delta_2r),
            "chi": gt_vec(&setup.chi), "g1_0": g1(setup.g1_0.0), "g2_0": g2(setup.g2_0.0),
            "h1": g1(setup.h1.0), "h2": g2(setup.h2.0), "ht": gt(setup.ht.0),
            "max_log_n": setup.max_log_n, "canonical_hex": canonical(setup)},
        "pcs_boundary": {"opening_point_jolt_order": opening_point.iter().map(|f| scalar(*f)).collect::<Vec<_>>(),
            "opening": scalar(opening), "joint_commitment": gt(commitment.0),
            "transcript_state_le_hex": hex(&state[..32]), "transcript_n_rounds": n_rounds},
        "fields": {"fq_modulus": Fq::MODULUS.to_string(), "fr_modulus": ark_bn254::Fr::MODULUS.to_string()}
    });
    std::fs::write(
        directory.join("full-proof.json"),
        serde_json::to_vec_pretty(&output).unwrap(),
    )
    .unwrap();
    std::fs::write(directory.join("proof.bin"), proof_bytes).unwrap();
    std::fs::write(directory.join("io_device.bin"), io_bytes).unwrap();
    std::fs::write(directory.join("preprocessing.bin"), preprocessing_bytes).unwrap();
    println!("Full native verifier accepted; PCS, claim and IO mutations rejected");
}
