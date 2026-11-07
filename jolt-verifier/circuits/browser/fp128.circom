pragma circom 2.2.3;

function browser_fp128_modulus() {
    return 2 ** 128 - 2 ** 32 + 22537;
}

// Witness calculation only. BrowserFp128Mul constrains the integer identity.
function browser_fp128_product_division(a, b) {
    var base = 2 ** 64;
    var digits[4];
    var carry = 0;
    for (var k = 0; k < 4; k++) {
        var coefficient = carry;
        for (var i = 0; i < 2; i++) {
            for (var j = 0; j < 2; j++) {
                if (i + j == k) {
                    coefficient += a[i] * b[j];
                }
            }
        }
        digits[k] = coefficient % base;
        carry = coefficient \ base;
    }
    var remainder = 0;
    var quotient = 0;
    for (var bit = 255; bit >= 0; bit--) {
        remainder = remainder * 2 + ((digits[bit \ 64] >> (bit % 64)) & 1);
        quotient *= 2;
        if (remainder >= browser_fp128_modulus()) {
            remainder -= browser_fp128_modulus();
            quotient += 1;
        }
    }
    var result[4] = [quotient % base, quotient \ base, remainder % base, remainder \ base];
    return result;
}

template BrowserBits(n) {
    assert(-1 == 21888242871839275222246405745257275088548364400416034343698204186575808495616);
    assert(n > 0 && n <= 129);
    signal input in;
    signal output bits[n];
    var packed = 0;
    for (var i = 0; i < n; i++) {
        bits[i] <-- (in >> i) & 1;
        bits[i] * (bits[i] - 1) === 0;
        packed += bits[i] * (2 ** i);
    }
    in === packed;
}

// Two canonical little-endian u64 limbs. The slack bound prevents aliases mod p.
template BrowserFp128Canonical() {
    signal input in[2];
    signal output packed;
    component limbs[2];
    for (var i = 0; i < 2; i++) {
        limbs[i] = BrowserBits(64);
        limbs[i].in <== in[i];
    }
    packed <== in[0] + (2 ** 64) * in[1];
    signal slack;
    slack <-- browser_fp128_modulus() - 1 - packed;
    component bound = BrowserBits(128);
    bound.in <== slack;
    packed + slack === browser_fp128_modulus() - 1;
}

template BrowserFp128Add() {
    signal input a[2];
    signal input b[2];
    signal output out[2];
    component ca = BrowserFp128Canonical();
    component cb = BrowserFp128Canonical();
    component cr = BrowserFp128Canonical();
    for (var i = 0; i < 2; i++) {
        ca.in[i] <== a[i];
        cb.in[i] <== b[i];
    }
    signal reduction;
    reduction <-- (ca.packed + cb.packed) \ browser_fp128_modulus();
    reduction * (reduction - 1) === 0;
    signal remainder;
    remainder <== ca.packed + cb.packed - reduction * browser_fp128_modulus();
    out[0] <-- remainder % (2 ** 64);
    out[1] <-- remainder \ (2 ** 64);
    for (var i = 0; i < 2; i++) {
        cr.in[i] <== out[i];
    }
    remainder === cr.packed;
}

template BrowserFp128Sub() {
    signal input a[2];
    signal input b[2];
    signal output out[2];
    component ca = BrowserFp128Canonical();
    component cb = BrowserFp128Canonical();
    component cr = BrowserFp128Canonical();
    for (var i = 0; i < 2; i++) {
        ca.in[i] <== a[i];
        cb.in[i] <== b[i];
    }
    signal reduction;
    reduction <-- (ca.packed + browser_fp128_modulus() - cb.packed) \ browser_fp128_modulus();
    reduction * (reduction - 1) === 0;
    signal remainder;
    remainder <== ca.packed + browser_fp128_modulus() - cb.packed - reduction * browser_fp128_modulus();
    out[0] <-- remainder % (2 ** 64);
    out[1] <-- remainder \ (2 ** 64);
    for (var i = 0; i < 2; i++) {
        cr.in[i] <== out[i];
    }
    remainder === cr.packed;
}

template BrowserFp128Mul() {
    signal input a[2];
    signal input b[2];
    signal output out[2];
    var base = 2 ** 64;
    var p[2] = [browser_fp128_modulus() % base, browser_fp128_modulus() \ base];
    component ca = BrowserFp128Canonical();
    component cb = BrowserFp128Canonical();
    component cr = BrowserFp128Canonical();
    for (var i = 0; i < 2; i++) {
        ca.in[i] <== a[i];
        cb.in[i] <== b[i];
    }
    signal division[4];
    division <-- browser_fp128_product_division(a, b);
    component quotient[2];
    for (var i = 0; i < 2; i++) {
        quotient[i] = BrowserBits(64);
        quotient[i].in <== division[i];
        out[i] <== division[2 + i];
        cr.in[i] <== out[i];
    }
    signal products[2][2];
    for (var i = 0; i < 2; i++) {
        for (var j = 0; j < 2; j++) {
            products[i][j] <== a[i] * b[j];
        }
    }
    signal carry[5];
    carry[0] <== 0;
    component carryBound[3];
    for (var k = 0; k < 4; k++) {
        var difference = carry[k];
        for (var i = 0; i < 2; i++) {
            for (var j = 0; j < 2; j++) {
                if (i + j == k) {
                    difference += products[i][j] - division[i] * p[j];
                }
            }
        }
        if (k < 2) {
            difference -= out[k];
        }
        carry[k + 1] <-- difference / base;
        difference === carry[k + 1] * base;
        if (k < 3) {
            carryBound[k] = BrowserBits(67);
            carryBound[k].in <== carry[k + 1] + (2 ** 66);
        }
    }
    carry[4] === 0;
}

// The caller supplies an inverse witness; multiplication enforces it, including nonzero.
template BrowserFp128InverseCheck() {
    signal input in[2];
    signal input inverse[2];
    component product = BrowserFp128Mul();
    for (var i = 0; i < 2; i++) {
        product.a[i] <== in[i];
        product.b[i] <== inverse[i];
    }
    product.out[0] === 1;
    product.out[1] === 0;
}
