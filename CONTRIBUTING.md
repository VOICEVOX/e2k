# 貢献者ガイド

## PRのタイトル

PRのタイトルは[Conventional Commits](https://www.conventionalcommits.org/ja/v1.0.0/)に従ってください。
また、変更を加えた部分をスコープの部分に記述してください。

### 例

- `feat(dataset): データセットの生成方式を追加`
- `chore(train): 学習中の表記を改善`
- `perf(infer, train): モデル構造を変えて高速化`

## モデル/データセットの更新

モデルやデータセットを更新する場合は、以下の手順に従ってください。

1. Hugging Faceの[VOICEVOX/e2k](https://huggingface.co/VOICEVOX/e2k)をcloneする。
2. モデル/データセットの更新を行う。
3. PRを作成し、マージする。
4. `git tag v{バージョン番号}`でタグを打つ。
5. `git push origin v{バージョン番号}`でタグをpushする。
6. `infer/crates/e2k-rs/build.rs`の`MODEL_TAG`を更新する。

---

（TODO：その他の項目を書く）
