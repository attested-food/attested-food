pragma circom 2.2.3;

include "../browser/blake2b.circom";

// Hash(mask_tag[128] || cv[64] || suffix), not an entire transcript transition.
template SpongefishCVHash(tag, suffixBytes) {
    assert(tag >= 0 && tag <= 2);
    assert(suffixBytes >= 0);
    signal input cv[64];
    signal input suffix[suffixBytes];
    signal output out[64];
    component hash = BrowserBlake2b(192 + suffixBytes, 64);
    for (var i = 0; i < 128; i++) {
        hash.in[i] <== i == 127 ? tag : 0;
    }
    for (var i = 0; i < 64; i++) {
        hash.in[128 + i] <== cv[i];
    }
    for (var i = 0; i < suffixBytes; i++) {
        hash.in[192 + i] <== suffix[i];
    }
    for (var i = 0; i < 64; i++) {
        out[i] <== hash.digest[i];
    }
}

// Complete an active absorb phase when squeezing next: H(H(mask_0 || cv || data)).
// All consecutive absorbed frames belong to data; do not finish between frames.
template SpongefishFinishAbsorb(absorbedBytes) {
    signal input cv[64];
    signal input data[absorbedBytes];
    signal output nextCV[64];
    component inner = SpongefishCVHash(0, absorbedBytes);
    for (var i = 0; i < 64; i++) {
        inner.cv[i] <== cv[i];
    }
    for (var i = 0; i < absorbedBytes; i++) {
        inner.suffix[i] <== data[i];
    }
    component outer = BrowserBlake2b(64, 64);
    for (var i = 0; i < 64; i++) {
        outer.in[i] <== inner.out[i];
    }
    for (var i = 0; i < 64; i++) {
        nextCV[i] <== outer.digest[i];
    }
}

// tag 1: counter is the squeeze block index. tag 2: counter is consumed bytes.
// The enclosing fixed-shape replay must constrain this counter's progression.
template SpongefishCounterHash(tag) {
    assert(tag == 1 || tag == 2);
    signal input cv[64];
    signal input counter;
    signal output out[64];
    component counterBits = BrowserBits(64);
    counterBits.in <== counter;
    component hash = SpongefishCVHash(tag, 8);
    for (var i = 0; i < 64; i++) {
        hash.cv[i] <== cv[i];
    }
    for (var i = 0; i < 8; i++) {
        var value = 0;
        for (var j = 0; j < 8; j++) {
            value += counterBits.bits[(7 - i) * 8 + j] * (2 ** j);
        }
        hash.suffix[i] <== value;
    }
    for (var i = 0; i < 64; i++) {
        out[i] <== hash.out[i];
    }
}

// Akita's production absorb encoding: u64_le(length) || payload.
template AkitaAbsorbFrame(payloadBytes) {
    assert(payloadBytes >= 0 && payloadBytes < 2 ** 64);
    signal input payload[payloadBytes];
    signal output frame[8 + payloadBytes];
    component byteBits[payloadBytes];
    for (var i = 0; i < 8; i++) {
        frame[i] <== (payloadBytes >> (8 * i)) & 255;
    }
    for (var i = 0; i < payloadBytes; i++) {
        byteBits[i] = BrowserBits(8);
        byteBits[i].in <== payload[i];
        frame[8 + i] <== payload[i];
    }
}

// Initial absorb stream, including the canonical outer Jolt challenge bridge.
// baseLabel and instance must be bound to the exact PCS statement by the caller.
template AkitaBridgedPreamble(baseLabelBytes, instanceBytes) {
    assert(baseLabelBytes >= 0 && baseLabelBytes < 2 ** 64 - 16);
    assert(instanceBytes >= 0 && instanceBytes < 2 ** 64);
    signal input baseLabel[baseLabelBytes];
    signal input outerChallenge[2];
    signal input instance[instanceBytes];
    signal output frame[160 + baseLabelBytes + instanceBytes];
    var protocol[31] = [97,107,105,116,97,45,112,99,115,47,116,114,97,110,115,99,114,105,112,116,47,118,49,47,98,108,97,107,101,50,98];
    var domain[26] = [97,107,105,116,97,45,112,99,115,47,115,101,115,115,105,111,110,45,108,97,98,101,108,47,118,49];
    // The session domain is "akita-pcs/session-label/v1" (26 bytes).
    for (var i = 0; i < 64; i++) {
        if (i < 31) {
            frame[i] <== protocol[i];
        } else {
            frame[i] <== 0;
        }
        if (i < 26) {
            frame[64 + i] <== domain[i];
        } else {
            frame[64 + i] <== 0;
        }
    }
    component canonical = BrowserFp128Canonical();
    component challengeBits[2];
    for (var i = 0; i < 2; i++) {
        canonical.in[i] <== outerChallenge[i];
        challengeBits[i] = BrowserBits(64);
        challengeBits[i].in <== outerChallenge[i];
    }
    component label = AkitaAbsorbFrame(baseLabelBytes + 16);
    component descriptor = AkitaAbsorbFrame(instanceBytes);
    for (var i = 0; i < baseLabelBytes; i++) {
        label.payload[i] <== baseLabel[i];
    }
    for (var i = 0; i < 16; i++) {
        var value = 0;
        for (var j = 0; j < 8; j++) {
            value += challengeBits[i \ 8].bits[(i % 8) * 8 + j] * (2 ** j);
        }
        label.payload[baseLabelBytes + i] <== value;
    }
    for (var i = 0; i < instanceBytes; i++) {
        descriptor.payload[i] <== instance[i];
    }
    for (var i = 0; i < 24 + baseLabelBytes; i++) {
        frame[128 + i] <== label.frame[i];
    }
    for (var i = 0; i < 8 + instanceBytes; i++) {
        frame[152 + baseLabelBytes + i] <== descriptor.frame[i];
    }
}

// Reduce 32 LE challenge bytes without ever forming a 256-bit native Fr value.
template AkitaDecode32() {
    signal input bytes[32];
    signal output out[2];
    component byteBits[32];
    var lo = 0;
    var hi = 0;
    for (var i = 0; i < 32; i++) {
        byteBits[i] = BrowserBits(8);
        byteBits[i].in <== bytes[i];
        if (i < 16) {
            lo += bytes[i] * (2 ** (8 * i));
        } else {
            hi += bytes[i] * (2 ** (8 * (i - 16)));
        }
    }
    signal folded;
    folded <== lo + hi * (2 ** 32 - 22537);
    signal quotient;
    quotient <-- folded \ browser_fp128_modulus();
    component quotientBits = BrowserBits(32);
    quotientBits.in <== quotient;
    signal reduced;
    reduced <== folded - quotient * browser_fp128_modulus();
    out[0] <-- reduced % (2 ** 64);
    out[1] <-- reduced \ (2 ** 64);
    component canonical = BrowserFp128Canonical();
    for (var i = 0; i < 2; i++) {
        canonical.in[i] <== out[i];
    }
    canonical.packed === reduced;
}
