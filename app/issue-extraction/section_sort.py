import json
import os
import re
import argparse
from collections import defaultdict


FINANCIAL_TAG = "財務・資本政策・ガバナンス"

# sorting.py と同じタグ順序（括弧内を除いた短縮名）
TAG_ORDER = [
    "経営戦略・中期ビジョン",
    "事業・営業・受注戦略",
    "生産性・施工オペレーション",
    "人的資本・組織運営",
    "技術・DX・研究開発",
    "サステナビリティ・社会的責任",
    "財務・資本政策・ガバナンス",
    "リスクマネジメント・コンプライアンス",
    "その他",
]

def _extract_code(filename: str) -> str | None:
    """ファイル名から企業コード（括弧内の数字）を抽出する。"""
    match = re.search(r"[（(](\d+)[）)]", filename)
    return match.group(1) if match else None


def sort_by_tag(report: dict, indices: dict | None = None) -> dict:
    """
    1つの報告書データ（ページ単位構造）をタグ単位構造に並び替える。
    indices が指定された場合、財務タグに財務指標データを追加する。

    入力:
        {"filename": "...", "pages": [{"page": 1, "sections": [{"tag": "...", "text": "..."}, ...]}, ...]}

    出力:
        {"filename": "...", "tags": [{"tag": "...", "sections": [...], "financial_indices": {...}}, ...]}
    """
    tag_sections = defaultdict(list)

    for page in report.get("pages", []):
        page_num = page.get("page")
        for section in page.get("sections", []):
            tag = section.get("tag", "その他")
            text = section.get("text", "")
            tag_sections[tag].append({"page": page_num, "text": text})

    # TAG_ORDER の順序でソートし、未知のタグは末尾に追加
    tag_order_map = {tag: i for i, tag in enumerate(TAG_ORDER)}

    if indices and FINANCIAL_TAG not in tag_sections:
        tag_sections[FINANCIAL_TAG] = []

    sorted_tags = sorted(
        tag_sections.keys(),
        key=lambda t: tag_order_map.get(t, len(TAG_ORDER)),
    )

    tags_list = []
    for tag in sorted_tags:
        entry = {"tag": tag, "sections": tag_sections[tag]}
        if tag == FINANCIAL_TAG and indices:
            entry["financial_indices"] = indices
        tags_list.append(entry)

    return {
        "filename": report.get("filename", ""),
        "tags": tags_list,
    }


def sort_reports(
    reports: list[dict],
    indices_map: dict | None = None,
    batch_size: int = 3,
    output_path: str | None = None,
) -> list[dict]:
    """
    複数の報告書データをまとめてタグ単位に並び替える。
    batch_size 件ずつ処理し、output_path が指定されていれば中間保存する。

    Args:
        reports: report_summarize_tmp.json のデータ
        indices_map: financial_indices.json のデータ（企業コード -> 指標データ）
        batch_size: 1回の処理で扱う報告書数
        output_path: 中間保存先のファイルパス
    """
    # 既存結果の読み込み（中断再開用）
    results = []
    processed_filenames = set()
    if output_path and os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                results = json.load(f)
            processed_filenames = {r["filename"] for r in results}
            if processed_filenames:
                print(f"既存の処理済みデータを読み込みました: {len(processed_filenames)} 社")
        except (json.JSONDecodeError, KeyError):
            results = []

    # 未処理の報告書のみ抽出
    pending = [r for r in reports if r.get("filename", "") not in processed_filenames]
    if not pending:
        print("全ての報告書が処理済みです。")
        return results

    print(f"処理対象: {len(pending)} 社（全{len(reports)} 社中）")

    for i in range(0, len(pending), batch_size):
        batch = pending[i:i + batch_size]
        batch_names = [r.get("filename", "不明") for r in batch]
        print(f"  バッチ {i // batch_size + 1}: {', '.join(batch_names)}")

        for report in batch:
            indices = None
            if indices_map:
                code = _extract_code(report.get("filename", ""))
                if code and code in indices_map:
                    indices = indices_map[code]
            results.append(sort_by_tag(report, indices))

        # バッチごとに中間保存
        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"    -> 中間保存完了（{len(results)}/{len(reports)} 社）")

    return results


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_input = os.path.join(base_dir, "data", "medium-output", "report-extraction", "report_summarize_tmp.json")
    default_indices = os.path.join(base_dir, "data", "medium-output", "report-extraction", "financial_indices.json")
    default_output = os.path.join(base_dir, "data", "medium-output", "issue-extraction", "report_sorted_by_tag.json")

    parser = argparse.ArgumentParser(description="報告書JSONをタグごとに並び替える")
    parser.add_argument("-i", "--input", default=default_input, help="入力JSONファイルパス")
    parser.add_argument("-f", "--financial-indices", default=default_indices, help="財務指標JSONファイルパス")
    parser.add_argument("-o", "--output", default=default_output, help="出力JSONファイルパス")
    parser.add_argument("--filename", default=None, help="特定のファイル名のみ処理する（部分一致）")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        reports = json.load(f)

    # --filename フィルタ
    if args.filename:
        reports = [r for r in reports if args.filename in r.get("filename", "")]
        print(f"フィルタ適用: '{args.filename}' に一致する {len(reports)} 件を処理")

    if not reports:
        print("処理対象の報告書が見つかりません。")
        return

    # 財務指標データの読み込み
    indices_map = None
    if os.path.exists(args.financial_indices):
        with open(args.financial_indices, "r", encoding="utf-8") as f:
            indices_map = json.load(f)
        print(f"財務指標データを読み込みました: {len(indices_map)} 社")
    else:
        print(f"財務指標ファイルが見つかりません（スキップ）: {args.financial_indices}")

    sorted_reports = sort_reports(reports, indices_map, output_path=args.output)

    print(f"タグごとに並び替えた結果を保存しました: {args.output}")
    for report in sorted_reports:
        print(f"  {report['filename']}: {len(report['tags'])} タグ")
        for tag_group in report["tags"]:
            idx_status = "（財務指標あり）" if "financial_indices" in tag_group else ""
            print(f"    - {tag_group['tag']}: {len(tag_group['sections'])} セク���ョン{idx_status}")


if __name__ == "__main__":
    main()
