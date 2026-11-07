pragma circom 2.2.3;

include "../browser/fp128.circom";

function browser_postcard_length_size(n) {
    var size = 1;
    while (n >= 128) {
        n = n \ 128;
        size++;
    }
    return size;
}

// Fixed-shape website IO encoding, not guest execution or proof verification.
template BrowserWebsiteStatement(TIER, INPUT_LENGTH, OUTPUT_LENGTH) {
    assert(TIER == 20 || TIER == 21 || TIER == 31 || TIER == 33);
    assert(INPUT_LENGTH >= 0 && OUTPUT_LENGTH >= 0);
    var inputPrefix = browser_postcard_length_size(INPUT_LENGTH);
    var outputPrefix = browser_postcard_length_size(OUTPUT_LENGTH);
    var inputSize = INPUT_LENGTH + inputPrefix + 2;
    var outputSize = OUTPUT_LENGTH + outputPrefix;
    assert(inputSize <= 500000);
    assert(outputSize <= 4096);

    signal input payload[INPUT_LENGTH];
    signal input result[OUTPUT_LENGTH];
    signal output inputBytes[inputSize];
    signal output outputBytes[outputSize];
    signal output vmOutputBytes[8 * ((outputSize + 7) \ 8)];
    component inputRange[INPUT_LENGTH];
    component outputRange[OUTPUT_LENGTH];

    inputBytes[0] <== TIER;
    var remaining = INPUT_LENGTH;
    for (var i = 0; i < inputPrefix; i++) {
        var continuation = 0;
        if (i + 1 < inputPrefix) { continuation = 128; }
        inputBytes[1 + i] <== (remaining % 128) + continuation;
        remaining = remaining \ 128;
    }
    for (var i = 0; i < INPUT_LENGTH; i++) {
        inputRange[i] = BrowserBits(8);
        inputRange[i].in <== payload[i];
        inputBytes[1 + inputPrefix + i] <== payload[i];
    }
    inputBytes[inputSize - 1] <== 0;

    remaining = OUTPUT_LENGTH;
    for (var i = 0; i < outputPrefix; i++) {
        var continuation = 0;
        if (i + 1 < outputPrefix) { continuation = 128; }
        outputBytes[i] <== (remaining % 128) + continuation;
        remaining = remaining \ 128;
    }
    for (var i = 0; i < OUTPUT_LENGTH; i++) {
        outputRange[i] = BrowserBits(8);
        outputRange[i].in <== result[i];
        outputBytes[outputPrefix + i] <== result[i];
    }
    for (var i = 0; i < 8 * ((outputSize + 7) \ 8); i++) {
        if (i < outputSize) {
            vmOutputBytes[i] <== outputBytes[i];
        } else {
            vmOutputBytes[i] <== 0;
        }
    }
}
