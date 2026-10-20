pub fn first(v: &[u32]) -> u32 {
    v.iter().max().unwrap() + v[0]
}

pub fn read(p: *const u8) -> u8 {
    unsafe { *p }
}
