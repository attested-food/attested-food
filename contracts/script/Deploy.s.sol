// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {TestFund, IERC20} from "../src/TestFund.sol";
import {MockUSD} from "../src/MockUSD.sol";

/// USD=<token> to reuse an existing stablecoin; otherwise deploys MockUSD.
contract Deploy is Script {
    function run() external {
        vm.startBroadcast();
        address usd = vm.envOr("USD", address(0));
        if (usd == address(0)) usd = address(new MockUSD());
        TestFund fund = new TestFund(IERC20(usd));
        vm.stopBroadcast();
        console.log("VITE_USD_ADDRESS=%s", usd);
        console.log("VITE_FUND_ADDRESS=%s", address(fund));
    }
}
