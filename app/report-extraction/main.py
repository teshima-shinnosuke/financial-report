import os
import sys
import json
import time
import logging
import argparse

# 同ディレクトリの summarizer, loader をインポート
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sorting import tag_pages
from securities_report_loader import load_pages
from financial_statements_loader import load_financial_data

from dotenv import load_dotenv


def main():
    load_dotenv()

    if not os.getenv("HF_TOKEN"):
        print("Warning: HF_TOKEN is not set in environment variables. Please set it in .env file.")

    # 引数パース（app/issue-extraction/ → app/ → プロジェクトルート）
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_data_dir = os.path.join(base_dir, "data", "input", "securities-reports")

    default_output = os.path.join(base_dir, "data", "medium-output", "security_report_summarize.json")

    # 財務諸表CSVのデフォルトパス
    default_csv = os.path.join(base_dir, "data", "input", "financial-statements", "financial_data.csv")
    default_fs_output = os.path.join(base_dir, "data", "medium-output", "financial_statements.json")

    parser = argparse.ArgumentParser(description='Extract and tag financial reports.')
    parser.add_argument('-i', '--input', default=default_data_dir,
                        help='Path to a PDF file or a directory containing PDFs')
    parser.add_argument('-o', '--output', default=default_output,
                        help='Output JSON file path for securities reports')
    parser.add_argument('--csv', default=default_csv,
                        help='Input CSV file path for financial statements')
    parser.add_argument('--fs-output', default=default_fs_output,
                        help='Output JSON file path for financial statements')
    args = parser.parse_args()

    input_path = args.input

    # PDFファイルの取得
    pdf_files = []
    if os.path.isfile(input_path):
        if input_path.lower().endswith('.pdf'):
            pdf_files.append(input_path)
        else:
            print(f"Error: {input_path} is not a PDF file.")
            return
    elif os.path.isdir(input_path):
        files = [os.path.join(input_path, f) for f in os.listdir(input_path) if f.lower().endswith('.pdf')]
        pdf_files.extend(files)
        if not pdf_files:
            print(f"No PDF files found in directory: {input_path}")
            return
        print(f"Found {len(pdf_files)} PDF files in {input_path}.\n")
    else:
        print(f"Error: Input path not found: {input_path}")
        return

    # ログ設定（コンソール出力のみ）
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger = logging.getLogger(__name__)

    # 出力ファイル
    output_file = args.output
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # 既存の結果があれば読み込む
    results = []
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
            logger.info(f"Loaded {len(results)} existing summaries.")
        except json.JSONDecodeError:
            logger.error("Existing JSON file is corrupt. Starting fresh.")
            results = []

    # 処理済みファイルの判定マップ
    processed_map = {}
    for i, item in enumerate(results):
        pages = item.get("pages", [])
        if pages and "sections" in pages[0]:
            processed_map[item["filename"]] = i

    for file_path in pdf_files:
        filename = os.path.basename(file_path)

        # 既に成功して処理済みならスキップ
        if filename in processed_map:
            logger.info(f"Skipping {filename} (already successfully processed).")
            continue

        logger.info(f"Processing: {filename}...")

        # PDFからページ単位でテキスト抽出
        try:
            pages = load_pages(file_path)
        except Exception as e:
            logger.error(f"  -> Failed to extract text: {e}")
            continue

        if not pages:
            logger.warning(f"  -> Extracted pages are empty.")
            continue

        logger.info(f"  -> Extracted {len(pages)} pages. Tagging (API Call)...")

        # ページ単位でセクション分割・タグ付け（5ページごとにAPIコール）
        tagged_pages = tag_pages(pages, batch_size=5)
        logger.info(f"  -> Tagged {len(tagged_pages)} pages.")

        file_summary = {
            "filename": filename,
            "pages": tagged_pages,
        }

        # 既存エントリーがあれば更新、なければ追加
        existing_index = next(
            (i for i, item in enumerate(results) if item["filename"] == filename), -1
        )
        if existing_index != -1:
            results[existing_index] = file_summary
        else:
            results.append(file_summary)

        # 1文書ごとに保存
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            logger.info(f"  -> Saved progress to {output_file}")
        except Exception as e:
            logger.error(f"Error saving to JSON: {e}")

        print("-" * 50 + "\n")
        time.sleep(5)

    logger.info(f"Securities report processing completed. Saved to {output_file}")

    # --- 財務諸表CSV → JSON変換 ---
    print("=" * 50)
    logger.info("Starting financial statements processing...")

    csv_path = args.csv
    if not os.path.exists(csv_path):
        logger.error(f"CSV file not found: {csv_path}")
    else:
        fs_output = args.fs_output
        os.makedirs(os.path.dirname(fs_output), exist_ok=True)

        data = load_financial_data(csv_path)
        with open(fs_output, "w", encoding="utf-8") as f:
            json.dump(data, indent=2, ensure_ascii=False, fp=f)
        logger.info(f"Financial statements saved to {fs_output} ({len(data)} companies)")

    logger.info("All processing completed.")


if __name__ == "__main__":
    main()
