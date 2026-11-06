// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {TestFund, IERC20} from "../src/TestFund.sol";
import {MockUSD} from "../src/MockUSD.sol";

contract TestFundTest is Test {
    MockUSD usd = new MockUSD();
    TestFund fund = new TestFund(IERC20(address(usd)));
    bytes32 id = keccak256("req");
    address alice = makeAddr("alice");
    address tester = makeAddr("tester");

    function setUp() public {
        for (uint256 i; i < 2; i++) {
            address a = i == 0 ? alice : tester;
            usd.mint(a, 1000e6);
            vm.prank(a);
            usd.approve(address(fund), type(uint256).max);
        }
    }

    function fundFully() internal {
        vm.prank(alice);
        fund.contribute(id, 100e6);
    }

    function status() internal view returns (TestFund.Status s) {
        (,,, s) = fund.campaigns(id);
    }

    function test_contributeCapsAtGoal() public {
        vm.startPrank(alice);
        fund.contribute(id, 60e6);
        vm.expectRevert("bad amount");
        fund.contribute(id, 41e6);
        fund.contribute(id, 40e6);
        assertEq(fund.contributed(id, alice), 100e6);
    }

    function test_commitAnytimeAndFundingContinues() public {
        vm.prank(tester);
        fund.commit(id);
        assertEq(usd.balanceOf(tester), 890e6);
        vm.prank(alice);
        vm.expectRevert("taken");
        fund.commit(id);
        fundFully();
        (uint256 pool,,,) = fund.campaigns(id);
        assertEq(pool, 100e6);
    }

    function test_submitBeforeDeadline() public {
        fundFully();
        vm.prank(tester);
        fund.commit(id);
        vm.prank(alice);
        vm.expectRevert("not your job");
        fund.submitReport(id);
        vm.warp(block.timestamp + 30 days);
        vm.prank(tester);
        fund.submitReport(id);
        assertEq(uint256(status()), uint256(TestFund.Status.Submitted));
        assertEq(usd.balanceOf(tester), 1000e6);
        vm.prank(alice);
        vm.expectRevert("closed");
        fund.contribute(id, 1e6);
    }

    function test_lateTesterIsSlashed() public {
        fundFully();
        vm.prank(tester);
        fund.commit(id);
        vm.expectRevert("not slashable");
        fund.slash(id);
        vm.warp(block.timestamp + 30 days + 1);
        vm.prank(tester);
        vm.expectRevert("deadline passed");
        fund.submitReport(id);
        fund.slash(id);
        (uint256 pool, address t,,) = fund.campaigns(id);
        assertEq(pool, 210e6);
        assertEq(t, address(0));
        assertEq(uint256(status()), uint256(TestFund.Status.Open));
        assertEq(usd.balanceOf(tester), 890e6);
    }
}
