#[test]
fn test_kana() {
    let src = "kanalizer";

    let kana = kanalizer::Kanalizer::new();
    let dst = kana.infer(src);
    assert_eq!(dst, "カナライザー");
}

#[test]
fn test_kana_empty() {
    let src = "";

    let kanalizer = kanalizer::Kanalizer::new();
    let dst = kanalizer.infer(src);
    assert_eq!(dst, "");
}

#[test]
fn test_kana_long() {
    let src = "pneumonoultramicroscopicsilicovolcanoconiosis";

    let unlimited_kanalizer = kanalizer::Kanalizer::new();
    let limited_kanalizer = kanalizer::Kanalizer::new().with_max_length(10);
    let unlimited_dst = unlimited_kanalizer.infer(src);
    let limited_dst = limited_kanalizer.infer(src);
    assert_ne!(unlimited_dst, limited_dst);
    assert_eq!(limited_dst.chars().count(), 10);
}
