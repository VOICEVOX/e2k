# e2k/train

学習用コードと推論のPython実装です。

## 実行

[uv](https://docs.astral.sh/uv/) が必要です。

### 学習

学習結果は `outputs/2025_03_14_23_43_01_example` のようなディレクトリに保存されます。
学習時の設定は `config/example.yml` を参照してください。

```bash
# 学習
uv run src/train.py ./config/example.yml
```

```bash
# Tensorboardを開く
uv run tensorboard --logdir outputs
```

### 評価

```bash
# UniDicをダウンロードし、英単語を抜き出す（初回のみ）
uv run src/setup_eval.py
```

```bash
# 評価
uv run src/eval.py ./outputs/2025_03_14_23_43_01_example
```

### 書き出し

safetensors形式で書き出します。

```bash
uv run src/export.py --model ./outputs/2025_03_14_23_43_01_example/model-e10.pth --output ./outputs/2025_03_14_23_43_01_example/model.safetensors
```

### フォーマット

```bash
uv run ruff check src/*.py

uv run ruff format src/*.py
```

## 謝辞

このディレクトリ下のコードは[Patchethium/e2k](https://github.com/Patchethium/e2k)のコードが元になっています。
