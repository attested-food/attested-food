//! Minimal zlib (RFC 1950) / DEFLATE (RFC 1951) decoder for the zkVM guest.
//!
//! Same output as zlib for every valid stream; every malformed stream panics
//! (no proof), following zlib's validity rules: over-subscribed codes, incomplete
//! codes (except a single length-1 code), missing end-of-block code, too many
//! length/distance symbols, invalid symbols 286/287 and 30/31, distances past
//! the start of the output, NLEN mismatch, input overrun and a bad Adler-32 are
//! all rejected. Decoding is table driven: one lookup for codes up to FAST bits,
//! canonical bit-by-bit decoding for the rare longer codes.

use alloc::vec::Vec;

const FAST: u32 = 10;

const LBASE: [u16; 29] =
    [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258];
const LEXT: [u8; 29] = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0];
const DBASE: [u16; 30] = [
    1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145,
    8193, 12289, 16385, 24577,
];
const DEXT: [u8; 30] =
    [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13];
const CL_ORDER: [usize; 19] = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15];

// Bit-reversed bytes.
static REV8: [u8; 256] = {
    let mut t = [0u8; 256];
    let mut k = 0;
    while k < 256 {
        t[k] = (k as u8).reverse_bits();
        k += 1;
    }
    t
};

struct Huff {
    // (symbol << 4) | length for codes of at most FAST bits, 0 = use the slow path.
    fast: [u16; 1 << FAST],
    // Index width of `fast`: min(FAST, longest code), so short codes fill less.
    mask: u64,
    counts: [u16; 16],
    symbols: [u16; 320],
}

impl Huff {
    fn new() -> Self {
        Huff { fast: [0; 1 << FAST], mask: 0, counts: [0; 16], symbols: [0; 320] }
    }

    // `allow_incomplete`: zlib accepts an incomplete set only for a lit/len or
    // distance code whose longest code is 1 bit (a single code).
    fn build(&mut self, lens: &[u8], allow_incomplete: bool) {
        self.counts = [0; 16];
        for &l in lens {
            self.counts[l as usize] += 1;
        }
        self.counts[0] = 0;
        let mut left: i32 = 1;
        let mut max = 0;
        for len in 1..16 {
            left <<= 1;
            left -= self.counts[len] as i32;
            assert!(left >= 0, "over-subscribed huffman code");
            if self.counts[len] != 0 {
                max = len;
            }
        }
        if left > 0 {
            assert!(allow_incomplete && max <= 1, "incomplete huffman code");
        }
        // Canonical order: symbols sorted by (length, symbol).
        let mut offs = [0u16; 16];
        for len in 1..15 {
            offs[len + 1] = offs[len] + self.counts[len];
        }
        for (sym, &l) in lens.iter().enumerate() {
            if l != 0 {
                self.symbols[offs[l as usize] as usize] = sym as u16;
                offs[l as usize] += 1;
            }
        }
        // Fast table: walk canonical codes, store each bit-reversed code.
        let tb = (max as u32).clamp(1, FAST);
        let size = 1usize << tb;
        self.mask = size as u64 - 1;
        self.fast[..size].fill(0);
        let mut code: u32 = 0;
        let mut idx = 0usize;
        for len in 1..=(tb as usize) {
            for _ in 0..self.counts[len] {
                let sym = self.symbols[idx] as u32;
                idx += 1;
                let rev =
                    ((REV8[(code & 0xff) as usize] as u32) << 8 | REV8[(code >> 8) as usize] as u32) >> (16 - len);
                let entry = ((sym << 4) | len as u32) as u16;
                let mut j = rev as usize;
                while j < size {
                    self.fast[j] = entry;
                    j += 1 << len;
                }
                code += 1;
            }
            code <<= 1;
        }
    }
}

#[cfg(feature = "std")]
pub static SLOW: core::sync::atomic::AtomicUsize = core::sync::atomic::AtomicUsize::new(0);

#[derive(Clone, Copy)]
struct Bits<'a> {
    data: &'a [u8],
    pos: usize,
    buf: u64,
    cnt: u32,
}

impl<'a> Bits<'a> {
    #[inline(always)]
    fn refill(&mut self) {
        while self.cnt <= 56 {
            let b = if self.pos < self.data.len() {
                self.data[self.pos]
            } else {
                // Zero padding may only ever sit in the 8-byte lookahead; more
                // means real bits were consumed past the end of the input.
                assert!(self.pos < self.data.len() + 8, "deflate input overrun");
                0
            };
            self.buf |= (b as u64) << self.cnt;
            self.pos += 1;
            self.cnt += 8;
        }
    }

    #[inline(always)]
    fn take(&mut self, n: u32) -> u32 {
        let v = (self.buf & ((1u64 << n) - 1)) as u32;
        self.buf >>= n;
        self.cnt -= n;
        v
    }

