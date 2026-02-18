# financial-report

有価証券報告書（PDF）から企業分析レポート（Word）を自動生成するパイプラインです。
Azure OpenAI（gpt-5-mini）を活用し、建設業・地域企業に特化した経営課題の抽出と施策提案を行います。

## パイプライン概要

```
PDF + 財務CSV
    ↓
Stage 1: Report Extraction    ─ PDF → テキスト抽出 → ページ別タグ付け + 財務指標算出
    ↓
Stage 2: Issue Extraction      ─ タグ別5段階スコアリング + 地域的特徴抽出
    ↓
Stage 3: Solution Selection    ─ 9施策候補から優先度つき3施策を選定
    ↓
Stage 4: Roadmaps              ─ 効果試算・実行ロードマップ・リスク対応策
    ↓
Stage 5: Executive Summary     ─ エグゼクティブサマリー生成
    ↓
Stage 6: Final Assembly        ─ 全結果を1つのJSONに統合
    ↓
Stage 7: JSON → DOCX           ─ Word文書に変換
```

## ファイル構成

```
.
├── app/
│   ├── run_pipeline.py                          # 統合パイプライン（全Stage一括実行）
│   ├── report-extraction/                       # Stage 1: レポート抽出
│   │   ├── main.py                              #   エントリポイント
│   │   ├── securities_report_loader.py          #   PDF → テキスト抽出（pypdf）
│   │   ├── securities_report_loader_pdfminer.py #   PDF → テキスト抽出（pdfminer）
│   │   ├── sorting.py                           #   ページ別タグ付け（11分類）
│   │   ├── financial_statements_loader.py       #   財務諸表CSV → JSON構造化
│   │   └── index_calcuration.py                 #   財務指標の自動算出（28指標）
│   ├── issue-extraction/                        # Stage 2: 課題抽出
│   │   ├── main.py                              #   エントリポイント
│   │   ├── section_sort.py                      #   タグ別テキスト統合（11→8分類）
│   │   ├── issue_extraction.py                  #   タグ別スコアリング + 総括生成
│   │   ├── local_feature_extraction.py          #   地域的特徴の抽出（3カテゴリ+統合）
│   │   └── build_fewshot.py                     #   few-shot例の構築
│   ├── solution-selection/                      # Stage 3-5: 施策提案
│   │   ├── solution_selection.py                #   施策選定（9候補→3施策）
│   │   ├── roadmaps.py                          #   効果試算・ロードマップ・リスク生成
│   │   └── executive_summary.py                 #   エグゼクティブサマリー生成
│   ├── final-assembly/                          # Stage 6: 最終統合
│   │   └── main.py                              #   全結果のJSON統合
│   └── json-to-docx/                            # Stage 7: Word変換
│       └── json-to-docx.py                      #   JSON → DOCX変換
├── data/
│   ├── input/                                   # 入力データ
│   │   ├── securities-reports/                  #   有価証券報告書PDF
│   │   ├── financial-statements/                #   財務諸表CSV
│   │   ├── fewshot/                             #   few-shot例（スコアリング参考）
│   │   └── solution.json                        #   施策候補マスタ（9施策）
│   ├── medium-output/                           # 中間出力
│   │   ├── report-extraction/                   #   タグ付きJSON・財務指標
│   │   ├── issue-extraction/                    #   スコア・地域特徴
│   │   └── solution-selection/                  #   施策選定・ロードマップ
│   └── final-output/                            # 最終出力
│       ├── executive-summary-per-company/       #   エグゼクティブサマリーJSON
│       ├── final-report-per-company/            #   最終レポートJSON
│       └── 手島進之介(teshimashinnosuke)/       #   提出用Word文書
├── pyproject.toml
├── .env.example
└── .python-version                              # Python 3.12
```

## セットアップ

### 1. リポジトリをクローン

```bash
git clone https://github.com/teshima-shinnosuke/financial-report.git
cd financial-report
```

### 2. Python環境の構築

```bash
uv sync
```

### 3. 環境変数の設定

`.env.example` を参考に `.env` ファイルを作成してください。

```bash
cp .env.example .env
```

```
AZURE_OPENAI_API_KEY=your_azure_openai_api_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
```

## 実行方法

### 一括実行（推奨）

```bash
# 対話モード（各ステージの間で確認あり）
uv run app/run_pipeline.py -i data/input/securities-reports/有価証券報告書（12044）.pdf

# 確認なしで全ステージ実行
uv run app/run_pipeline.py -i data/input/securities-reports/有価証券報告書（12044）.pdf --yes

# 企業コード明示 + 財務CSV指定
uv run app/run_pipeline.py -i 有報.pdf -c 12044 --csv data/input/financial-statements/12044.csv
```

### 途中再開

```bash
# Stage 4 から再開（前回の実行IDを指定）
uv run app/run_pipeline.py \
    -i data/input/securities-reports/有報.pdf \
    --run-id 12044_20260211_223000 \
    --start-stage 4
```

### 個別ステージ実行

```bash
# Stage 1: Report Extraction
uv run app/report-extraction/main.py -i 有報.pdf -c 12044

# Stage 2: Issue Extraction
uv run app/issue-extraction/main.py -i report_tagged_12044.json -m gpt-5-mini

# Stage 3: Solution Selection
uv run app/solution-selection/solution_selection.py -s scores.json -f features.json

# Stage 4: Roadmaps
uv run app/solution-selection/roadmaps.py -s selection.json

# Stage 5: Executive Summary
uv run app/solution-selection/executive_summary.py -c 12044 \
    --local-features features.json --report-scores scores.json \
    --selection selection.json --roadmap roadmap.json

# Stage 6: Final Assembly
uv run app/final-assembly/main.py --code 12044 \
    --executive-summary exec.json --local-features features.json \
    --report-scores scores.json --solution-selection selection.json \
    --roadmap roadmap.json

# Stage 7: JSON → DOCX
uv run app/json-to-docx/json-to-docx.py -i final_report_12044.json
```

### オプション

| オプション | 説明 |
|---|---|
| `-i`, `--input` | 入力PDFファイルパス |
| `-c`, `--code` | 企業コード（未指定時はファイル名から自動抽出） |
| `--csv` | 財務諸表CSVファイルパス |
| `-m`, `--model` | 使用するモデルID（デフォルト: `gpt-5-mini`） |
| `--no-fewshot` | few-shot例を使用しない |
| `-y`, `--yes` | 確認なしで全ステージ実行 |
| `--start-stage` | 開始ステージ番号（1-7） |
| `--run-id` | 既存の実行ID（途中再開時に指定） |

## 依存ライブラリ

| ライブラリ | 用途 |
|---|---|
| `openai` | Azure OpenAI API呼び出し |
| `pypdf` | PDF テキスト抽出 |
| `pdfminer-six` | PDF テキスト抽出（代替） |
| `python-docx` | Word文書生成 |
| `python-dotenv` | 環境変数管理 |
| `json-repair` | 壊れたJSONレスポンスの自動修復 |

## ブランチ運用ルール

```text
main        ← 本番用（直接pushしない）
└── develop ← 開発統合用（各自の作業をここにマージ）
     └── feature-igaken （個人作業用）
     └── feature-teshi（個人作業用���
```
