// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {TestFund, IERC20} from "../src/TestFund.sol";
import {MockUSD} from "../src/MockUSD.sol";
import {EurekhaReportRegistry} from "eurekha/EurekhaReportRegistry.sol";
import {SP1Groth16ProofVerifier} from "eurekha/vendors/SP1Groth16ProofVerifier.sol";
import {SP1Verifier as SP1VerifierGroth16} from "eurekha/vendors/sp1/v6_1_0/SP1VerifierGroth16.sol";

/// Env (all optional): USD (reuse a token, else MockUSD), REGISTRY (reuse, else deploy one with
/// NOTARY + VKEY), ADMIN (default: the deployer).
contract Deploy is Script {
    // Public dev notary of backend2-rs (key [1u8; 32]) and the live prover's SP1 program vkey.
    address constant DEV_NOTARY = 0x1a642f0E3c3aF545E7AcBD38b07251B3990914F1;
    bytes32 constant VKEY = 0x00721e792ebc24a7648b3bf2ed694871aca88d0c10a96e8b5a88e20c213c9500;

    function run() external {
        vm.startBroadcast();
        address usd = vm.envOr("USD", address(0));
        if (usd == address(0)) usd = address(new MockUSD());
        address registry = vm.envOr("REGISTRY", address(0));
        if (registry == address(0)) {
            EurekhaReportRegistry r =
                new EurekhaReportRegistry(vm.envOr("NOTARY", DEV_NOTARY), "eurekhalabs.s3.amazonaws.com");
            r.addVerifier(
                bytes32("sp1"),
                new SP1Groth16ProofVerifier(address(new SP1VerifierGroth16()), vm.envOr("VKEY", VKEY))
            );
            registry = address(r);
        }
        TestFund fund = new TestFund(IERC20(usd), EurekhaReportRegistry(registry), vm.envOr("ADMIN", msg.sender));
        vm.stopBroadcast();
        console.log("VITE_USD_ADDRESS=%s", usd);
        console.log("VITE_FUND_ADDRESS=%s", address(fund));
        console.log("REGISTRY=%s", registry);
    }
}
