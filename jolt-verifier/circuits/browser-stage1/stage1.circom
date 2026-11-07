pragma circom 2.2.3;

include "../browser-scalar/sumcheck.circom";

// Denominators are products of node differences on {-4, ..., 5}.
function browser_stage1_lagrange_inverses() {
    var inverse[10] = [
        218146240806654204064360739224193641015,
        78378034265742944201000991547096831047,
        26770229857966686659370641239085942509,
        50963585971723885615926706251290556378,
        263836987963352635039484548050537432130,
        76445378957585828423890059376935834567,
        289318780949214577847447901176182710319,
        313512137062971776804003966188387324188,
        261904332655195519262373615880376435650,
        122136126114284259399013868203279625682
    ];
    return inverse;
}

// Product form has no challenge-dependent inversions, including at grid nodes.
template BrowserStage1Lagrange10() {
    signal input point[2];
    signal output basis[10][2];
    var inverses[10] = browser_stage1_lagrange_inverses();
    component differences[10];
    for (var j = 0; j < 10; j++) {
        var node = (browser_fp128_modulus() + j - 4) % browser_fp128_modulus();
        differences[j] = BrowserFp128Sub();
        differences[j].a <== point;
        differences[j].b[0] <== node % (2 ** 64);
        differences[j].b[1] <== node \ (2 ** 64);
    }
    component products[10][9];
    signal accumulators[10][10][2];
    for (var i = 0; i < 10; i++) {
        accumulators[i][0][0] <== inverses[i] % (2 ** 64);
        accumulators[i][0][1] <== inverses[i] \ (2 ** 64);
        var k = 0;
        for (var j = 0; j < 10; j++) {
            if (i != j) {
                products[i][k] = BrowserFp128Mul();
                products[i][k].a <== accumulators[i][k];
                products[i][k].b <== differences[j].out;
                accumulators[i][k + 1] <== products[i][k].out;
                k++;
            }
        }
        basis[i] <== accumulators[i][9];
    }
}

// Sparse RV64 row, with column zero denoting the fixed public constant one.
template BrowserStage1Row(indices, factors) {
    signal input openings[35][2];
    signal output out[2];
    signal accumulators[6][2];
    accumulators[0][0] <== 0;
    accumulators[0][1] <== 0;
    component products[5];
    component additions[5];
    for (var k = 0; k < 5; k++) {
        if (factors[k] == 0) {
            accumulators[k + 1] <== accumulators[k];
        } else {
            var coefficient = (browser_fp128_modulus() + factors[k]) % browser_fp128_modulus();
            products[k] = BrowserFp128Mul();
            if (indices[k] == 0) {
                products[k].a[0] <== 1;
                products[k].a[1] <== 0;
            } else {
                products[k].a <== openings[indices[k] - 1];
            }
            products[k].b[0] <== coefficient % (2 ** 64);
            products[k].b[1] <== coefficient \ (2 ** 64);
            additions[k] = BrowserFp128Add();
            additions[k].a <== accumulators[k];
            additions[k].b <== products[k].out;
            accumulators[k + 1] <== additions[k].out;
        }
    }
    out <== accumulators[5];
}

