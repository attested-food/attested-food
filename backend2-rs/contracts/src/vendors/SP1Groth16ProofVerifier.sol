// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IEurekhaProofVerifier} from "../IEurekhaProofVerifier.sol";
import {ISP1Verifier} from "./sp1/ISP1Verifier.sol";

/// @title SP1Groth16ProofVerifier
/// @notice SP1 v6 Groth16 proof of the pinned guest vkey through Succinct's SP1VerifierGroth16 (v6.1.0,
///         vendored in ./sp1). `proof` is `SP1ProofWithPublicValues::bytes()`: the 4-byte verifier selector,
///         then the Groth16 proof; the verifier checks the selector and that the program committed
///         exactly `publicValues`.
contract SP1Groth16ProofVerifier is IEurekhaProofVerifier {
    ISP1Verifier public immutable groth16;
    bytes32 public immutable programVKey;

    constructor(address _groth16, bytes32 _programVKey) {
        groth16 = ISP1Verifier(_groth16);
        programVKey = _programVKey;
    }

    function verify(bytes calldata publicValues, bytes calldata proof) external view {
        groth16.verifyProof(programVKey, publicValues, proof);
    }

    function programId() external view returns (bytes32) {
        return programVKey;
    }
}
