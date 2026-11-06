//! SHA-256 reading the message as 8-byte aligned words (funnel-shifted when
//! the slice is not aligned) and byte-swapping with SWAR masks instead of
//! per-byte loads. With the `sp1` feature on the SP1 zkVM target the block
//! function is the SP1 extend/compress precompile pair (the `pico` feature
//! takes the same path: Pico exports the same two syscalls with the same
//! signatures); everywhere else it is the portable `compress` below. Words are
//! held in u64 slots because that is the SP1 v6 (RV64) syscall layout.
//!
//! With the `risc0` feature on the RISC Zero target (RV32) the whole message is
//! hashed by the `sys_sha_buffer` accelerator instead, see [`risc0`]. With the
//! `openvm` feature on the OpenVM target (RV32) each block goes through the
//! SHA-2 extension's compress instruction, see [`openvm`].
#![cfg_attr(
    all(any(feature = "risc0", feature = "openvm"), target_os = "zkvm", target_arch = "riscv32"),
    allow(dead_code)
)]

const H0: [u64; 8] = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];

#[repr(align(64))]
struct W([u64; 64]);

// Provided by `sp1-zkvm`, which every SP1 guest links (by `pico-sdk` in a Pico guest).
#[cfg(all(any(feature = "sp1", feature = "pico"), target_os = "zkvm"))]
extern "C" {
    fn syscall_sha256_extend(w: *mut [u64; 64]);
    fn syscall_sha256_compress(w: *mut [u64; 64], state: *mut [u64; 8]);
}

#[cfg(all(any(feature = "sp1", feature = "pico"), target_os = "zkvm"))]
#[inline(always)]
fn compress(w: &mut W, state: &mut [u64; 8]) {
    unsafe {
        syscall_sha256_extend(&mut w.0);
        syscall_sha256_compress(&mut w.0, state);
    }
}

// Portable block function (native builds and zkVMs without a precompile here).
#[cfg(not(all(any(feature = "sp1", feature = "pico"), target_os = "zkvm")))]
fn compress(w: &mut W, state: &mut [u64; 8]) {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98,
        0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
        0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8,
        0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
        0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
        0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
        0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];
    let mut m = [0u32; 64];
    for i in 0..16 {
        m[i] = w.0[i] as u32;
    }
    for i in 16..64 {
        let s0 = m[i - 15].rotate_right(7) ^ m[i - 15].rotate_right(18) ^ (m[i - 15] >> 3);
        let s1 = m[i - 2].rotate_right(17) ^ m[i - 2].rotate_right(19) ^ (m[i - 2] >> 10);
        m[i] = m[i - 16].wrapping_add(s0).wrapping_add(m[i - 7]).wrapping_add(s1);
    }
    let mut v = [0u32; 8];
    for i in 0..8 {
        v[i] = state[i] as u32;
    }
    for i in 0..64 {
        let s1 = v[4].rotate_right(6) ^ v[4].rotate_right(11) ^ v[4].rotate_right(25);
        let ch = (v[4] & v[5]) ^ (!v[4] & v[6]);
        let t1 = v[7].wrapping_add(s1).wrapping_add(ch).wrapping_add(K[i]).wrapping_add(m[i]);
        let s0 = v[0].rotate_right(2) ^ v[0].rotate_right(13) ^ v[0].rotate_right(22);
        let maj = (v[0] & v[1]) ^ (v[0] & v[2]) ^ (v[1] & v[2]);
        let t2 = s0.wrapping_add(maj);
        v = [t1.wrapping_add(t2), v[0], v[1], v[2], v[3].wrapping_add(t1), v[4], v[5], v[6]];
    }
    for i in 0..8 {
        state[i] = (state[i] as u32).wrapping_add(v[i]) as u64;
    }
}

// Little-endian u64 of 8 message bytes -> the two big-endian u32 words it holds.
#[inline(always)]
fn split_be(x: u64) -> (u64, u64) {
    let x = ((x & 0x00ff_00ff_00ff_00ff) << 8) | ((x >> 8) & 0x00ff_00ff_00ff_00ff);
    let x = ((x & 0x0000_ffff_0000_ffff) << 16) | ((x >> 16) & 0x0000_ffff_0000_ffff);
    (x & 0xffff_ffff, x >> 32)
}

