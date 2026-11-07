pragma circom 2.2.3;

include "blake2b.circom";

// Deployed Jolt scalar challenges consume the first 16 digest bytes as LE.
template BrowserFp128Decode16() {
    signal input bytes[16];
    signal output out[2];
    component byteBits[16];
    var packed = 0;
    for (var i = 0; i < 16; i++) {
        byteBits[i] = BrowserBits(8);
        byteBits[i].in <== bytes[i];
        packed += bytes[i] * (2 ** (8 * i));
    }
    signal reduction;
    reduction <-- packed \ browser_fp128_modulus();
    reduction * (reduction - 1) === 0;
    signal reduced;
    reduced <== packed - reduction * browser_fp128_modulus();
    out[0] <-- reduced % (2 ** 64);
    out[1] <-- reduced \ (2 ** 64);
    component canonical = BrowserFp128Canonical();
    for (var i = 0; i < 2; i++) {
        canonical.in[i] <== out[i];
    }
    canonical.packed === reduced;
}

// One raw append or squeeze step, not an initialized or complete transcript.
// payloadBytes = 0 gives the squeeze hash; typed append framing is the caller's job.
template BrowserJoltDigestStep(payloadBytes) {
    assert(payloadBytes >= 0);
    signal input state[32];
    signal input counter;
    signal input payload[payloadBytes];
    signal output nextState[32];
    signal output nextCounter;
    signal output scalar[2];
    component counterBits = BrowserBits(32);
    counterBits.in <== counter;
    component nextCounterBits = BrowserBits(32);
    nextCounter <== counter + 1;
    nextCounterBits.in <== nextCounter;
    component hash = BrowserBlake2b(64 + payloadBytes, 32);
    for (var i = 0; i < 32; i++) {
        hash.in[i] <== state[i];
        if (i < 28) {
            hash.in[32 + i] <== 0;
        } else {
            var byte = 0;
            for (var j = 0; j < 8; j++) {
                byte += counterBits.bits[(31 - i) * 8 + j] * (2 ** j);
            }
            hash.in[32 + i] <== byte;
        }
    }
    for (var i = 0; i < payloadBytes; i++) {
        hash.in[64 + i] <== payload[i];
    }
    for (var i = 0; i < 32; i++) {
        nextState[i] <== hash.digest[i];
    }
    component decode = BrowserFp128Decode16();
    for (var i = 0; i < 16; i++) {
        decode.bytes[i] <== nextState[i];
    }
    for (var i = 0; i < 2; i++) {
        scalar[i] <== decode.out[i];
    }
}
