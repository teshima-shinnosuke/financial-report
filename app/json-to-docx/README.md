# JSON to DOCX 変換

要約済みJSONファイルからDOCXファイルを生成します。

## 実行方法

```bash
uv run app/json-to-docx/json-to-docx.py
```

### オプション

```bash
# 入力・出力ファイルを指定する場合
uv run app/json-to-docx/json-to-docx.py -i 入力.json -o 出力.docx
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `-i`, `--input` | 入力JSONファイルのパス | `app/security_report_summarize.json.bak` |
| `-o`, `--output` | 出力DOCXファイルのパス | `app/json-to-docx/output.docx` |