// Concrete non-field-inline RV64 matrix, 19 equality rows and 35 openings.
template BrowserStage1Terminal(LOG_T) {
    assert(LOG_T >= 0 && LOG_T <= 21);
    var R = LOG_T + 1;
    signal input tau[LOG_T + 2][2];
    signal input uniskipChallenge[2];
    signal input remainderChallenges[R][2];
    signal input openings[35][2];
    signal output terminal[2];
    signal output openingPoint[R][2];
    signal output tauKernel[2];
    signal output az[2];
    signal output bz[2];

    var aIndices[19][5] = [
        [25, 26, 0, 0, 0], [0, 25, 26, 0, 0], [25, 0, 0, 0, 0], [25, 0, 0, 0, 0],
        [26, 0, 0, 0, 0], [22, 23, 24, 0, 0], [0, 22, 23, 24, 0], [22, 0, 0, 0, 0],
        [23, 0, 0, 0, 0], [24, 0, 0, 0, 0], [0, 22, 23, 24, 32], [30, 0, 0, 0, 0],
        [28, 0, 0, 0, 0], [27, 0, 0, 0, 0], [21, 0, 0, 0, 0], [4, 0, 0, 0, 0],
        [0, 4, 27, 0, 0], [29, 35, 0, 0, 0], [18, 19, 0, 0, 0]
    ];
    var aFactors[19][5] = [
        [1, 1, 0, 0, 0], [1, -1, -1, 0, 0], [1, 0, 0, 0, 0], [1, 0, 0, 0, 0],
        [1, 0, 0, 0, 0], [1, 1, 1, 0, 0], [1, -1, -1, -1, 0], [1, 0, 0, 0, 0],
        [1, 0, 0, 0, 0], [1, 0, 0, 0, 0], [1, -1, -1, -1, -1], [1, 0, 0, 0, 0],
        [1, 0, 0, 0, 0], [1, 0, 0, 0, 0], [1, 0, 0, 0, 0], [1, 0, 0, 0, 0],
        [1, -1, -1, 0, 0], [1, -1, 0, 0, 0], [1, -1, 0, 0, 0]
    ];
    var bIndices[19][5] = [
        [8, 9, 7, 0, 0], [8, 0, 0, 0, 0], [12, 13, 0, 0, 0], [12, 11, 0, 0, 0],
        [10, 13, 0, 0, 0], [14, 0, 0, 0, 0], [14, 1, 0, 0, 0], [15, 1, 2, 0, 0],
        [15, 1, 2, 0, 0], [15, 3, 0, 0, 0], [15, 2, 0, 0, 0], [20, 0, 0, 0, 0],
        [11, 20, 0, 0, 0], [11, 6, 0, 33, 0], [16, 20, 0, 0, 0], [16, 6, 7, 0, 0],
        [16, 6, 0, 31, 33], [17, 5, 0, 0, 0], [0, 31, 0, 0, 0]
    ];
    var bFactors[19][5] = [
        [1, -1, -1, 0, 0], [1, 0, 0, 0, 0], [1, -1, 0, 0, 0], [1, -1, 0, 0, 0],
        [1, -1, 0, 0, 0], [1, 0, 0, 0, 0], [1, -1, 0, 0, 0], [1, -1, -1, 0, 0],
        [1, -1, 1, -(2 ** 64), 0], [1, -1, 0, 0, 0], [1, -1, 0, 0, 0], [1, -1, 0, 0, 0],
        [1, -1, 0, 0, 0], [1, -1, -4, 2, 0], [1, -1, 0, 0, 0], [1, -1, -1, 0, 0],
        [1, -1, -4, 4, 2], [1, -1, -1, 0, 0], [1, -1, 0, 0, 0]
    ];
    var first[10] = [1, 2, 3, 4, 5, 6, 11, 14, 17, 18];
    var second[9] = [0, 7, 8, 9, 10, 12, 13, 15, 16];

    component canonical[35];
    for (var i = 0; i < 35; i++) {
        canonical[i] = BrowserFp128Canonical();
        canonical[i].in <== openings[i];
    }
    component lu = BrowserStage1Lagrange10();
    component lh = BrowserStage1Lagrange10();
    lu.point <== uniskipChallenge;
    lh.point <== tau[LOG_T + 1];
    component lagrangeKernel = BrowserSumcheckWeightedSum(10);
    lagrangeKernel.values <== lu.basis;
    lagrangeKernel.weights <== lh.basis;

    component complement = BrowserFp128Sub();
    complement.a[0] <== 1;
    complement.a[1] <== 0;
    complement.b <== remainderChallenges[0];
    signal rowWeights[19][2];
    component firstWeights[10];
    component secondWeights[9];
    for (var i = 0; i < 10; i++) {
        firstWeights[i] = BrowserFp128Mul();
        firstWeights[i].a <== lu.basis[i];
        firstWeights[i].b <== complement.out;
        rowWeights[first[i]] <== firstWeights[i].out;
        if (i < 9) {
            secondWeights[i] = BrowserFp128Mul();
            secondWeights[i].a <== lu.basis[i];
            secondWeights[i].b <== remainderChallenges[0];
            rowWeights[second[i]] <== secondWeights[i].out;
        }
    }
    component aRows[19];
    component bRows[19];
    component aFold = BrowserSumcheckWeightedSum(19);
    component bFold = BrowserSumcheckWeightedSum(19);
    for (var row = 0; row < 19; row++) {
        aRows[row] = BrowserStage1Row(aIndices[row], aFactors[row]);
        bRows[row] = BrowserStage1Row(bIndices[row], bFactors[row]);
        aRows[row].openings <== openings;
        bRows[row].openings <== openings;
        aFold.values[row] <== aRows[row].out;
        bFold.values[row] <== bRows[row].out;
    }
    aFold.weights <== rowWeights;
    bFold.weights <== rowWeights;
    az <== aFold.out;
    bz <== bFold.out;

    // EqPolynomial(tau_low, reverse(remainder)) includes the stream coordinate.
    signal kernels[R + 1][2];
    kernels[0] <== lagrangeKernel.out;
    component oneMinusTau[R];
    component oneMinusR[R];
    component zeroProducts[R];
    component oneProducts[R];
    component eqFactors[R];
    component kernelProducts[R];
    for (var i = 0; i < R; i++) {
        openingPoint[i] <== remainderChallenges[R - 1 - i];
        oneMinusTau[i] = BrowserFp128Sub();
        oneMinusR[i] = BrowserFp128Sub();
        oneMinusTau[i].a[0] <== 1;
        oneMinusTau[i].a[1] <== 0;
        oneMinusTau[i].b <== tau[i];
        oneMinusR[i].a[0] <== 1;
        oneMinusR[i].a[1] <== 0;
        oneMinusR[i].b <== remainderChallenges[R - 1 - i];
        zeroProducts[i] = BrowserFp128Mul();
        oneProducts[i] = BrowserFp128Mul();
        zeroProducts[i].a <== oneMinusTau[i].out;
        zeroProducts[i].b <== oneMinusR[i].out;
        oneProducts[i].a <== tau[i];
        oneProducts[i].b <== remainderChallenges[R - 1 - i];
        eqFactors[i] = BrowserFp128Add();
        eqFactors[i].a <== zeroProducts[i].out;
        eqFactors[i].b <== oneProducts[i].out;
        kernelProducts[i] = BrowserFp128Mul();
        kernelProducts[i].a <== kernels[i];
        kernelProducts[i].b <== eqFactors[i].out;
        kernels[i + 1] <== kernelProducts[i].out;
    }
    tauKernel <== kernels[R];
    component formsProduct = BrowserFp128Mul();
    formsProduct.a <== az;
    formsProduct.b <== bz;
    component result = BrowserFp128Mul();
    result.a <== tauKernel;
    result.b <== formsProduct.out;
    terminal <== result.out;
}

