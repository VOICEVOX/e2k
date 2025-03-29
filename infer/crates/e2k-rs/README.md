# e2k-rs

推論コードのRust実装。

## 使い方

```rust
// 文字列をカタカナに変換する例
let src = "constants";
let c2k = e2k::C2k::new();
let dst = c2k.infer(src);

dbg!(dst); // "コンスタンツ"
```

## ライセンス

MIT License にて公開しています。
