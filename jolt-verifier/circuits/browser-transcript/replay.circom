pragma circom 2.2.3;

include "../browser/jolt_digest.circom";

function browser_jolt_replay_size(n, sizes) {
    var total = 0;
    for (var i = 0; i < n; i++) { total += sizes[i]; }
    return total;
}

function browser_jolt_replay_challenges(n, squeezes) {
    var total = 0;
    for (var i = 0; i < n; i++) { total += squeezes[i]; }
    return total;
}

// The protocol wrapper fixes the operation schedule and binds every payload.
template BrowserJoltReplay(N, SIZES, SQUEEZES) {
    assert(N >= 0 && N < 2 ** 32);
    for (var i = 0; i < N; i++) {
        assert(SIZES[i] >= 0);
        assert(SQUEEZES[i] == 0 || SQUEEZES[i] == 1);
        if (SQUEEZES[i] == 1) { assert(SIZES[i] == 0); }
    }
    signal input payload[browser_jolt_replay_size(N, SIZES)];
    signal output states[N + 1][32];
    signal output challenges[browser_jolt_replay_challenges(N, SQUEEZES)][2];
    // BLAKE2b-256 of the fixed 32-byte Jolt label word.
    var initial[32] = [
        6, 206, 44, 16, 209, 210, 128, 28,
        72, 200, 89, 215, 203, 22, 81, 4,
        118, 176, 212, 134, 103, 217, 86, 46,
        208, 33, 178, 13, 154, 5, 229, 71
    ];
    for (var i = 0; i < 32; i++) { states[0][i] <== initial[i]; }
    component hashes[N];
    component decoders[browser_jolt_replay_challenges(N, SQUEEZES)];
    var offset = 0;
    var challengeIndex = 0;
    for (var i = 0; i < N; i++) {
        hashes[i] = BrowserBlake2b(64 + SIZES[i], 32);
        for (var j = 0; j < 32; j++) {
            hashes[i].in[j] <== states[i][j];
            if (j < 28) { hashes[i].in[32 + j] <== 0; }
            else { hashes[i].in[32 + j] <== (i >> (8 * (31 - j))) & 255; }
        }
        for (var j = 0; j < SIZES[i]; j++) {
            hashes[i].in[64 + j] <== payload[offset + j];
        }
        for (var j = 0; j < 32; j++) {
            states[i + 1][j] <== hashes[i].digest[j];
        }
        if (SQUEEZES[i] == 1) {
            decoders[challengeIndex] = BrowserFp128Decode16();
            for (var j = 0; j < 16; j++) {
                decoders[challengeIndex].bytes[j] <== states[i + 1][j];
            }
            for (var j = 0; j < 2; j++) {
                challenges[challengeIndex][j] <== decoders[challengeIndex].out[j];
            }
            challengeIndex++;
        }
        offset += SIZES[i];
    }
}

// Canonical field absorption is BE, unlike the LE challenge decoder.
template BrowserJoltFieldMessage() {
    signal input limbs[2];
    signal output bytes[16];
    component canonical = BrowserFp128Canonical();
    component ranges[2];
    for (var i = 0; i < 2; i++) {
        canonical.in[i] <== limbs[i];
        ranges[i] = BrowserBits(64);
        ranges[i].in <== limbs[i];
    }
    for (var i = 0; i < 16; i++) {
        var value = 0;
        for (var j = 0; j < 8; j++) {
            value += ranges[(15 - i) \ 8].bits[((15 - i) % 8) * 8 + j] * (2 ** j);
        }
        bytes[i] <== value;
    }
}

// HAS_COUNT selects LabelWithCount; otherwise count must be zero.
template BrowserJoltLabelMessage(LENGTH, LABEL, HAS_COUNT) {
    assert(HAS_COUNT == 0 || HAS_COUNT == 1);
    assert(LENGTH >= 0 && LENGTH <= 32 - 8 * HAS_COUNT);
    signal input count;
    signal output bytes[32];
    component countBits = BrowserBits(64);
    countBits.in <== count;
    if (HAS_COUNT == 0) { count === 0; }
    for (var i = 0; i < 32; i++) {
        if (i < LENGTH) {
            assert(LABEL[i] >= 0 && LABEL[i] < 256);
            bytes[i] <== LABEL[i];
        } else if (HAS_COUNT == 1 && i >= 24) {
            var value = 0;
            for (var j = 0; j < 8; j++) {
                value += countBits.bits[(31 - i) * 8 + j] * (2 ** j);
            }
            bytes[i] <== value;
        } else {
            bytes[i] <== 0;
        }
    }
}
