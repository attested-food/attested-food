// KoalaBear inverses for SP1's gnark hints (koalabear.h). SP1 links Rust
// implementations (sp1-recursion-gnark-ffi src/koalabear.rs); this standalone
// exporter carries the same functions in C. Field p = 2^31 - 2^24 + 1, the
// degree-4 extension is F_p[x] / (x^4 - 3), as Plonky3's KoalaBear.
#include <stdint.h>
#include "../../koalabear.h"

#define P 2130706433u
#define W 3u

static uint32_t mul(uint32_t a, uint32_t b) { return (uint32_t)(((uint64_t)a * b) % P); }
static uint32_t add(uint32_t a, uint32_t b) { return (uint32_t)(((uint64_t)a + b) % P); }
static uint32_t sub(uint32_t a, uint32_t b) { return (uint32_t)(((uint64_t)a + P - b) % P); }

static uint32_t pw(uint32_t a, uint32_t e) {
    uint32_t r = 1;
    while (e) {
        if (e & 1) r = mul(r, a);
        a = mul(a, a);
        e >>= 1;
    }
    return r;
}

uint32_t koalabearinv(uint32_t a) { return pw(a % P, P - 2); }

// Inverse of a = a0 + a1 x + a2 x^2 + a3 x^3: solve M y = e0 where column j of
// M is a * x^j reduced with x^4 = W. Returns coefficient i of the inverse.
uint32_t koalabearextinv(uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t i) {
    uint32_t a[4] = {a0 % P, a1 % P, a2 % P, a3 % P};
    uint32_t m[4][5];
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 5; c++) m[r][c] = 0;
    for (int j = 0; j < 4; j++)
        for (int k = 0; k < 4; k++) {
            int d = j + k;
            uint32_t v = a[k];
            if (d >= 4) { d -= 4; v = mul(v, W); }
            m[d][j] = add(m[d][j], v);
        }
    m[0][4] = 1;
    for (int c = 0; c < 4; c++) {
        int piv = c;
        while (piv < 4 && m[piv][c] == 0) piv++;
        if (piv == 4) return 0;
        if (piv != c)
            for (int k = 0; k < 5; k++) { uint32_t t = m[c][k]; m[c][k] = m[piv][k]; m[piv][k] = t; }
        uint32_t inv = koalabearinv(m[c][c]);
        for (int k = 0; k < 5; k++) m[c][k] = mul(m[c][k], inv);
        for (int r = 0; r < 4; r++)
            if (r != c && m[r][c]) {
                uint32_t f = m[r][c];
                for (int k = 0; k < 5; k++) m[r][k] = sub(m[r][k], mul(f, m[c][k]));
            }
    }
    return m[i & 3][4];
}
