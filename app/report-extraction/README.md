# report-extraction

有価証券報告書（PDF）と財務諸表（CSV）から構造化データを抽出するモジュール。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `main.py` | エントリーポイント。PDF タグ付け → 財務諸表変換を一括実行 |
| `securities_report_loader.py` | PDF からページ単位でテキストを抽出 |
| `sorting.py` | HuggingFace API でページ内セクションにタグを付与 |
| `financial_statements_loader.py` | 財務諸表 CSV を階層構造の JSON に変換 |

## 処理フロー

```
1. securities_report_loader  : PDF → [{"page": 1, "text": "..."}]
2. sorting (tag_pages)       : LLM API で各ページをセクション分割・タグ付け
3. financial_statements_loader: CSV → 企業ごとの PL/BS/CF 構造化 JSON
```

## 実行方法

```bash
# 全処理を一括実行（デフォルトパス使用）
uv run app/report-extraction/main.py

# PDF入力・出力を指定
uv run app/report-extraction/main.py -i data/input/securities-reports -o data/medium-output/security_report_summarize.json

# 財務諸表CSV・出力を指定
uv run app/report-extraction/main.py --csv data/input/financial-statements/financial_data.csv --fs-output data/medium-output/financial_statements.json

# 財務諸表のみ単体実行
uv run app/report-extraction/financial_statements_loader.py
```

## 引数一覧（main.py）

| 引数 | デフォルト | 説明 |
|---|---|---|
| `-i`, `--input` | `data/input/securities-reports` | PDF ファイルまたはディレクトリ |
| `-o`, `--output` | `data/medium-output/security_report_summarize.json` | 有報タグ付き JSON 出力先 |
| `--csv` | `data/input/financial-statements/financial_data.csv` | 財務諸表 CSV |
| `--fs-output` | `data/medium-output/financial_statements.json` | 財務諸表 JSON 出力先 |

## タグ分類（有価証券報告書）

sorting.py で使用する 8分類 + その他:

1. 経営戦略・中期ビジョン
2. 事業・営業・受注戦略
3. 生産性・施工オペレーション
4. 人的資本・組織運営
5. 技術・DX・研究開発
6. サステナビリティ・社会的責任
7. 財務・資本政策・ガバナンス
8. リスクマネジメント・コンプライアンス
9. その他

## 出力形式

### 有価証券報告書（security_report_summarize.json）

```json
[
  {
    "filename": "有価証券報告書（12044）.pdf",
    "pages": [
      {
        "page": 1,
        "sections": [
          {"tag": "その他", "text": "有価証券報告書 提出日..."}
        ]
      }
    ]
  }
]
```

### 財務諸表（financial_statements.json）

```json
{
  "12044": {
    "企業情報": {
      "コード": "12044",
      "本社所在地": "...",
      "業種分類": "..."
    },
    "財務データ": [
      {
        "YEAR": 2023,
        "損益計算書": { "売上高": {...}, "営業利益": ... },
        "貸借対照表": { "資産": {...}, "負債・純資産": {...} },
        "キャッシュ・フロー計算書": { ... }
      }
    ]
  }
}
```

## 環境変数

- `HF_TOKEN`: HuggingFace API トークン（`.env` に設定）
