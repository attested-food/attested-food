// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title EurekhaPublicValues
/// @notice Decoder for `EurekhaAttested::encode()` (backend2-rs/core/src/eurekha.rs), header-signer form:
///         `0x01 | header (u64-LE-length-prefixed) | session_time u64 LE | server_name (u64-LE-length-prefixed)
///         | key_sha256 | body_commitment | pdf_len u32 LE | redacted_sha256 | spans (u32 count, u32 LE pairs)
///         | kv (u32 count, length-prefixed key, value) | rows (u32 count, 8 length-prefixed strings each)`.
///         Integers are little-endian; strings are u64-LE-length-prefixed UTF-8.
library EurekhaPublicValues {
    struct Head {
        bytes header;
        uint64 sessionTime;
        string serverName;
        bytes32 keySha256;
        bytes32 bodyCommitment;
        uint32 pdfLen;
        bytes32 redactedSha256;
        /// @notice Offset of the span list in the encoding.
        uint256 spansAt;
    }

    struct KeyValue {
        string key;
        string value;
    }

    struct Row {
        string discipline;
        string group;
        string parameter;
        string unit;
        string method;
        string result;
        string rda;
        string rdaPct;
    }

    error Truncated();
    error NotHeaderSigned();

    function head(bytes calldata pv) internal pure returns (Head memory h) {
        if (pv.length < 1 || pv[0] != 0x01) revert NotHeaderSigned();
        uint256 at = 1;
        (h.header, at) = readBytes(pv, at);
        (h.sessionTime, at) = readU64(pv, at);
        bytes memory name;
        (name, at) = readBytes(pv, at);
        h.serverName = string(name);
        (h.keySha256, at) = readB32(pv, at);
        (h.bodyCommitment, at) = readB32(pv, at);
        (h.pdfLen, at) = readU32(pv, at);
        (h.redactedSha256, at) = readB32(pv, at);
        h.spansAt = at;
    }

    /// @notice Redaction spans, every key-value pair and result row (view helper; not used by `submit`).
    function body(bytes calldata pv)
        internal
        pure
        returns (uint32[2][] memory spans, KeyValue[] memory kv, Row[] memory rows)
    {
        uint256 at = head(pv).spansAt;
        uint32 n;
        (n, at) = readU32(pv, at);
        spans = new uint32[2][](n);
        for (uint256 i; i < n; i++) {
            (spans[i][0], at) = readU32(pv, at);
            (spans[i][1], at) = readU32(pv, at);
        }
        (n, at) = readU32(pv, at);
        kv = new KeyValue[](n);
        for (uint256 i; i < n; i++) {
            (kv[i].key, at) = readString(pv, at);
            (kv[i].value, at) = readString(pv, at);
        }
        (n, at) = readU32(pv, at);
        rows = new Row[](n);
        for (uint256 i; i < n; i++) {
            Row memory r = rows[i];
            (r.discipline, at) = readString(pv, at);
            (r.group, at) = readString(pv, at);
            (r.parameter, at) = readString(pv, at);
            (r.unit, at) = readString(pv, at);
            (r.method, at) = readString(pv, at);
            (r.result, at) = readString(pv, at);
            (r.rda, at) = readString(pv, at);
            (r.rdaPct, at) = readString(pv, at);
        }
        if (at != pv.length) revert Truncated();
    }

    function readLE(bytes calldata pv, uint256 at, uint256 len) private pure returns (uint64 v, uint256 next) {
        if (at + len > pv.length) revert Truncated();
        uint256 acc = 0;
        for (uint256 i; i < len; i++) {
            acc |= uint256(uint8(pv[at + i])) << (8 * i);
        }
        // casting to 'uint64' is safe because len is at most 8
        // forge-lint: disable-next-line(unsafe-typecast)
        v = uint64(acc);
        next = at + len;
    }

    function readU32(bytes calldata pv, uint256 at) private pure returns (uint32, uint256) {
        (uint64 v, uint256 next) = readLE(pv, at, 4);
        // casting to 'uint32' is safe because readLE read exactly 4 bytes
        // forge-lint: disable-next-line(unsafe-typecast)
        return (uint32(v), next);
    }

    function readU64(bytes calldata pv, uint256 at) private pure returns (uint64, uint256) {
        return readLE(pv, at, 8);
    }

    function readB32(bytes calldata pv, uint256 at) private pure returns (bytes32 v, uint256 next) {
        if (at + 32 > pv.length) revert Truncated();
        v = bytes32(pv[at:at + 32]);
        next = at + 32;
    }

    function readBytes(bytes calldata pv, uint256 at) private pure returns (bytes memory v, uint256 next) {
        uint64 n;
        (n, at) = readU64(pv, at);
        if (at + n > pv.length) revert Truncated();
        v = pv[at:at + n];
        next = at + n;
    }

    function readString(bytes calldata pv, uint256 at) private pure returns (string memory, uint256) {
        (bytes memory b, uint256 next) = readBytes(pv, at);
        return (string(b), next);
    }
}
