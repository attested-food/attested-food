#!/usr/bin/env python3
"""Generate public SHA and unsigned synthetic TLSNotary tier inputs, without secrets."""

import argparse
import hashlib
from pathlib import Path
import struct


def varint(n):
    out = bytearray()
    while n >= 128:
        out.append((n & 127) | 128)
        n >>= 7
    return bytes(out + bytes([n]))


def vector(value):
    return varint(len(value)) + value


def leaf(domain, value):
    return hashlib.sha256(bytes.fromhex(domain) + value).digest()


def merkle(leaves):
    while len(leaves) > 1:
        leaves = [
            hashlib.sha256(leaves[i] + leaves[i + 1]).digest()
            if i + 1 < len(leaves)
            else leaves[i]
            for i in range(0, len(leaves), 2)
        ]
    return leaves[0]


def tls_input():
    # All openings are public fixture constants, not a real TLS session or signature.
    host = b"eurekhalabs.s3.amazonaws.com"
    parts = [
        b"GET ",
        b"/public-synthetic-fixture.pdf",
        b" HTTP/1.1\r\nHost: " + host + b"\r\n\r\n",
    ]
    request = b"".join(parts)
    blinders = [bytes([i]) * 16 for i in range(3)]
    commitment = hashlib.sha256(b"public synthetic body" + bytes(16)).digest()
    pdf_len = len(b"public synthetic body")

    def preimage(direction, start, end, digest):
        return (
            b"\x00"
            + bytes([direction])
            + b"\x01"
            + struct.pack("<QQ", start, end)
            + b"\x01\x20"
            + digest
        )

    ext = vector(b"equinox.server_name") + vector(host)
    body = preimage(1, 0, pdf_len, commitment)
    conn = (
        struct.pack("<Q", 1800000000)
        + b"\x00"
        + struct.pack("<II", len(request), pdf_len)
    )
    sent = []
    offset = 0
    for part, blinder in zip(parts, blinders):
        sent.append(
            preimage(
                0, offset, offset + len(part), hashlib.sha256(part + blinder).digest()
            )
        )
        offset += len(part)
    leaves = [
        leaf("67ed567f312ca482b9f365cc271baa42", ext),
        leaf("bd0ab9ac6ea93ebda2500e8769e63a9e", body),
        leaf("6e317487904af460f6bba793610c9961", conn),
    ]
    leaves += [leaf("bd0ab9ac6ea93ebda2500e8769e63a9e", value) for value in sent]
    header = b"PUBLIC SYNTHETIC UNSIGNED FIXTURE" + b"\x01\x20" + merkle(leaves)
    tls = (
        vector(header)
        + vector(b"")
        + varint(len(leaves))
        + b"".join(leaves)
        + varint(0)
        + vector(ext)
        + varint(1)
        + vector(body)
    )
    req = (
        varint(2)
        + vector(conn)
        + varint(3)
        + b"".join(varint(i) for i in [3, 4, 5])
        + varint(3)
        + b"".join(vector(pre) for pre in sent)
    )
    secret = vector(request) + varint(3) + b"".join(blinders)
    aux = tls + req + secret
    return struct.pack("<I", len(aux)) + aux + commitment + struct.pack("<Q", pdf_len)


def generate(directory):
    directory.mkdir(parents=True, exist_ok=True)
    iv = struct.pack(
        "<8I",
        0x6A09E667,
        0xBB67AE85,
        0x3C6EF372,
        0xA54FF53A,
        0x510E527F,
        0x9B05688C,
        0x1F83D9AB,
        0x5BE0CD19,
    )
    for name, value in {
        "tier20-empty": iv,
        "tier20-zero-block": iv + bytes(64),
        "tier21-abc": iv + struct.pack("<Q", 3) + b"abc",
        "tier21-def": iv + struct.pack("<Q", 3) + b"def",
        "tier33-synthetic-unsigned": tls_input(),
    }.items():
        (directory / (name + ".bin")).write_bytes(value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    generate(parser.parse_args().output)
