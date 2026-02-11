from pypdf import PdfReader
import os
import json
import argparse


def load_pages(file_path: str) -> list[dict]:
    """
    PDFファイルからページ単位でテキストを抽出する。

    Args:
        file_path (str): PDFファイルのパス

    Returns:
        list[dict]: [{"page": 1, "text": "..."}, ...]
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        reader = PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            # 冒頭の「架空・サンプルデータ」行を除去
            if text.startswith("架空・サンプルデータ\n"):
                text = text[len("架空・サンプルデータ\n"):]
            elif text.startswith("架空・サンプルデータ"):
                text = text[len("架空・サンプルデータ"):]
            pages.append({"page": i + 1, "text": text})
        return pages
    except Exception as e:
        print(f"Error reading PDF {file_path}: {e}")
        return []


def _extract_code(filename: str) -> str:
    import re
    match = re.search(r"(\d+)", filename)
    if match:
        return match.group(1)
    return re.sub(r"[^a-zA-Z0-9_]", "", os.path.splitext(filename)[0])


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    parser = argparse.ArgumentParser(description="1つのPDFからページ単位でテキストを抽出する")
    parser.add_argument("-i", "--input", required=True, help="入力PDFファイルパス")
    parser.add_argument("-o", "--output", default=None, help="出力JSONファイルパス（未指定時は自動生成）")
    args = parser.parse_args()

    if not os.path.isfile(args.input) or not args.input.lower().endswith(".pdf"):
        print(f"Error: PDFファイルを指定してください: {args.input}")
        exit(1)

    filename = os.path.basename(args.input)
    code = _extract_code(filename)
    pages = load_pages(args.input)
    print(f"{filename}: {len(pages)}ページ")

    result = {"filename": filename, "pages": pages}

    output_dir = os.path.join(base_dir, "data", "medium-output", "report-extraction", "report-pages")
    output_path = args.output or os.path.join(output_dir, f"report_pages_{code}.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, indent=2, ensure_ascii=False, fp=f)
    print(f"出力完了: {output_path}")