fn block_from_bytes(w: &mut W, b: &[u8]) {
    for j in 0..16 {
        w.0[j] = u32::from_be_bytes([b[4 * j], b[4 * j + 1], b[4 * j + 2], b[4 * j + 3]]) as u64;
    }
}

/// SHA-256 of `buf[start..start + len]`. `buf` is the whole allocation the
/// message lives in; whole-word reads may touch up to 7 bytes past the message
/// but never past the end of `buf` rounded down to a word.
#[cfg(not(all(any(feature = "risc0", feature = "openvm"), target_os = "zkvm", target_arch = "riscv32")))]
pub fn sha256_in(buf: &[u8], start: usize, len: usize) -> [u8; 32] {
    assert!(start + len <= buf.len());
    let mut st = H0;
    let mut w = W([0; 64]);
    let nblocks = len / 64;
    let base = buf.as_ptr() as usize;
    let p = base + start;
    let shift = (p & 7) as u32 * 8;
    let aligned = (p & !7) as *const u64;
    // Last word index any block read touches must stay inside buf.
    let words_needed = if shift == 0 { nblocks * 8 } else { nblocks * 8 + 1 };
    let fast =
        nblocks > 0 && aligned as usize >= base && (aligned as usize + words_needed * 8) <= base + (buf.len() & !7);
    let mut done = 0;
    if fast {
        unsafe {
            if shift == 0 {
                for blk in 0..nblocks {
                    let src = aligned.add(blk * 8);
                    for i in 0..8 {
                        let (a, b) = split_be(*src.add(i));
                        w.0[2 * i] = a;
                        w.0[2 * i + 1] = b;
                    }
                    compress(&mut w, &mut st);
                }
            } else {
                let rs = 64 - shift;
                let mut prev = *aligned;
                for blk in 0..nblocks {
                    let src = aligned.add(blk * 8 + 1);
                    for i in 0..8 {
                        let next = *src.add(i);
                        let (a, b) = split_be((prev >> shift) | (next << rs));
                        w.0[2 * i] = a;
                        w.0[2 * i + 1] = b;
                        prev = next;
                    }
                    compress(&mut w, &mut st);
                }
            }
        }
        done = nblocks;
    }
    let msg = &buf[start..start + len];
    for blk in done..nblocks {
        block_from_bytes(&mut w, &msg[blk * 64..blk * 64 + 64]);
        compress(&mut w, &mut st);
    }
    // Padding: 0x80, zeros, 64-bit big-endian bit length.
    let rem = &msg[nblocks * 64..];
    let mut tail = [0u8; 128];
    tail[..rem.len()].copy_from_slice(rem);
    tail[rem.len()] = 0x80;
    let tl = if rem.len() < 56 { 64 } else { 128 };
    tail[tl - 8..tl].copy_from_slice(&((len as u64) * 8).to_be_bytes());
    for blk in 0..tl / 64 {
        block_from_bytes(&mut w, &tail[blk * 64..blk * 64 + 64]);
        compress(&mut w, &mut st);
    }
    let mut out = [0u8; 32];
    for i in 0..8 {
        out[4 * i..4 * i + 4].copy_from_slice(&(st[i] as u32).to_be_bytes());
    }
    out
}

pub fn sha256(msg: &[u8]) -> [u8; 32] {
    sha256_in(msg, 0, msg.len())
}

#[cfg(all(feature = "risc0", target_os = "zkvm", target_arch = "riscv32"))]
pub use risc0::sha256_in;

/// RISC Zero SHA-256: the accelerator takes the state as the digest bytes
/// (each word byte-swapped) and reads 64-byte blocks straight from
/// word-aligned memory, so an aligned message is hashed in place and an
/// unaligned one is copied through an aligned chunk first.
#[cfg(all(feature = "risc0", target_os = "zkvm", target_arch = "riscv32"))]
mod risc0 {
    use risc0_zkvm_platform::syscall::sys_sha_buffer;

