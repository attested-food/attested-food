// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {Verifier} from "../src/vendors/sp1/v6_1_0/Groth16Verifier.sol";

/// @notice A Groth16 proof of SP1's v6.1.0 wrap circuit made by snarkrs instead of gnark
///         (test/fixtures/snarkrs-groth16.json, a backend2 job's witness), checked by the
///         same pairing verifier `SP1VerifierGroth16` calls.
contract SnarkrsGroth16Test is Test {
    Verifier verifier;
    uint256[8] proof;
    uint256[5] input;

    function setUp() public {
        string memory j = vm.readFile("test/fixtures/snarkrs-groth16.json");
        proof = abi.decode(vm.parseJsonBytes(j, ".proof"), (uint256[8]));
        uint256[] memory xs = vm.parseJsonUintArray(j, ".input");
        for (uint256 i = 0; i < 5; i++) {
            input[i] = xs[i];
        }
        verifier = new Verifier();
    }

    function test_snarkrsProofVerifies() public view {
        verifier.verifyProof(proof, input);
    }

    function test_rejectsTamperedProof() public {
        proof[2] ^= 1;
        vm.expectRevert();
        verifier.verifyProof(proof, input);
    }

    function test_rejectsOtherPublicInput() public {
        input[1] ^= 1;
        vm.expectRevert(Verifier.ProofInvalid.selector);
        verifier.verifyProof(proof, input);
    }
}
