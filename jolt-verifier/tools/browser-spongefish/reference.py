"""Independent hashlib replay of the inspected Spongefish 0.7.4 byte API.

Diagnostic/reference code only, never an acceptance input to a circuit.
"""

from hashlib import blake2b

P = 2**128 - 2**32 + 22537
PROTOCOL = b"akita-pcs/transcript/v1/blake2b".ljust(64, b"\0")
SESSION_DOMAIN = b"akita-pcs/session-label/v1".ljust(64, b"\0")


def h(data):
    return blake2b(data, digest_size=64).digest()


def mask(tag):
    return bytes(127) + bytes([tag])


def framed(payload):
    return len(payload).to_bytes(8, "little") + payload


def initial_frame(session_label, instance):
    return PROTOCOL + SESSION_DOMAIN + framed(session_label) + framed(instance)


def bridge_session(base_label, outer_challenge):
    if not 0 <= outer_challenge < P:
        raise ValueError("outer challenge must be canonical fp128")
    return base_label + outer_challenge.to_bytes(16, "little")


class ReferenceSponge:
    def __init__(self):
        self.cv = bytes(64)
        self.mode = "start"
        self.absorbed = b""
        self.consumed = 0

    def absorb(self, data):
        if self.mode == "squeeze":
            self.cv = h(mask(2) + self.cv + self.consumed.to_bytes(8, "big"))
            self.mode = "start"
            self.consumed = 0
        if self.mode == "start":
            self.mode = "absorb"
            self.absorbed = mask(0) + self.cv
        self.absorbed += data

    def squeeze(self, count):
        if self.mode == "absorb":
            self.cv = h(h(self.absorbed))
            self.absorbed = b""
            self.mode = "start"
        if self.mode == "start":
            self.mode = "squeeze"
            self.consumed = 0
        out = bytearray()
        while len(out) < count:
            index, offset = divmod(self.consumed, 64)
            digest = h(mask(1) + self.cv + index.to_bytes(8, "big"))
            take = min(count - len(out), 64 - offset)
            out.extend(digest[offset : offset + take])
            self.consumed += take
        return bytes(out)


class AkitaReference:
    def __init__(self, session_label, instance):
        self.sponge = ReferenceSponge()
        self.sponge.absorb(initial_frame(session_label, instance))

    def absorb(self, payload):
        self.sponge.absorb(framed(payload))

    def challenge_bytes(self, count):
        # Akita requests separate 32-byte verifier messages. Unused suffix bytes
        # of a final message are consumed even if the caller asks for fewer.
        out = bytearray()
        while len(out) < count:
            block = self.sponge.squeeze(32)
            out.extend(block[: min(count - len(out), 32)])
        return bytes(out)

    def scalar(self):
        return int.from_bytes(self.challenge_bytes(32), "little") % P
