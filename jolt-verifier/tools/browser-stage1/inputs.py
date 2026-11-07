"""Export serialized stage-1 data, optionally matched to an outer native capture.

This does not authenticate the transcript, openings, or complete Jolt proof.
"""

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from reference import P, limbs

OPENING_NAMES = (
    "left_instruction_input",
    "right_instruction_input",
    "product",
    "should_branch",
    "pc",
    "unexpanded_pc",
    "imm",
    "ram_address",
    "rs1_value",
    "rs2_value",
    "rd_write_value",
    "ram_read_value",
    "ram_write_value",
    "left_lookup_operand",
    "right_lookup_operand",
    "next_unexpanded_pc",
    "next_pc",
    "next_is_virtual",
    "next_is_first_in_sequence",
    "lookup_output",
    "should_jump",
    "add_operands",
    "subtract_operands",
    "multiply_operands",
    "load",
    "store",
    "jump",
    "write_lookup_output_to_rd",
    "virtual_instruction",
    "assert",
    "do_not_update_unexpanded_pc",
    "advice",
    "is_compressed",
    "is_first_in_sequence",
    "is_last_in_sequence",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scalar(value):
    require(
        isinstance(value, list)
        and len(value) == 16
        and all(type(x) is int and 0 <= x <= 255 for x in value),
        "expected 16 little-endian field bytes",
    )
    result = int.from_bytes(bytes(value), "little")
    require(result < P, "noncanonical serialized Fp128")
    return result


@dataclass(frozen=True)
class Stage1Wire:
    log_t: int
    coefficients: tuple
    compressed: tuple
    uniskip_output: int
    openings: tuple

    def proof_inputs(self):
        return {
            "uniskipCoefficients": list(map(limbs, self.coefficients)),
            "uniskipOutputClaim": limbs(self.uniskip_output),
            "compressed": [[limbs(c) for c in p] for p in self.compressed],
            "openings": list(map(limbs, self.openings)),
        }


def parse_proof(proof):
    require(
        proof["protocol"]
        == {
            "zk": "Transparent",
            "commitment": "Packed",
            "scalar_challenge_endianness": "Little",
        },
        "wrong website protocol",
    )
    trace = proof["trace_length"]
    require(
        type(trace) is int and 1 <= trace <= 2**21 and trace & (trace - 1) == 0,
        "invalid trace length",
    )
    log_t = trace.bit_length() - 1
    stages = proof["stages"]
    rounds = stages["stage1_uni_skip_first_round_proof"]["Clear"]["Full"][
        "round_polynomials"
    ]
    require(len(rounds) == 1, "expected exactly one full uni-skip round")
    coefficients = tuple(map(scalar, rounds[0]["coefficients"]))
    require(len(coefficients) <= 28, "uni-skip degree exceeds 27")
    compressed_rounds = stages["stage1_sumcheck_proof"]["Clear"]["Compressed"][
        "round_polynomials"
    ]
    require(len(compressed_rounds) == log_t + 1, "wrong remainder round count")
    compressed = tuple(
        tuple(map(scalar, p["coeffs_except_linear_term"])) for p in compressed_rounds
    )
    require(all(len(p) == 3 for p in compressed), "expected fixed cubic wire shape")
    claims = proof["claims"]["Clear"]["stage1"]
    openings = claims["outer"]["outer_remainder"]
    require(set(openings) == set(OPENING_NAMES), "wrong rv64 opening layout")
    return Stage1Wire(
        log_t,
        coefficients,
        compressed,
        scalar(claims["uniskip_output_claim"]),
        tuple(scalar(openings[name]) for name in OPENING_NAMES),
    )


class CaptureCursor:
    def __init__(self, events, index):
        self.events, self.index = events, index

    def take(self, op):
        require(self.index < len(self.events), "truncated stage-1 capture")
        event = self.events[self.index]
        self.index += 1
        require(event["op"] == op, f"expected {op} at capture event {self.index - 1}")
        return event

    def absorb(self, payload):
        event = self.take("absorb")
        require(
            bytes.fromhex(event["payload_hex"]) == payload,
            "serialized proof differs from captured absorption",
        )

    def label(self, label, count=None):
        event = self.take("label" if count is None else "label_count")
        require(
            bytes.fromhex(event["label_hex"]) == label and event["count"] == count,
            "wrong stage-1 capture label/count",
        )
        self.absorb(
            label.ljust(24, b"\0") + count.to_bytes(8, "big")
            if count is not None
            else label.ljust(32, b"\0")
        )

    def challenge(self, kind):
        squeezed = self.take("squeeze")
        event = self.take(kind)
        raw = bytes.fromhex(event["raw_hex"])
        encoded = bytes.fromhex(event["field_le_hex"])
        require(
            len(raw) == len(encoded) == 16
            and raw == bytes.fromhex(squeezed["raw_hex"])[:16],
            "challenge bytes differ from squeeze",
        )
        value = int.from_bytes(raw, "little") % P
        require(int.from_bytes(encoded, "little") == value, "wrong challenge decoding")
        return value

    def polynomial(self, label, coefficients):
        self.label(label, len(coefficients))
        for coefficient in coefficients:
            self.absorb(coefficient.to_bytes(16, "big"))
        return self.challenge("decode_challenge")

    def claim(self, label, value):
        self.label(label)
        self.absorb(value.to_bytes(16, "big"))


def capture_inputs(wire, events):
    starts = [
        i
        for i, e in enumerate(events)
        if e["op"] == "label_count" and bytes.fromhex(e["label_hex"]) == b"uniskip_poly"
    ]
    require(starts, "missing uni-skip capture")
    start = starts[0]
    # Stage 0 draws no field challenges; the first contiguous draws are stage-1 tau.
    prefix = events[:start]
    decoded = [e for e in prefix if e["op"] in {"decode_challenge", "decode_scalar"}]
    require(len(decoded) == wire.log_t + 2, "wrong stage-1 tau draw count")
    tau_cursor = CaptureCursor(events, start - 2 * len(decoded))
    tau = [tau_cursor.challenge("decode_challenge") for _ in decoded]
    require(tau_cursor.index == start, "noncontiguous tau capture")
    cursor = CaptureCursor(events, start)
    challenge = cursor.polynomial(b"uniskip_poly", wire.coefficients)
    cursor.claim(b"opening_claim", wire.uniskip_output)
    cursor.claim(b"sumcheck_claim", wire.uniskip_output)
    coefficient = cursor.challenge("decode_scalar")
    remainder = [cursor.polynomial(b"sumcheck_poly", p) for p in wire.compressed]
    for opening in wire.openings:
        cursor.claim(b"opening_claim", opening)
    return {
        **wire.proof_inputs(),
        "tau": list(map(limbs, tau)),
        "uniskipChallenge": limbs(challenge),
        "batchingCoefficient": limbs(coefficient),
        "remainderChallenges": list(map(limbs, remainder)),
    }


def export(proof_path, trace_path=None):
    raw = proof_path.read_bytes()
    wire = parse_proof(json.loads(raw))
    inputs = wire.proof_inputs()
    if trace_path is not None:
        events = [json.loads(line) for line in trace_path.read_text().splitlines()]
        inputs = capture_inputs(wire, events)
    return {
        "schema": "website-stage1-scalar-inputs-v1",
        "complete_proof_verification": False,
        "transcript_constraints_connected": False,
        "proof_json_sha256": hashlib.sha256(raw).hexdigest(),
        "capture_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest()
        if trace_path
        else None,
        "shape": {
            "LOG_T": wire.log_t,
            "L": len(wire.coefficients),
            "stored_per_round": 3,
        },
        "missing_inputs": []
        if trace_path
        else ["tau", "uniskipChallenge", "batchingCoefficient", "remainderChallenges"],
        "inputs": inputs,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proof", type=Path)
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.proof, args.trace), indent=2, sort_keys=True))
