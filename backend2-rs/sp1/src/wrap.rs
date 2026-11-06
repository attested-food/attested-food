//! SP1's Groth16 witness without SP1's Groth16 prover: shrink and wrap a
//! compressed proof on the CPU, then build the gnark witness input exactly as
//! SP1's own Groth16 task does (sp1-prover 6.10.0
//! `worker/prover/recursion.rs`, `run_groth16`), so an external Groth16
//! prover (snarkrs, via `witness-export`) can prove SP1's gnark circuit.

use std::{borrow::Borrow, path::Path, time::Instant};

use anyhow::{anyhow, Context, Result};
use slop_algebra::{AbstractField, PrimeField32};
use slop_bn254::Bn254Fr;
use sp1_hypercube::koalabears_to_bn254;
use sp1_primitives::SP1Field;
use sp1_prover::{
    build::try_build_groth16_artifacts_dir,
    worker::{cpu_worker_builder, SP1LocalNodeBuilder},
};
use sp1_recursion_circuit::{
    machine::SP1ShapedWitnessValues,
    utils::{koalabear_bytes_to_bn254, koalabears_proof_nonce_to_bn254, words_to_bytes},
    witness::{OuterWitness, Witnessable},
};
use sp1_recursion_executor::RecursionPublicValues;
use sp1_recursion_gnark_ffi::GnarkWitness;
use sp1_sdk::SP1ProofWithPublicValues;

/// Write the gnark witness input for `stark` (a compressed proof) to `out`;
/// returns the Groth16 circuit dir it is for.
pub async fn witness(stark: &Path, out: &Path) -> Result<std::path::PathBuf> {
    let proof = SP1ProofWithPublicValues::load(stark).context("load compressed proof")?;

    let t = Instant::now();
    let node = SP1LocalNodeBuilder::from_worker_client_builder(cpu_worker_builder()).build().await?;
    eprintln!("cpu node: {} ms", t.elapsed().as_millis());

    let t = Instant::now();
    let wrap = node.shrink_wrap(&proof.proof).await?;
    eprintln!("shrink + wrap: {} ms", t.elapsed().as_millis());

    let t = Instant::now();
    let dir = try_build_groth16_artifacts_dir(&wrap.vk, &wrap.proof).await?;
    let pv: &RecursionPublicValues<SP1Field> = wrap.proof.public_values.as_slice().borrow();
    let vkey_hash = koalabears_to_bn254(&pv.sp1_vk_digest);
    let digest: [SP1Field; 32] = words_to_bytes(&pv.committed_value_digest)
        .try_into()
        .map_err(|_| anyhow!("committed_value_digest is not 32 bytes"))?;
    let committed_values_digest = koalabear_bytes_to_bn254(&digest);
    let exit_code = Bn254Fr::from_canonical_u32(pv.exit_code.as_canonical_u32());
    let proof_nonce = koalabears_proof_nonce_to_bn254(&pv.proof_nonce);
    let vk_root = koalabears_to_bn254(&pv.vk_root);
    let input = SP1ShapedWitnessValues { vks_and_proofs: vec![(wrap.vk, wrap.proof)], is_complete: true };
    let mut witness = OuterWitness::default();
    input.write(&mut witness);
    witness.write_committed_values_digest(committed_values_digest);
    witness.write_vkey_hash(vkey_hash);
    witness.write_exit_code(exit_code);
    witness.write_vk_root(vk_root);
    witness.write_proof_nonce(proof_nonce);
    std::fs::write(out, serde_json::to_vec(&GnarkWitness::new(witness))?)?;
    eprintln!("witness: {} ms", t.elapsed().as_millis());
    Ok(dir)
}
