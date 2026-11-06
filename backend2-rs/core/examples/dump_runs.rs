//! Print the decoded text runs of a report PDF (debugging the extraction rules).
//! `cargo run -p equinox-core --example dump_runs --features std -- <pdf>`
fn main() {
    let path = std::env::args().nth(1).expect("pdf path");
    let mut buf = std::fs::read(path).unwrap();
    buf.extend_from_slice(&[0u8; equinox_core::BLINDER_LEN]);
    let r = std::panic::catch_unwind(|| equinox_core::run(&buf, &[]));
    match r {
        Ok(out) => {
            for (i, run) in out.runs.iter().enumerate() {
                println!("{i:4} {run:?}");
            }
            println!("pii words: {:?}", out.pii);
        }
        Err(_) => println!("run() panicked"),
    }
}
