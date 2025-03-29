#[test]
fn test_c2k() {
    let src = "constants";

    let c2k = e2k::C2k::new();
    let dst = c2k.infer(src);
    dbg!(dst);
}

#[test]
fn test_c2k_empty() {
    let src = "";

    let c2k = e2k::C2k::new();
    let dst = c2k.infer(src);
    assert_eq!(dst, "");
}

#[test]
fn test_c2k_long() {
    let src = "pneumonoultramicroscopicsilicovolcanoconiosis";

    let unlimited_c2k = e2k::C2k::new();
    let limited_c2k = e2k::C2k::new().with_max_length(10);
    let unlimited_dst = unlimited_c2k.infer(src);
    let limited_dst = limited_c2k.infer(src);
    assert_ne!(unlimited_dst, limited_dst);
    assert_eq!(limited_dst.chars().count(), 10);
}
