pragma circom 2.2.3;

include "fp128.circom";

// Unkeyed sequential BLAKE2b, RFC 7693. No third-party circuit dependency.
function browser_blake2b_iv() {
    var iv[8] = [
        0x6a09e667f3bcc908, 0xbb67ae8584caa73b,
        0x3c6ef372fe94f82b, 0xa54ff53a5f1d36f1,
        0x510e527fade682d1, 0x9b05688c2b3e6c1f,
        0x1f83d9abfb41bd6b, 0x5be0cd19137e2179
    ];
    return iv;
}

function browser_blake2b_sigma() {
    var sigma[10][16] = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        [14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3],
        [11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4],
        [7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8],
        [9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13],
        [2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9],
        [12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11],
        [13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10],
        [6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5],
        [10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0]
    ];
    return sigma;
}

template BrowserU64Add(n) {
    assert(n == 2 || n == 3);
    signal input in[n];
    signal output out;
    component inputBits[n];
    var total = 0;
    for (var i = 0; i < n; i++) {
        inputBits[i] = BrowserBits(64);
        inputBits[i].in <== in[i];
        total += in[i];
    }
    signal carry;
    out <-- total % (2 ** 64);
    carry <-- total \ (2 ** 64);
    component outputBits = BrowserBits(64);
    outputBits.in <== out;
    component carryBits = BrowserBits(2);
    carryBits.in <== carry;
    total === out + carry * (2 ** 64);
}

template BrowserU64XorRotate(rotation) {
    assert(rotation >= 0 && rotation < 64);
    signal input a;
    signal input b;
    signal output out;
    component ca = BrowserBits(64);
    component cb = BrowserBits(64);
    ca.in <== a;
    cb.in <== b;
    signal xorBits[64];
    var packed = 0;
    for (var i = 0; i < 64; i++) {
        xorBits[i] <== ca.bits[i] + cb.bits[i] - 2 * ca.bits[i] * cb.bits[i];
    }
    for (var i = 0; i < 64; i++) {
        packed += xorBits[(i + rotation) % 64] * (2 ** i);
    }
    out <== packed;
}

template BrowserBlake2bG() {
    signal input v[4];
    signal input m[2];
    signal output out[4];
    component a0 = BrowserU64Add(3);
    a0.in[0] <== v[0]; a0.in[1] <== v[1]; a0.in[2] <== m[0];
    component d0 = BrowserU64XorRotate(32);
    d0.a <== v[3]; d0.b <== a0.out;
    component c0 = BrowserU64Add(2);
    c0.in[0] <== v[2]; c0.in[1] <== d0.out;
    component b0 = BrowserU64XorRotate(24);
    b0.a <== v[1]; b0.b <== c0.out;
    component a1 = BrowserU64Add(3);
    a1.in[0] <== a0.out; a1.in[1] <== b0.out; a1.in[2] <== m[1];
    component d1 = BrowserU64XorRotate(16);
    d1.a <== d0.out; d1.b <== a1.out;
    component c1 = BrowserU64Add(2);
    c1.in[0] <== c0.out; c1.in[1] <== d1.out;
    component b1 = BrowserU64XorRotate(63);
    b1.a <== b0.out; b1.b <== c1.out;
    out[0] <== a1.out;
    out[1] <== b1.out;
    out[2] <== c1.out;
    out[3] <== d1.out;
}