    const CHUNK_BLOCKS: usize = 64;

    #[repr(align(4))]
    struct Aligned<const N: usize>([u8; N]);

    #[inline(always)]
    fn absorb(st: &mut [u32; 8], p: *const u8, nblocks: usize) {
        if nblocks > 0 {
            let s: *mut [u32; 8] = st;
            unsafe { sys_sha_buffer(s, s, p, nblocks as u32) }
        }
    }

    pub fn sha256_in(buf: &[u8], start: usize, len: usize) -> [u8; 32] {
        assert!(start + len <= buf.len());
        let msg = &buf[start..start + len];
        let mut st = super::H0.map(|h| (h as u32).swap_bytes());
        let nblocks = len / 64;
        if msg.as_ptr() as usize % 4 == 0 {
            absorb(&mut st, msg.as_ptr(), nblocks);
        } else {
            let mut chunk = Aligned([0u8; CHUNK_BLOCKS * 64]);
            for blocks in msg[..nblocks * 64].chunks(CHUNK_BLOCKS * 64) {
                chunk.0[..blocks.len()].copy_from_slice(blocks);
                absorb(&mut st, chunk.0.as_ptr(), blocks.len() / 64);
            }
        }
        // Padding: 0x80, zeros, 64-bit big-endian bit length.
        let rem = &msg[nblocks * 64..];
        let mut tail = Aligned([0u8; 128]);
        tail.0[..rem.len()].copy_from_slice(rem);
        tail.0[rem.len()] = 0x80;
        let tl = if rem.len() < 56 { 64 } else { 128 };
        tail.0[tl - 8..tl].copy_from_slice(&((len as u64) * 8).to_be_bytes());
        absorb(&mut st, tail.0.as_ptr(), tl / 64);
        let mut out = [0u8; 32];
        for i in 0..8 {
            out[4 * i..4 * i + 4].copy_from_slice(&st[i].to_le_bytes());
        }
        out
    }
}

#[cfg(all(feature = "openvm", target_os = "zkvm", target_arch = "riscv32"))]
pub use openvm::sha256_in;

/// OpenVM SHA-256: `zkvm_sha256_impl` takes the state as native `u32` words
/// and one raw 64-byte block, so the message blocks are passed in place (the
/// intrinsic copies an unaligned block through an aligned buffer itself).
#[cfg(all(feature = "openvm", target_os = "zkvm", target_arch = "riscv32"))]
mod openvm {
    use openvm_sha2_guest::zkvm_sha256_impl;

    #[repr(align(4))]
    struct Aligned<const N: usize>([u8; N]);

    #[inline(always)]
    fn absorb(st: &mut [u32; 8], block: *const u8) {
        let s = st.as_mut_ptr() as *mut u8;
        unsafe { zkvm_sha256_impl(s, block, s) }
    }

    pub fn sha256_in(buf: &[u8], start: usize, len: usize) -> [u8; 32] {
        assert!(start + len <= buf.len());
        let msg = &buf[start..start + len];
        let mut st = super::H0.map(|h| h as u32);
        let nblocks = len / 64;
        for blk in 0..nblocks {
            absorb(&mut st, msg[blk * 64..].as_ptr());
        }
        // Padding: 0x80, zeros, 64-bit big-endian bit length.
        let rem = &msg[nblocks * 64..];
        let mut tail = Aligned([0u8; 128]);
        tail.0[..rem.len()].copy_from_slice(rem);
        tail.0[rem.len()] = 0x80;
        let tl = if rem.len() < 56 { 64 } else { 128 };
        tail.0[tl - 8..tl].copy_from_slice(&((len as u64) * 8).to_be_bytes());
        for blk in 0..tl / 64 {
            absorb(&mut st, tail.0[blk * 64..].as_ptr());
        }
        let mut out = [0u8; 32];
        for i in 0..8 {
            out[4 * i..4 * i + 4].copy_from_slice(&st[i].to_be_bytes());
        }
        out
    }
}
