// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {TestFund, IERC20} from "../src/TestFund.sol";
import {MockUSD} from "../src/MockUSD.sol";
import {EurekhaReportRegistry} from "eurekha/EurekhaReportRegistry.sol";
import {SP1Groth16ProofVerifier} from "eurekha/vendors/SP1Groth16ProofVerifier.sol";
import {SP1Verifier as SP1VerifierGroth16} from "eurekha/vendors/sp1/v6_1_0/SP1VerifierGroth16.sol";

/// Uses backend2-rs's real SP1 Groth16 artifact of the choco-millet-muesli Eurekha report.
contract TestFundTest is Test {
    bytes32 constant SP1 = bytes32("sp1");
    MockUSD usd = new MockUSD();
    TestFund fund;
    bytes32 id = keccak256("req");
    address admin = makeAddr("admin");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address tester = makeAddr("tester");
    bytes pv;
    bytes proof;
    bytes sig;

    function setUp() public {
        string memory j = vm.readFile("../backend2-rs/contracts/test/fixtures/sp1-groth16.json");
        pv = vm.parseJsonBytes(j, ".publicValues");
        proof = vm.parseJsonBytes(j, ".proof");
        sig = vm.parseJsonBytes(j, ".notarySignature");
        EurekhaReportRegistry registry =
            new EurekhaReportRegistry(0x1a642f0E3c3aF545E7AcBD38b07251B3990914F1, "eurekhalabs.s3.amazonaws.com");
        registry.addVerifier(
            SP1, new SP1Groth16ProofVerifier(address(new SP1VerifierGroth16()), vm.parseJsonBytes32(j, ".vkey"))
        );
        fund = new TestFund(IERC20(address(usd)), registry, admin);
        address[4] memory users = [admin, alice, bob, tester];
        for (uint256 i; i < users.length; i++) {
            usd.mint(users[i], 1000e6);
            vm.prank(users[i]);
            usd.approve(address(fund), type(uint256).max);
        }
    }

    function give(address who, uint256 amount) internal {
        vm.prank(who);
        fund.contribute(id, amount);
    }

    function take() internal {
        vm.prank(tester);
        fund.commit(id);
    }

    function submit() internal {
        vm.prank(tester);
        fund.submitReport(id, SP1, pv, proof, sig);
    }

    function test_contributeCapsAtGoal() public {
        give(alice, 60e6);
        vm.expectRevert("bad amount");
        give(alice, 41e6);
        give(alice, 40e6);
        assertEq(fund.contributed(id, alice), 100e6);
        assertEq(fund.contributors(id).length, 1);
    }

    function test_validProofPaysPoolAndStake() public {
        give(alice, 100e6);
        take();
        assertEq(usd.balanceOf(tester), 890e6);
        vm.prank(alice);
        vm.expectRevert("not your job");
        fund.submitReport(id, SP1, pv, proof, sig);
        vm.roll(42);
        vm.expectEmit(address(fund));
        emit TestFund.ReportSubmitted(id, tester, 210e6, pv);
        submit();
        (,,,,, uint64 reportBlock) = fund.campaigns(id);
        assertEq(reportBlock, 42);
        assertEq(usd.balanceOf(tester), 1100e6);
        assertEq(fund.contributed(id, tester), 0);
        vm.expectRevert("closed");
        give(alice, 1e6);
    }

    function test_shortfallCountsAsTesterContribution() public {
        give(alice, 60e6);
        take();
        submit();
        assertEq(usd.balanceOf(tester), 1060e6);
        assertEq(fund.contributed(id, tester), 40e6);
        (,,,, uint256 shares,) = fund.campaigns(id);
        assertEq(shares, 100e6);
    }

    function test_badProofRejectedAndReportSingleUse() public {
        give(alice, 100e6);
        take();
        bytes memory bad = sig;
        bad[0] ^= 0x01;
        vm.prank(tester);
        vm.expectRevert();
        fund.submitReport(id, SP1, pv, proof, bad);
        submit();

        bytes32 other = keccak256("other");
        vm.prank(tester);
        fund.commit(other);
        vm.prank(tester);
        vm.expectRevert("report already used");
        fund.submitReport(other, SP1, pv, proof, sig);
    }

    function test_distributeProRata() public {
        give(alice, 10e6);
        give(bob, 40e6);
        take();
        submit(); // tester's shortfall: 50
        vm.expectRevert("not admin");
        fund.distribute(id, 200e6);
        vm.prank(admin);
        fund.distribute(id, 200e6);
        assertEq(usd.balanceOf(alice), 990e6 + 20e6);
        assertEq(usd.balanceOf(bob), 960e6 + 80e6);
        assertEq(usd.balanceOf(tester), 1050e6 + 100e6);
        assertEq(usd.balanceOf(admin), 800e6);
    }

    function test_distributeNeedsTestedPool() public {
        give(alice, 10e6);
        vm.prank(admin);
        vm.expectRevert("not tested");
        fund.distribute(id, 1e6);
    }

    function test_lateTesterIsSlashed() public {
        give(alice, 100e6);
        take();
        vm.expectRevert("not slashable");
        fund.slash(id);
        vm.warp(block.timestamp + 30 days + 1);
        vm.prank(tester);
        vm.expectRevert("deadline passed");
        fund.submitReport(id, SP1, pv, proof, sig);
        fund.slash(id);
        (uint256 pool, address t,,,,) = fund.campaigns(id);
        assertEq(pool, 210e6);
        assertEq(t, address(0));
    }
}
