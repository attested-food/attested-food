pragma circom 2.2.3;

include "stage1.circom";

function browser_stage1_power_sums() {
    var sums[28];
    for (var k = 0; k < 28; k++) {
        sums[k] = 0;
        for (var node = -4; node <= 5; node++) {
            sums[k] += node ** k;
        }
    }
    return sums;
}

// Full coefficients, not compressed. The native centered-domain input is zero.
template BrowserStage1Uniskip(L) {
    assert(L >= 0 && L <= 28);
    signal input coefficients[L][2];
    signal input challenge[2];
    signal input outputClaim[2];
    signal output out[2];
    var sums[28] = browser_stage1_power_sums();
    component canonicalChallenge = BrowserFp128Canonical();
    canonicalChallenge.in <== challenge;
    component canonicalOutput = BrowserFp128Canonical();
    canonicalOutput.in <== outputClaim;
    component roundSum = BrowserSumcheckWeightedSum(L);
    roundSum.values <== coefficients;
    for (var i = 0; i < L; i++) {
        roundSum.weights[i][0] <== sums[i] % (2 ** 64);
        roundSum.weights[i][1] <== sums[i] \ (2 ** 64);
    }
    roundSum.out[0] === 0;
    roundSum.out[1] === 0;

    if (L == 0) {
        out[0] <== 0;
        out[1] <== 0;
    } else {
        signal accumulators[L][2];
        accumulators[L - 1] <== coefficients[L - 1];
        component products[L - 1];
        component additions[L - 1];
        for (var i = L - 2; i >= 0; i--) {
            products[i] = BrowserFp128Mul();
            products[i].a <== accumulators[i + 1];
            products[i].b <== challenge;
            additions[i] = BrowserFp128Add();
            additions[i].a <== products[i].out;
            additions[i].b <== coefficients[i];
            accumulators[i] <== additions[i].out;
        }
        out <== accumulators[0];
    }
    out === outputClaim;
}

// Complete clear stage-1 scalar relations with external transcript/PCS signals.
template BrowserStage1Clear(LOG_T, L) {
    assert(LOG_T >= 0 && LOG_T <= 21);
    var R = LOG_T + 1;
    signal input tau[LOG_T + 2][2];
    signal input uniskipChallenge[2];
    signal input uniskipCoefficients[L][2];
    signal input uniskipOutputClaim[2];
    signal input batchingCoefficient[2];
    signal input remainderChallenges[R][2];
    signal input compressed[R][3][2];
    signal input openings[35][2];
    signal output initialClaim[2];
    signal output expectedFinal[2];
    signal output openingPoint[R][2];

    component uniskip = BrowserStage1Uniskip(L);
    uniskip.coefficients <== uniskipCoefficients;
    uniskip.challenge <== uniskipChallenge;
    uniskip.outputClaim <== uniskipOutputClaim;
    component remainder = BrowserStage1Remainder(LOG_T);
    remainder.tau <== tau;
    remainder.uniskipChallenge <== uniskipChallenge;
    remainder.uniskipOutputClaim <== uniskip.out;
    remainder.batchingCoefficient <== batchingCoefficient;
    remainder.remainderChallenges <== remainderChallenges;
    remainder.compressed <== compressed;
    remainder.openings <== openings;
    initialClaim <== remainder.initialClaim;
    expectedFinal <== remainder.expectedFinal;
    openingPoint <== remainder.openingPoint;
}
