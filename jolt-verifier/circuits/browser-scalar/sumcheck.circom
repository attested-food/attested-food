pragma circom 2.2.3;

include "../browser/fp128.circom";

// Stored order is c0, c2, ..., cD. The running claim determines c1.
template BrowserCompressedUniPoly(D) {
    assert(D >= 1 && D <= 32);
    signal input compressed[D][2];
    signal input claim[2];
    signal input challenge[2];
    signal output coefficients[D + 1][2];
    signal output out[2];

    component subtract[D + 1];
    for (var k = 0; k <= D; k++) {
        subtract[k] = BrowserFp128Sub();
        for (var limb = 0; limb < 2; limb++) {
            if (k == 0) {
                subtract[k].a[limb] <== claim[limb];
            } else {
                subtract[k].a[limb] <== subtract[k - 1].out[limb];
            }
            if (k <= 1) {
                subtract[k].b[limb] <== compressed[0][limb];
            } else {
                subtract[k].b[limb] <== compressed[k - 1][limb];
            }
        }
    }
    for (var limb = 0; limb < 2; limb++) {
        coefficients[0][limb] <== compressed[0][limb];
        coefficients[1][limb] <== subtract[D].out[limb];
        for (var k = 2; k <= D; k++) {
            coefficients[k][limb] <== compressed[k - 1][limb];
        }
    }

    // Horner evaluation is equivalent to native ascending-power accumulation.
    component multiply[D];
    component add[D];
    signal accumulator[D + 1][2];
    for (var limb = 0; limb < 2; limb++) {
        accumulator[D][limb] <== coefficients[D][limb];
    }
    for (var k = D - 1; k >= 0; k--) {
        multiply[k] = BrowserFp128Mul();
        add[k] = BrowserFp128Add();
        for (var limb = 0; limb < 2; limb++) {
            multiply[k].a[limb] <== accumulator[k + 1][limb];
            multiply[k].b[limb] <== challenge[limb];
        }
        for (var limb = 0; limb < 2; limb++) {
            add[k].a[limb] <== multiply[k].out[limb];
            add[k].b[limb] <== coefficients[k][limb];
        }
        for (var limb = 0; limb < 2; limb++) {
            accumulator[k][limb] <== add[k].out[limb];
        }
    }
    for (var limb = 0; limb < 2; limb++) {
        out[limb] <== accumulator[0][limb];
    }
}

// Shape is compile-time, not proof-selected. Unused slots must be zero.
template BrowserCompressedSumcheck(R, D, degrees) {
    assert(R >= 0 && R <= 255);
    assert(D >= 1 && D <= 32);
    signal input initialClaim[2];
    signal input compressed[R][D][2];
    signal input challenges[R][2];
    signal input expectedFinal[2];
    signal output claims[R + 1][2];
    component initial = BrowserFp128Canonical();
    component finalValue = BrowserFp128Canonical();
    for (var limb = 0; limb < 2; limb++) {
        initial.in[limb] <== initialClaim[limb];
        finalValue.in[limb] <== expectedFinal[limb];
        claims[0][limb] <== initialClaim[limb];
    }
    component rounds[R];
    for (var r = 0; r < R; r++) {
        assert(degrees[r] >= 1 && degrees[r] <= D);
        rounds[r] = BrowserCompressedUniPoly(degrees[r]);
        for (var limb = 0; limb < 2; limb++) {
            rounds[r].claim[limb] <== claims[r][limb];
            rounds[r].challenge[limb] <== challenges[r][limb];
            for (var k = 0; k < D; k++) {
                if (k < degrees[r]) {
                    rounds[r].compressed[k][limb] <== compressed[r][k][limb];
                } else {
                    compressed[r][k][limb] === 0;
                }
            }
        }
        for (var limb = 0; limb < 2; limb++) {
            claims[r + 1][limb] <== rounds[r].out[limb];
        }
    }
    for (var limb = 0; limb < 2; limb++) {
        claims[R][limb] === expectedFinal[limb];
    }
}

// Final relation uses one independently drawn coefficient per present member.
template BrowserSumcheckWeightedSum(N) {
    assert(N >= 0);
    signal input values[N][2];
    signal input weights[N][2];
    signal output out[2];
    signal sums[N + 1][2];
    component products[N];
    component additions[N];
    for (var limb = 0; limb < 2; limb++) {
        sums[0][limb] <== 0;
    }
    for (var i = 0; i < N; i++) {
        products[i] = BrowserFp128Mul();
        additions[i] = BrowserFp128Add();
        for (var limb = 0; limb < 2; limb++) {
            products[i].a[limb] <== values[i][limb];
            products[i].b[limb] <== weights[i][limb];
        }
        for (var limb = 0; limb < 2; limb++) {
            additions[i].a[limb] <== sums[i][limb];
            additions[i].b[limb] <== products[i].out[limb];
        }
        for (var limb = 0; limb < 2; limb++) {
            sums[i + 1][limb] <== additions[i].out[limb];
        }
    }
    for (var limb = 0; limb < 2; limb++) {
        out[limb] <== sums[N][limb];
    }
}

// BatchPrelude: sum coefficient * input_claim * 2^(R - member_rounds).
template BrowserSumcheckBatchInitial(N, R, memberRounds) {
    assert(N >= 0);
    assert(R >= 0 && R <= 255);
    signal input inputClaims[N][2];
    signal input weights[N][2];
    signal output out[2];
    component scaled[N];
    component fold = BrowserSumcheckWeightedSum(N);
    for (var i = 0; i < N; i++) {
        assert(memberRounds[i] >= 0 && memberRounds[i] <= R);
        var scale = 1;
        for (var k = 0; k < R - memberRounds[i]; k++) {
            scale = (scale * 2) % browser_fp128_modulus();
        }
        scaled[i] = BrowserFp128Mul();
        for (var limb = 0; limb < 2; limb++) {
            scaled[i].a[limb] <== inputClaims[i][limb];
        }
        scaled[i].b[0] <== scale % (2 ** 64);
        scaled[i].b[1] <== scale \ (2 ** 64);
        for (var limb = 0; limb < 2; limb++) {
            fold.values[i][limb] <== scaled[i].out[limb];
            fold.weights[i][limb] <== weights[i][limb];
        }
    }
    for (var limb = 0; limb < 2; limb++) {
        out[limb] <== fold.out[limb];
    }
}
