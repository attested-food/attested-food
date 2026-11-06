// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title IEurekhaProofVerifier
/// @notice One per zkVM vendor: checks a proof that the pinned eurekha-attested guest committed exactly
///         `publicValues` (the `EurekhaAttested::encode()` layout). Reverts on failure.
interface IEurekhaProofVerifier {
    function verify(bytes calldata publicValues, bytes calldata proof) external view;

    /// @notice The pinned program identity (SP1 vkey hash, OpenVM app exe commit, ...).
    function programId() external view returns (bytes32);
}
