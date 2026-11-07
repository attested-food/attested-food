pragma circom 2.2.3;

// Canonical little-endian bits, including the strict Fr modulus bound.
template CanonicalFrBits() {
    signal input in;
    signal output bits[254];
    var maximum = 21888242871839275222246405745257275088548364400416034343698204186575808495616;
    signal equal[255];
    signal less[255];
    equal[254] <== 1;
    less[254] <== 0;
    var reconstruction = 0;
    for (var i = 253; i >= 0; i--) {
        bits[i] <-- (in >> i) & 1;
        bits[i] * (bits[i] - 1) === 0;
        reconstruction += bits[i] * (2 ** i);
        if ((maximum >> i) & 1) {
            equal[i] <== equal[i + 1] * bits[i];
            less[i] <== less[i + 1] + equal[i + 1] * (1 - bits[i]);
        } else {
            equal[i] <== equal[i + 1] * (1 - bits[i]);
            less[i] <== less[i + 1];
        }
    }
    in === reconstruction;
    less[0] + equal[0] === 1;
}

// Modes match the historical AST evaluator, including byte reversal in mode 2.
template TranscriptTransform(mode) {
    assert(mode >= 0 && mode <= 3);
    signal input in;
    signal output out;
    component canonical = CanonicalFrBits();
    canonical.in <== in;
    var accumulator = 0;
    var count = mode == 0 ? 254 : (mode == 3 ? 64 : 128);
    for (var i = 0; i < count; i++) {
        var destination;
        if (mode == 0) {
            destination = (31 - (i \ 8)) * 8 + (i % 8);
        } else if (mode == 3) {
            destination = (7 - (i \ 8)) * 8 + (i % 8) + 192;
        } else {
            destination = (15 - (i \ 8)) * 8 + (i % 8);
            if (mode == 1) {
                destination += 128;
            }
        }
        accumulator += canonical.bits[i] * (2 ** destination);
    }
    out <== accumulator;
}