template BrowserBlake2bCompress(totalBytes, last) {
    assert(totalBytes >= 0 && totalBytes < 2 ** 64);
    assert(last == 0 || last == 1);
    signal input h[8];
    signal input block[128];
    signal output out[8];
    var iv[8] = browser_blake2b_iv();
    var sigma[10][16] = browser_blake2b_sigma();
    component bytes[128];
    signal words[16];
    for (var i = 0; i < 128; i++) {
        bytes[i] = BrowserBits(8);
        bytes[i].in <== block[i];
    }
    for (var i = 0; i < 16; i++) {
        var word = 0;
        for (var j = 0; j < 8; j++) {
            word += block[8 * i + j] * (2 ** (8 * j));
        }
        words[i] <== word;
    }
    signal state[25][16];
    for (var i = 0; i < 8; i++) {
        state[0][i] <== h[i];
        if (i == 4) {
            state[0][8 + i] <== iv[i] ^ totalBytes;
        } else if (i == 6 && last == 1) {
            state[0][8 + i] <== iv[i] ^ (2 ** 64 - 1);
        } else {
            state[0][8 + i] <== iv[i];
        }
    }
    component column[12][4];
    component diagonal[12][4];
    for (var r = 0; r < 12; r++) {
        for (var j = 0; j < 4; j++) {
            column[r][j] = BrowserBlake2bG();
            for (var k = 0; k < 4; k++) {
                column[r][j].v[k] <== state[2 * r][j + 4 * k];
            }
            column[r][j].m[0] <== words[sigma[r % 10][2 * j]];
            column[r][j].m[1] <== words[sigma[r % 10][2 * j + 1]];
            for (var k = 0; k < 4; k++) {
                state[2 * r + 1][j + 4 * k] <== column[r][j].out[k];
            }
        }
        for (var j = 0; j < 4; j++) {
            diagonal[r][j] = BrowserBlake2bG();
            for (var k = 0; k < 4; k++) {
                diagonal[r][j].v[k] <== state[2 * r + 1][((j + k) % 4) + 4 * k];
            }
            diagonal[r][j].m[0] <== words[sigma[r % 10][8 + 2 * j]];
            diagonal[r][j].m[1] <== words[sigma[r % 10][9 + 2 * j]];
            for (var k = 0; k < 4; k++) {
                state[2 * r + 2][((j + k) % 4) + 4 * k] <== diagonal[r][j].out[k];
            }
        }
    }
    component feed[8][2];
    for (var i = 0; i < 8; i++) {
        feed[i][0] = BrowserU64XorRotate(0);
        feed[i][0].a <== h[i]; feed[i][0].b <== state[24][i];
        feed[i][1] = BrowserU64XorRotate(0);
        feed[i][1].a <== feed[i][0].out; feed[i][1].b <== state[24][i + 8];
        out[i] <== feed[i][1].out;
    }
}

template BrowserBlake2b(byteCount, digestBytes) {
    assert(byteCount >= 0 && byteCount < 2 ** 64);
    assert(digestBytes >= 1 && digestBytes <= 64);
    signal input in[byteCount];
    signal output digest[digestBytes];
    var blocks = byteCount == 0 ? 1 : ((byteCount + 127) \ 128);
    var iv[8] = browser_blake2b_iv();
    signal h[blocks + 1][8];
    for (var i = 0; i < 8; i++) {
        h[0][i] <== i == 0 ? (iv[i] ^ (0x01010000 + digestBytes)) : iv[i];
    }
    component compress[blocks];
    for (var b = 0; b < blocks; b++) {
        var total = b == blocks - 1 ? byteCount : (b + 1) * 128;
        compress[b] = BrowserBlake2bCompress(total, b == blocks - 1);
        for (var i = 0; i < 8; i++) {
            compress[b].h[i] <== h[b][i];
        }
        for (var i = 0; i < 128; i++) {
            if (b * 128 + i < byteCount) {
                compress[b].block[i] <== in[b * 128 + i];
            } else {
                compress[b].block[i] <== 0;
            }
        }
        for (var i = 0; i < 8; i++) {
            h[b + 1][i] <== compress[b].out[i];
        }
    }
    component resultBits[8];
    for (var i = 0; i < 8; i++) {
        resultBits[i] = BrowserBits(64);
        resultBits[i].in <== h[blocks][i];
    }
    for (var i = 0; i < digestBytes; i++) {
        var value = 0;
        for (var j = 0; j < 8; j++) {
            value += resultBits[i \ 8].bits[(i % 8) * 8 + j] * (2 ** j);
        }
        digest[i] <== value;
    }
}