function browser_stage1_degrees() {
    var degrees[22];
    for (var i = 0; i < 22; i++) {
        degrees[i] = 3;
    }
    return degrees;
}

// Uni-skip proof and all transcript/PCS bindings remain external.
template BrowserStage1Remainder(LOG_T) {
    assert(LOG_T >= 0 && LOG_T <= 21);
    var R = LOG_T + 1;
    signal input tau[LOG_T + 2][2];
    signal input uniskipChallenge[2];
    signal input uniskipOutputClaim[2];
    signal input batchingCoefficient[2];
    signal input remainderChallenges[R][2];
    signal input compressed[R][3][2];
    signal input openings[35][2];
    signal output initialClaim[2];
    signal output expectedFinal[2];
    signal output openingPoint[R][2];
    signal output uniskipInitialClaim[2];
    uniskipInitialClaim[0] <== 0;
    uniskipInitialClaim[1] <== 0;

    component relation = BrowserStage1Terminal(LOG_T);
    relation.tau <== tau;
    relation.uniskipChallenge <== uniskipChallenge;
    relation.remainderChallenges <== remainderChallenges;
    relation.openings <== openings;
    openingPoint <== relation.openingPoint;
    component initial = BrowserFp128Mul();
    initial.a <== batchingCoefficient;
    initial.b <== uniskipOutputClaim;
    initialClaim <== initial.out;
    component finalValue = BrowserFp128Mul();
    finalValue.a <== batchingCoefficient;
    finalValue.b <== relation.terminal;
    expectedFinal <== finalValue.out;
    component sumcheck = BrowserCompressedSumcheck(R, 3, browser_stage1_degrees());
    sumcheck.initialClaim <== initialClaim;
    sumcheck.compressed <== compressed;
    sumcheck.challenges <== remainderChallenges;
    sumcheck.expectedFinal <== expectedFinal;
}
