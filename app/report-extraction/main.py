import os
import sys
import json
import time
import re
import logging
import argparse

# 同ディレクトリの summarizer, loader をインポート
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from summarizer import summarize_all_strategies, STRATEGIES
from loader import PDFLoader

from dotenv import load_dotenv


def main():
    load_dotenv()

    if not os.getenv("HF_TOKEN"):
        print("Warning: HF_TOKEN is not set in environment variables. Please set it in .env file.")

    # 引数パース（app/issue-extraction/ → app/ → プロジェクトルート）
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_data_dir = os.path.join(base_dir, "data", "input", "security")

    default_output = os.path.join(base_dir, "data", "medium-output", "security_report_summarize.json")

    parser = argparse.ArgumentParser(description='Summarize financial reports.')
    parser.add_argument('-i', '--input', default=default_data_dir,
                        help='Path to a PDF file or a directory containing PDFs')
    parser.add_argument('-o', '--output', default=default_output,
                        help='Output JSON file path')
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

    # ログ設定
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processing.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
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
        summaries = item.get("summaries", {})
        if isinstance(summaries, dict) and "error" not in summaries and "企業概要" in summaries:
            processed_map[item["filename"]] = i

    loader = PDFLoader()

    for file_path in pdf_files:
        filename = os.path.basename(file_path)

        # 既に成功して処理済みならスキップ
        if filename in processed_map:
            logger.info(f"Skipping {filename} (already successfully processed).")
            continue

        logger.info(f"Processing: {filename}...")

        # PDFからテキスト抽出（全ページ）
        try:
            text = loader.load_text(file_path)
        except Exception as e:
            logger.error(f"  -> Failed to extract text: {e}")
            continue

        if not text:
            logger.warning(f"  -> Extracted text is empty.")
            continue

        logger.info(f"  -> Extracted {len(text)} chars. Summarizing (API Call)...")

        # APIのレート制限回避
        time.sleep(2)

        # 要約実行
        json_str = summarize_all_strategies(text)

        # JSONパース
        extracted_summaries = {}
        try:
            match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if match:
                extracted_summaries = json.loads(match.group(0))
            else:
                raise json.JSONDecodeError("No JSON object found", json_str, 0)
            logger.info(f"  -> Successfully summarized.")
        except json.JSONDecodeError:
            logger.error(f"  !! Failed to parse JSON response. Saving raw output.")
            extracted_summaries = {
                "error": "JSON parse error",
                "raw_output": json_str,
            }
            for s in STRATEGIES:
                extracted_summaries.setdefault(s, "取得失敗")

        # エラーチェック（API課金エラー等）
        if "error" in extracted_summaries and isinstance(extracted_summaries, dict):
            error_msg = str(extracted_summaries.get("error", ""))
            raw_out = str(extracted_summaries.get("raw_output", ""))
            if "402" in error_msg or "Payment Required" in raw_out:
                logger.critical("  !! API Quota Exceeded. Stopping processing.")
                return

        file_summary = {
            "filename": filename,
            "full_text": text,
            "summaries": extracted_summaries,
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

    logger.info(f"All processing completed. Saved to {output_file}")


if __name__ == "__main__":
    main()
