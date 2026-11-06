// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IEurekhaProofVerifier} from "./IEurekhaProofVerifier.sol";
import {EurekhaPublicValues} from "./EurekhaPublicValues.sol";

/// @title EurekhaReportRegistry
/// @notice Records Eurekha Labs reports proven by backend2-rs (`format=eurekha-attested`): one zkVM proof that a
///         TLSNotary-attested GET to the lab's S3 bucket returned a PDF whose redaction (customer fields zeroed)
///         hashes to `redactedSha256` and whose non-customer key-value pairs and result rows are the committed
///         ones. The guest checks every attestation leaf against the BCS attestation header and commits that
///         header; this contract checks the rest:
///         - the vendor proof of the pinned guest (SP1 Groth16, ...);
///         - the notary's secp256k1 signature over `keccak256(header)` (`ecrecover`), notary address pinned;
///         - the attested server name is the lab's bucket.
///         The object key (the link to the unredacted original) is only committed as `keySha256`.
contract EurekhaReportRegistry {
    struct Report {
        bytes32 backend;
        bytes32 keySha256;
        bytes32 redactedSha256;
        bytes32 bodyCommitment;
        uint64 sessionTime;
        uint32 pdfLen;
        address submitter;
    }

    address public immutable notary;
    /// @notice keccak256 of the accepted bucket host, e.g. "eurekhalabs.s3.amazonaws.com".
    bytes32 public immutable serverNameHash;
    address public owner;

    /// @notice Vendor verifiers by backend name (bytes32("sp1"), ...). Add-only.
    mapping(bytes32 => IEurekhaProofVerifier) public verifiers;

    uint256 public reportCount;
    mapping(uint256 => Report) public reports;
    /// @notice keccak256(publicValues) => recorded (the same values cannot be recorded twice).
    mapping(bytes32 => bool) public seen;
    /// @notice keySha256 => report ids (one S3 object can be attested again later).
    mapping(bytes32 => uint256[]) internal byKey;

    event VerifierAdded(bytes32 indexed backend, address verifier, bytes32 programId);
    event ReportAttested(
        uint256 indexed id,
        bytes32 indexed keySha256,
        bytes32 indexed redactedSha256,
        bytes32 backend,
        address submitter
    );

    error NotOwner();
    error UnknownBackend(bytes32 backend);
    error VerifierExists(bytes32 backend);
    error BadNotarySignature();
    error BadServerName();
    error AlreadyAttested(bytes32 digest);
    error ZeroNotary();

    constructor(address _notary, string memory _serverName) {
        if (_notary == address(0)) revert ZeroNotary();
        notary = _notary;
        serverNameHash = keccak256(bytes(_serverName));
        owner = msg.sender;
    }

    function addVerifier(bytes32 backend, IEurekhaProofVerifier verifier) external {
        if (msg.sender != owner) revert NotOwner();
        if (address(verifiers[backend]) != address(0)) revert VerifierExists(backend);
        verifiers[backend] = verifier;
        emit VerifierAdded(backend, address(verifier), verifier.programId());
    }

    /// @notice Every check `submit` makes, without recording. Reverts on failure.
    function check(bytes32 backend, bytes calldata publicValues, bytes calldata proof, bytes calldata notarySignature)
        public
        view
        returns (EurekhaPublicValues.Head memory h)
    {
        IEurekhaProofVerifier v = verifiers[backend];
        if (address(v) == address(0)) revert UnknownBackend(backend);
        v.verify(publicValues, proof);
        h = EurekhaPublicValues.head(publicValues);
        if (recover(keccak256(h.header), notarySignature) != notary) revert BadNotarySignature();
        if (keccak256(bytes(h.serverName)) != serverNameHash) revert BadServerName();
    }

    /// @notice Verify and record a report. `publicValues`, `proof` and `notarySignature` are the
    ///         `publicValues`, `proof` and `notarySignature` of a backend2-rs EVM artifact.
    function submit(bytes32 backend, bytes calldata publicValues, bytes calldata proof, bytes calldata notarySignature)
        external
        returns (uint256 id)
    {
        bytes32 digest = keccak256(publicValues);
        if (seen[digest]) revert AlreadyAttested(digest);
        EurekhaPublicValues.Head memory h = check(backend, publicValues, proof, notarySignature);
        seen[digest] = true;
        id = ++reportCount;
        reports[id] = Report({
            backend: backend,
            keySha256: h.keySha256,
            redactedSha256: h.redactedSha256,
            bodyCommitment: h.bodyCommitment,
            sessionTime: h.sessionTime,
            pdfLen: h.pdfLen,
            submitter: msg.sender
        });
        byKey[h.keySha256].push(id);
        emit ReportAttested(id, h.keySha256, h.redactedSha256, backend, msg.sender);
    }

    function reportsForKey(bytes32 keySha256) external view returns (uint256[] memory) {
        return byKey[keySha256];
    }

    /// @notice Redaction spans, key-value pairs and result rows of committed public values.
    function decode(bytes calldata publicValues)
        external
        pure
        returns (
            EurekhaPublicValues.Head memory h,
            uint32[2][] memory spans,
            EurekhaPublicValues.KeyValue[] memory kv,
            EurekhaPublicValues.Row[] memory rows
        )
    {
        h = EurekhaPublicValues.head(publicValues);
        (spans, kv, rows) = EurekhaPublicValues.body(publicValues);
    }

    /// @dev 65-byte `r || s || v` (v 0/1 or 27/28), as the tlsn secp256k1eth signer emits it.
    function recover(bytes32 digest, bytes calldata sig) internal pure returns (address) {
        if (sig.length != 65) return address(0);
        bytes32 r = bytes32(sig[0:32]);
        bytes32 s = bytes32(sig[32:64]);
        uint8 v = uint8(sig[64]);
        if (v < 27) v += 27;
        return ecrecover(digest, v, r, s);
    }
}