    // Bits consumed so far must not run past the real input (the refill pads with zeros).
    fn check_overrun(&self) {
        let consumed_bits = self.pos * 8 - self.cnt as usize;
        assert!(consumed_bits <= self.data.len() * 8, "deflate input overrun");
    }

    #[inline(always)]
    fn decode(&mut self, h: &Huff) -> u32 {
        let e = h.fast[(self.buf & h.mask) as usize];
        if e != 0 {
            let len = (e & 15) as u32;
            self.buf >>= len;
            self.cnt -= len;
            return (e >> 4) as u32;
        }
        self.decode_slow(h)
    }

    #[inline(always)]
    fn decode_slow(&mut self, h: &Huff) -> u32 {
        let (sym, len) = slow(self.buf, h);
        self.buf >>= len;
        self.cnt -= len;
        sym
    }
}

// Canonical bit-by-bit decode for codes longer than FAST bits: (symbol, length).
#[inline(never)]
fn slow(buf: u64, h: &Huff) -> (u32, u32) {
    #[cfg(feature = "std")]
    SLOW.fetch_add(1, core::sync::atomic::Ordering::Relaxed);
    let mut code: i32 = 0;
    let mut first: i32 = 0;
    let mut index: i32 = 0;
    for len in 1..16 {
        code |= ((buf >> (len - 1)) & 1) as i32;
        let count = h.counts[len] as i32;
        if code - first < count {
            return (h.symbols[(index + code - first) as usize] as u32, len as u32);
        }
        index += count;
        first += count;
        first <<= 1;
        code <<= 1;
    }
    panic!("invalid huffman code");
}

/// Inflate a zlib stream (2-byte header, DEFLATE data, Adler-32 trailer).
pub fn zlib_decompress(input: &[u8], size_hint: usize) -> Vec<u8> {
    assert!(input.len() >= 6, "zlib stream too short");
    let cmf = input[0];
    let flg = input[1];
    assert!(cmf & 0x0f == 8 && (cmf >> 4) <= 7, "zlib: bad method/window");
    assert!(((cmf as u32) << 8 | flg as u32) % 31 == 0, "zlib: bad header check");
    assert!(flg & 0x20 == 0, "zlib: preset dictionary not supported");
    let mut out: Vec<u8> = Vec::with_capacity(size_hint.max(input.len() * 4));
    let end = inflate_raw(&input[2..], &mut out);
    let tail = 2 + end;
    assert!(tail + 4 <= input.len(), "zlib: missing adler32");
    let want = u32::from_be_bytes([input[tail], input[tail + 1], input[tail + 2], input[tail + 3]]);
    assert!(adler32(&out) == want, "zlib: adler32 mismatch");
    out
}

// Returns the byte offset just past the final block (byte aligned).
fn inflate_raw(data: &[u8], out: &mut Vec<u8>) -> usize {
    let mut bits = Bits { data, pos: 0, buf: 0, cnt: 0 };
    let mut lit = Huff::new();
    let mut dist = Huff::new();
    loop {
        bits.refill();
        let last = bits.take(1);
        let kind = bits.take(2);
        match kind {
            0 => {
                // Stored: drop to the byte boundary, LEN / NLEN, raw bytes.
                let drop = bits.cnt % 8;
                bits.take(drop);
                let len = bits.take(16) as usize;
                let nlen = bits.take(16) as usize;
                assert!(len == (!nlen & 0xffff), "stored block: NLEN mismatch");
                // Rewind the byte cursor to the first unconsumed byte.
                let at = bits.pos - (bits.cnt / 8) as usize;
                assert!(at <= data.len() && at + len <= data.len(), "stored block overrun");
                out.extend_from_slice(&data[at..at + len]);
                bits.pos = at + len;
                bits.buf = 0;
                bits.cnt = 0;
            }
            1 => {
                let mut l = [0u8; 288];
                l[..144].fill(8);
                l[144..256].fill(9);
                l[256..280].fill(7);
                l[280..].fill(8);
                lit.build(&l, false);
                dist.build(&[5u8; 32], false);
                codes(&mut bits, &lit, &dist, out);
            }
            2 => {
                read_dynamic(&mut bits, &mut lit, &mut dist);
                codes(&mut bits, &lit, &dist, out);
            }
            _ => panic!("invalid deflate block type"),
        }
        bits.check_overrun();
        if last == 1 {
            break;
        }
    }
    // Final position, rounded up to a whole byte.
    let consumed_bits = bits.pos * 8 - bits.cnt as usize;
    (consumed_bits + 7) / 8
}

