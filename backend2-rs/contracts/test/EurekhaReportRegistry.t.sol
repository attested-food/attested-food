// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test, console2} from "forge-std/Test.sol";
import {EurekhaReportRegistry} from "../src/EurekhaReportRegistry.sol";
import {EurekhaPublicValues} from "../src/EurekhaPublicValues.sol";
import {IEurekhaProofVerifier} from "../src/IEurekhaProofVerifier.sol";
import {SP1Groth16ProofVerifier} from "../src/vendors/SP1Groth16ProofVerifier.sol";
import {SP1Verifier as SP1VerifierGroth16} from "../src/vendors/sp1/v6_1_0/SP1VerifierGroth16.sol";

/// @notice A real SP1 Groth16 artifact from `eurekha-sp1 prove` (test/fixtures/sp1-groth16.json): a proxy-mode
///         TLSNotary session (public dev notary) of the mock choco-millet-muesli report on eurekhalabs S3.
contract EurekhaReportRegistryTest is Test {
    /// @dev Address of the public dev notary key [1u8; 32].
    address constant NOTARY = 0x1a642f0E3c3aF545E7AcBD38b07251B3990914F1;
    string constant HOST = "eurekhalabs.s3.amazonaws.com";
    bytes32 constant SP1 = bytes32("sp1");

    EurekhaReportRegistry registry;
    SP1Groth16ProofVerifier adapter;
    bytes publicValues;
    bytes proof;
    bytes signature;

    /// @dev The artifact under test; overridden to run the same checks on another prover's proof.
    function fixture() internal pure virtual returns (string memory) {
        return "test/fixtures/sp1-groth16.json";
    }

    function setUp() public {
        string memory j = vm.readFile(fixture());
        publicValues = vm.parseJsonBytes(j, ".publicValues");
        proof = vm.parseJsonBytes(j, ".proof");
        signature = vm.parseJsonBytes(j, ".notarySignature");
        adapter = new SP1Groth16ProofVerifier(address(new SP1VerifierGroth16()), vm.parseJsonBytes32(j, ".vkey"));
        registry = new EurekhaReportRegistry(NOTARY, HOST);
        registry.addVerifier(SP1, adapter);
    }

    function test_submit() public {
        (bytes memory pv, bytes memory pf, bytes memory sig) = (publicValues, proof, signature);
        uint256 g = gasleft();
        uint256 id = registry.submit(SP1, pv, pf, sig);
        console2.log("submit gas (excl. calldata)", g - gasleft());
        console2.log("calldata bytes", pv.length + pf.length + sig.length);
        assertEq(id, 1);
        (
            bytes32 backend,
            bytes32 keySha256,
            bytes32 redactedSha256,,
            uint64 sessionTime,
            uint32 pdfLen,
            address submitter
        ) = registry.reports(id);
        assertEq(backend, SP1);
        assertEq(keySha256, sha256("reports/2026/choco-millet-muesli-38e6ce6dad24bbef.pdf"));
        assertEq(redactedSha256, 0x0f3af67c23f319ba5c0c664630c7d7fa8996338904f381909dc0932ee5e426cc);
        assertEq(pdfLen, 90718);
        assertGt(sessionTime, 1_700_000_000);
        assertEq(submitter, address(this));
        assertEq(registry.reportsForKey(keySha256).length, 1);

        vm.expectRevert(abi.encodeWithSelector(EurekhaReportRegistry.AlreadyAttested.selector, keccak256(publicValues)));
        registry.submit(SP1, publicValues, proof, signature);
    }

    function test_verifyGas() public view {
        (bytes memory pv, bytes memory pf) = (publicValues, proof);
        uint256 g = gasleft();
        adapter.verify(pv, pf);
        console2.log("groth16 verify gas", g - gasleft());
    }

    function test_decode() public view {
        (
            EurekhaPublicValues.Head memory h,
            uint32[2][] memory spans,
            EurekhaPublicValues.KeyValue[] memory kv,
            EurekhaPublicValues.Row[] memory rows
        ) = registry.decode(publicValues);
        assertEq(h.serverName, HOST);
        assertEq(h.header.length, 54);
        assertEq(spans.length, 5);
        assertEq(spans[0][0], 39543);
        assertEq(kv.length, 22);
        assertEq(rows.length, 11);
        for (uint256 i; i < kv.length; i++) {
            assertTrue(keccak256(bytes(kv[i].key)) != keccak256("Client Name"));
        }
    }

    function test_rejectsForgedSignature() public {
        bytes memory sig = signature;
        sig[5] ^= 0x01;
        vm.expectRevert(EurekhaReportRegistry.BadNotarySignature.selector);
        registry.submit(SP1, publicValues, proof, sig);
    }

    function test_rejectsOtherNotary() public {
        EurekhaReportRegistry other = new EurekhaReportRegistry(address(0xBEEF), HOST);
        other.addVerifier(SP1, adapter);
        vm.expectRevert(EurekhaReportRegistry.BadNotarySignature.selector);
        other.submit(SP1, publicValues, proof, signature);
    }

    function test_rejectsOtherBucket() public {
        EurekhaReportRegistry other = new EurekhaReportRegistry(NOTARY, "equinox-labs-latest.s3.amazonaws.com");
        other.addVerifier(SP1, adapter);
        vm.expectRevert(EurekhaReportRegistry.BadServerName.selector);
        other.submit(SP1, publicValues, proof, signature);
    }

    function test_rejectsTamperedValues() public {
        bytes memory pv = publicValues;
        pv[pv.length - 1] ^= 0x01;
        vm.expectRevert();
        registry.submit(SP1, pv, proof, signature);
    }

    function test_rejectsUnknownBackend() public {
        vm.expectRevert(abi.encodeWithSelector(EurekhaReportRegistry.UnknownBackend.selector, bytes32("openvm")));
        registry.submit(bytes32("openvm"), publicValues, proof, signature);
    }

    function test_onlyOwnerAddsVerifiers() public {
        vm.prank(address(0xBEEF));
        vm.expectRevert(EurekhaReportRegistry.NotOwner.selector);
        registry.addVerifier(bytes32("x"), IEurekhaProofVerifier(address(adapter)));
        vm.expectRevert(abi.encodeWithSelector(EurekhaReportRegistry.VerifierExists.selector, SP1));
        registry.addVerifier(SP1, adapter);
    }
}

/// @notice The same checks on an artifact whose Groth16 proof snarkrs made on the GPU inside sp1-gpu-server
///         (`sp1/gpu-server`, `SP1_GROTH16_PROVER=snarkrs`), from a live backend2 job on the same report.
contract EurekhaReportRegistrySnarkrsTest is EurekhaReportRegistryTest {
    function fixture() internal pure override returns (string memory) {
        return "test/fixtures/sp1-groth16-snarkrs.json";
    }
}
