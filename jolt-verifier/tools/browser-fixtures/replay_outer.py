#!/usr/bin/env python3
"""Replay observed LegacyBlake2bTranscript operations without running upstream code."""

import argparse
import hashlib
import json
from pathlib import Path

P = 2**128 - 2**32 + 22537


def require(condition, message):
    if not condition:
        raise ValueError(message)


def replay(path):
    events = [json.loads(line) for line in path.read_text().splitlines()]
    require(bool(events), "Empty outer transcript")
    state, round_number = None, 0
    session, pending, squeezed = None, None, b""
    fields = []
    transitions = []
    counts = {}
    for index, event in enumerate(events):
        op = event["op"]
        counts[op] = counts.get(op, 0) + 1
        if op == "session":
            require(state is None and session is None, "Unexpected transcript session")
            session = bytes.fromhex(event["label_hex"])
            require(event["count"] is None, "Session count is not null")
            continue
        if op in {"label", "label_count", "u64"}:
            require(pending is None and state is not None, "Overlapping label words")
            label, count = bytes.fromhex(event["label_hex"]), event["count"]
            if op == "label":
                require(len(label) <= 32 and count is None, "Invalid label")
                pending = label.ljust(32, b"\0")
            else:
                require(
                    len(label) <= 24
                    and isinstance(count, int)
                    and 0 <= count < 2**64,
                    "Invalid label/count",
                )
                require(op != "u64" or not label, "u64 has a label")
                pending = label.ljust(24, b"\0") + count.to_bytes(8, "big")
            continue
        before = bytes.fromhex(event["state_before_hex"])
        after = bytes.fromhex(event["state_after_hex"])
        payload = bytes.fromhex(event["payload_hex"])
        raw = bytes.fromhex(event["raw_hex"])
        field = bytes.fromhex(event["field_le_hex"])
        require(len(before) == len(after) == 32, "Wrong state width")
        if op == "init":
            require(
                state is None and session is not None,
                "Duplicate/missing initialization",
            )
            require(
                before == bytes(32)
                and event["round_before"] == event["round_after"] == 0,
                "Bad initial state/counter",
            )
            require(
                payload == session.ljust(32, b"\0") and len(payload) == 32,
                "Wrong initial session padding",
            )
            require(
                after == hashlib.blake2b(payload, digest_size=32).digest(),
                "Initial Blake2b hash differs",
            )
            require(not raw and not field, "Unexpected init output")
            state = after
            continue
        require(
            state is not None
            and before == state
            and event["round_before"] == round_number,
            f"State/counter discontinuity at {index}",
        )
        if op in {"absorb", "squeeze"}:
            counter = round_number.to_bytes(32, "big")
            expected = hashlib.blake2b(
                state + counter + payload, digest_size=32
            ).digest()
            require(after == expected, f"Blake2b transition differs at {index}")
            require(
                event["round_after"] == round_number + 1,
                "Counter did not increment once",
            )
            require(not field, "Hash transition contains decoded field")
            if op == "absorb":
                require(not raw, "Absorb has raw squeeze output")
                if pending is not None:
                    require(
                        payload == pending, "Label encoding differs from absorbed word"
                    )
                    pending = None
                squeezed = b""
            else:
                require(
                    not payload and raw == after and pending is None,
                    "Wrong squeezed bytes or unresolved label",
                )
                squeezed += raw
            transitions.append(
                {
                    "event_index": index,
                    "op": op,
                    "round_before": round_number,
                    "counter_word_be_hex": counter.hex(),
                    "state_after_hex": after.hex(),
                }
            )
            state, round_number = after, round_number + 1
        elif op in {"decode_challenge", "decode_scalar", "state", "raw_bytes"}:
            require(
                after == state and event["round_after"] == round_number and not payload,
                "Observation altered state",
            )
            if op.startswith("decode_"):
                require(
                    len(raw) == len(field) == 16 and raw == squeezed[-32:][:16],
                    "Decoded challenge bytes differ",
                )
                value = int.from_bytes(raw, "little") % P
                require(
                    int.from_bytes(field, "little") == value and value < P,
                    "Challenge field decoding differs",
                )
                fields.append(
                    {
                        "event_index": index,
                        "kind": op,
                        "round": round_number,
                        "raw_hex": raw.hex(),
                        "field_le_hex": field.hex(),
                        "value_decimal": str(value),
                    }
                )
                squeezed = b""
            elif op == "raw_bytes":
                require(
                    not field and raw == squeezed[: len(raw)],
                    "Raw multi-byte output differs",
                )
                squeezed = b""
            else:
                require(not field and not raw, "Unexpected state observation bytes")
        else:
            raise ValueError(f"Unknown transcript operation: {op}")
    require(
        pending is None and state is not None and fields, "Incomplete outer capture"
    )
    nested = path.with_name("akita-transcript.tsv")
    bridge_checked = False
    if nested.exists():
        operation, encoded = nested.read_text().splitlines()[0].split("\t")
        require(operation == "session", "Nested capture does not start with session")
        expected = b"jolt-akita/precommitted-group-batch/v3" + bytes.fromhex(
            fields[-1]["field_le_hex"]
        )
        require(bytes.fromhex(encoded) == expected, "Outer-to-Akita bridge differs")
        bridge_checked = True
    return {
        "schema": "website-jolt-outer-replay-v1",
        "nested_bridge_checked": bridge_checked,
        "hash": "blake2b-256",
        "field_modulus": str(P),
        "events": len(events),
        "operation_counts": counts,
        "rounds": round_number,
        "final_state_hex": state.hex(),
        "replayed_all_transitions": True,
        "fields": fields,
        "transitions": transitions,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    print(json.dumps(replay(args.trace), indent=2, sort_keys=True))
