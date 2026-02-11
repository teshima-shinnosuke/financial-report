"""pdfminer.six 版の securities_report_loader（一時利用）"""

from pdfminer.high_level import extract_text
import os
import json
import argparse


def load_pages(file_path: str) -> list[dict]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        pages = []
        for i in range(count_pages(file_path)):
            text = extract_text(file_path, page_numbers=[i]) or ""
            if text.startswith("架空・サンプルデータ\n"):
                text = text[len("架空・サンプルデータ\n"):]
            elif text.startswith("架空・サンプルデータ"):
                text = text[len("架空・サンプルデータ"):]
            pages.append({"page": i + 1, "text": text.strip()})
        return pages
    except Exception as e:
        print(f"Error reading PDF {file_path}: {e}")
        return []


def count_pages(file_path: str) -> int:
    from pdfminer.pdfpage import PDFPage
    with open(file_path, "rb") as f:
        return sum(1 for _ in PDFPage.get_pages(f))


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_input = os.path.join(base_dir, "data", "input", "securities-reports")
    default_output = os.path.join(base_dir, "data", "medium-output", "report-extraction", "securities_report_pages.json")

    parser = argparse.ArgumentParser(description="PDFからページ単位でテキストを抽出する（pdfminer版）")
    parser.add_argument("-i", "--input", default=default_input, help="PDFファイルまたはディレクトリのパス")
    parser.add_argument("-o", "--output", default=default_output, help="出力JSONファイルパス")
    args = parser.parse_args()

    input_path = args.input
    if os.path.isfile(input_path):
        pdf_files = [input_path]
    elif os.path.isdir(input_path):
        pdf_files = [os.path.join(input_path, f) for f in sorted(os.listdir(input_path)) if f.lower().endswith('.pdf')]
    else:
        print(f"Error: Input path not found: {input_path}")
        pdf_files = []

    results = []
    for pdf_path in pdf_files:
        pages = load_pages(pdf_path)
        results.append({"filename": os.path.basename(pdf_path), "pages": pages})
        print(f"{os.path.basename(pdf_path)}: {len(pages)}ページ")

    if results:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, indent=2, ensure_ascii=False, fp=f)
        print(f"出力完了: {args.output} ({len(results)}ファイル)")