fn read_dynamic(bits: &mut Bits, lit: &mut Huff, dist: &mut Huff) {
    let nlen = bits.take(5) as usize + 257;
    let ndist = bits.take(5) as usize + 1;
    let ncode = bits.take(4) as usize + 4;
    assert!(nlen <= 286 && ndist <= 30, "too many length or distance symbols");
    let mut cl = [0u8; 19];
    for &o in CL_ORDER.iter().take(ncode) {
        bits.refill();
        cl[o] = bits.take(3) as u8;
    }
    let mut clh = Huff::new();
    clh.build(&cl, false);
    let mut lens = [0u8; 316];
    let total = nlen + ndist;
    let mut i = 0;
    while i < total {
        bits.refill();
        let sym = bits.decode(&clh);
        if sym < 16 {
            lens[i] = sym as u8;
            i += 1;
        } else {
            let (val, rep) = match sym {
                16 => {
                    assert!(i > 0, "repeat with no first length");
                    (lens[i - 1], 3 + bits.take(2) as usize)
                }
                17 => (0, 3 + bits.take(3) as usize),
                _ => (0, 11 + bits.take(7) as usize),
            };
            assert!(i + rep <= total, "too many code lengths");
            for _ in 0..rep {
                lens[i] = val;
                i += 1;
            }
        }
    }
    bits.check_overrun();
    assert!(lens[256] != 0, "missing end-of-block code");
    lit.build(&lens[..nlen], true);
    dist.build(&lens[nlen..total], true);
}

fn codes(bits_ref: &mut Bits, lit: &Huff, dist: &Huff, out: &mut Vec<u8>) {
    // Work on a register-resident copy of the bit reader; write it back on exit.
    let mut bits = *bits_ref;
    let r = codes_inner(&mut bits, lit, dist, out);
    *bits_ref = bits;
    r
}

#[inline(always)]
fn codes_inner(bits: &mut Bits, lit: &Huff, dist: &Huff, out: &mut Vec<u8>) {
    loop {
        bits.refill();
        let sym = bits.decode(lit);
        if sym < 256 {
            out.push(sym as u8);
            continue;
        }
        if sym == 256 {
            return;
        }
        let s = (sym - 257) as usize;
        assert!(s < 29, "invalid length symbol");
        let len = LBASE[s] as usize + bits.take(LEXT[s] as u32) as usize;
        let ds = bits.decode(dist) as usize;
        assert!(ds < 30, "invalid distance symbol");
        bits.refill();
        let d = DBASE[ds] as usize + bits.take(DEXT[ds] as u32) as usize;
        let n = out.len();
        assert!(d <= n, "distance too far back");
        out.reserve(len);
        unsafe {
            let p = out.as_mut_ptr();
            let mut src = p.add(n - d);
            let mut dst = p.add(n);
            // Strictly in-order byte copy (overlapping copies repeat the
            // pattern), unrolled by 4; len >= 3 always.
            let mut left = len;
            while left >= 4 {
                *dst = *src;
                *dst.add(1) = *src.add(1);
                *dst.add(2) = *src.add(2);
                *dst.add(3) = *src.add(3);
                dst = dst.add(4);
                src = src.add(4);
                left -= 4;
            }
            while left > 0 {
                *dst = *src;
                dst = dst.add(1);
                src = src.add(1);
                left -= 1;
            }
            out.set_len(n + len);
        }
    }
}

pub fn adler32(data: &[u8]) -> u32 {
    // Scalar head until 8-byte aligned, then 8 bytes per step with SWAR sums:
    // for bytes x0..x7, a += sum(x), b += 8*a_old + sum((8-k)*xk). Reduce mod
    // 65521 every 4096 words so u64 sums cannot overflow.
    const M: u64 = 65521;
    let mut a: u64 = 1;
    let mut b: u64 = 0;
    let mut i = 0;
    let n = data.len();
    while i < n && (data.as_ptr() as usize + i) & 7 != 0 {
        a += data[i] as u64;
        b += a;
        i += 1;
    }
    const LO: u64 = 0x00ff_00ff_00ff_00ff;
    const ONES: u64 = 0x0001_0001_0001_0001;
    // Even lanes hold bytes 0,2,4,6 (weights 8,6,4,2); odd lanes bytes 1,3,5,7 (7,5,3,1).
    const WE: u64 = 2 | (4 << 16) | (6 << 32) | (8 << 48);
    const WO: u64 = 1 | (3 << 16) | (5 << 32) | (7 << 48);
    let words = (n - i) / 8;
    let p = unsafe { data.as_ptr().add(i) as *const u64 };
    let mut w = 0;
    while w < words {
        let stop = (w + 4096).min(words);
        while w < stop {
            let x = unsafe { *p.add(w) };
            let e = x & LO;
            let o = (x >> 8) & LO;
            let sum = ((e + o).wrapping_mul(ONES)) >> 48;
            let ws = (e.wrapping_mul(WE) >> 48) + (o.wrapping_mul(WO) >> 48);
            b += 8 * a + ws;
            a += sum;
            w += 1;
        }
        a %= M;
        b %= M;
    }
    i += words * 8;
    while i < n {
        a += data[i] as u64;
        b += a;
        i += 1;
    }
    a %= M;
    b %= M;
    ((b as u32) << 16) | a as u32
}
