import os
import sys
import re
import json
import logging
import argparse

# 同ディレクトリの summarizer, loader をインポート
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sorting import tag_pages
from securities_report_loader import load_pages
from financial_statements_loader import load_financial_data
from index_calcuration import calculate_indices

from dotenv import load_dotenv


def _extract_code(filename: str) -> str:
    """ファイル名から企業コードを抽出する。数字がなければファイル名ベースで生成。"""
    match = re.search(r"(\d+)", filename)
    if match:
        return match.group(1)
    return re.sub(r"[^a-zA-Z0-9_]", "", os.path.splitext(filename)[0])


def main():
    load_dotenv()

    if not os.getenv("AZURE_OPENAI_API_KEY") or not os.getenv("AZURE_OPENAI_ENDPOINT"):
        print("Warning: AZURE_OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT is not set. Please set them in .env file.")

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    default_csv = os.path.join(base_dir, "data", "input", "financial-statements", "financial_data.csv")

    parser = argparse.ArgumentParser(description="1企業のPDF抽出・タグ付け＋財務諸表・指標算出を実行する")
    parser.add_argument("-i", "--input", required=True,
                        help="入力PDFファイルパス")
    parser.add_argument("-c", "--code", default=None,
                        help="企業コード（未指定時はファイル名から自動抽出）")
    parser.add_argument("--csv", default=default_csv,
                        help="財務諸表CSVファイルパス")
    parser.add_argument("-o", "--output", default=None,
                        help="タグ付け出力JSONファイルパス（未指定時は自動生成）")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    logger = logging.getLogger(__name__)

    input_path = args.input
    if not os.path.isfile(input_path) or not input_path.lower().endswith(".pdf"):
        logger.error(f"PDFファイルを指定してください: {input_path}")
        return

    filename = os.path.basename(input_path)
    code = args.code or _extract_code(filename)
    logger.info(f"対象ファイル: {filename} (コード: {code})")

    # ========================================
    # 1. PDF → ページ抽出 → タグ付け
    # ========================================
    logger.info("[1/3] ページ抽出中...")
    pages = load_pages(input_path)
    if not pages:
        logger.error("抽出されたページが空です。")
        return
    logger.info(f"  {len(pages)} ページ抽出完了。タグ付け中...")

    tagged_pages = tag_pages(pages, batch_size=5)
    logger.info(f"  {len(tagged_pages)} ページのタグ付け完了。")

    tagged_result = {
        "filename": filename,
        "pages": tagged_pages,
    }

    tagged_dir = os.path.join(
        base_dir, "data", "medium-output", "report-extraction", "report-tagged-per-company"
    )
    tagged_path = args.output or os.path.join(tagged_dir, f"report_tagged_{code}.json")
    os.makedirs(os.path.dirname(tagged_path), exist_ok=True)
    with open(tagged_path, "w", encoding="utf-8") as f:
        json.dump(tagged_result, f, indent=2, ensure_ascii=False)
    logger.info(f"  保存: {tagged_path}")

    # ========================================
    # 2. 財務諸表CSV → JSON
    # ========================================
    logger.info("[2/3] 財務諸表CSV → JSON...")
    csv_path = args.csv
    if not os.path.exists(csv_path):
        logger.warning(f"  CSVファイルが見つかりません: {csv_path}（スキップ）")
    else:
        fs_data = load_financial_data(csv_path, company_code=code)
        if not fs_data:
            logger.warning(f"  企業コード '{code}' のデータがCSVに見つかりません（スキップ）")
        else:
            fs_dir = os.path.join(
                base_dir, "data", "medium-output", "report-extraction", "financial-statements-per-company"
            )
            fs_path = os.path.join(fs_dir, f"financial_statements_{code}.json")
            os.makedirs(fs_dir, exist_ok=True)
            with open(fs_path, "w", encoding="utf-8") as f:
                json.dump(fs_data, f, indent=2, ensure_ascii=False)
            logger.info(f"  保存: {fs_path}")

            # ========================================
            # 3. 財務諸表 → 指標算出
            # ========================================
            logger.info("[3/3] 財務指標算出中...")
            company_data = fs_data[code]
            indices = calculate_indices(company_data)

            idx_dir = os.path.join(
                base_dir, "data", "medium-output", "report-extraction", "financial-indices-per-company"
            )
            idx_path = os.path.join(idx_dir, f"financial_indices_{code}.json")
            os.makedirs(idx_dir, exist_ok=True)
            with open(idx_path, "w", encoding="utf-8") as f:
                json.dump(indices, f, indent=2, ensure_ascii=False)
            logger.info(f"  保存: {idx_path}")

    logger.info("全処理完了。")


if __name__ == "__main__":
    main()
