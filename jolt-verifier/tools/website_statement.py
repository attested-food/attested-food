"""Reference codec for the website guest's IO, not a Jolt proof verifier.

The fork concatenates postcard(tier), postcard(buf), postcard(labels). The
website always supplies an empty labels list. Guest outputs are postcard Vec<u8>.
These checks must also be enforced in the eventual verifier circuit.
"""

from dataclasses import dataclass

ALLOWED_TIERS = frozenset((20, 21, 31, 33))
MAX_INPUT_SIZE = 500000
MAX_OUTPUT_SIZE = 4096


def encode_length(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Expected a nonnegative integer length")
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def decode_length(data, offset, maximum):
    start = offset
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if value > maximum:
            raise ValueError("Length exceeds the approved bound")
        if byte < 128:
            if data[start:offset] != encode_length(value):
                raise ValueError("Noncanonical postcard length")
            return value, offset
        shift += 7
        if shift > maximum.bit_length() + 7:
            raise ValueError("Unterminated postcard length")
    raise ValueError("Truncated postcard length")


@dataclass(frozen=True)
class GuestInput:
    tier: int
    payload: bytes


def encode_guest_input(tier, payload):
    if isinstance(tier, bool) or not isinstance(tier, int) or tier not in ALLOWED_TIERS:
        raise ValueError("Tier is not used by the website Jolt prover")
    if not isinstance(payload, bytes):
        raise ValueError("Guest payload must be bytes")
    result = bytes((tier,)) + encode_length(len(payload)) + payload + b"\x00"
    if len(result) > MAX_INPUT_SIZE:
        raise ValueError("Encoded guest input exceeds the website memory layout")
    return result


def decode_guest_input(data):
    if not isinstance(data, bytes) or not data or len(data) > MAX_INPUT_SIZE:
        raise ValueError("Invalid encoded guest input size")
    tier = data[0]
    if tier not in ALLOWED_TIERS:
        raise ValueError("Tier is not used by the website Jolt prover")
    length, start = decode_length(data, 1, MAX_INPUT_SIZE)
    end = start + length
    if end > len(data):
        raise ValueError("Truncated guest payload")
    if data[end:] != b"\x00":
        raise ValueError("Expected exactly the website's empty labels list")
    return GuestInput(tier, data[start:end])


def encode_guest_output(payload):
    if not isinstance(payload, bytes):
        raise ValueError("Guest output must be bytes")
    result = encode_length(len(payload)) + payload
    if len(result) > MAX_OUTPUT_SIZE:
        raise ValueError("Encoded output exceeds the website memory layout")
    return result


def decode_guest_output(data):
    if not isinstance(data, bytes) or not data or len(data) > MAX_OUTPUT_SIZE:
        raise ValueError("Invalid encoded output size")
    length, start = decode_length(data, 0, MAX_OUTPUT_SIZE)
    if start + length != len(data):
        raise ValueError("Truncated output or trailing bytes")
    return data[start:]
