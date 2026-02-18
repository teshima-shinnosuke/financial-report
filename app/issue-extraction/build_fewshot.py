"""
ゴールデンデータからタグ単位のfew-shot例を生成するスクリプト。

入力:
  - data/input/fewshot/sorted_by_tag_*.json（タグ並び替え済みデータ）
  - data/input/fewshot/report_scores_*.json（手修正済みスコアデータ）

出力:
  - data/input/fewshot/fewshot.json（タグ単位のfew-shot例、JSON形式）
"""

import json
import os
import glob
import argparse


def build_fewshot(sorted_path: str, scores_path: str) -> list[dict]:
    """1組のソート済みデータ + スコアデータからfew-shot例を生成する。"""
    with open(sorted_path, "r", encoding="utf-8") as f:
        sorted_report = json.load(f)
    if isinstance(sorted_report, list):
        sorted_report = sorted_report[0]

    with open(scores_path, "r", encoding="utf-8") as f:
        scores_data = json.load(f)
    if isinstance(scores_data, list):
        scores_data = scores_data[0]

    # スコアデータをタグ名で辞書化
    scores_map = {}
    for score_entry in scores_data.get("scores", []):
        scores_map[score_entry["tag"]] = score_entry

    examples = []
    for tag_group in sorted_report.get("tags", []):
        tag = tag_group["tag"]
        if tag not in scores_map:
            continue

        score_entry = scores_map[tag]
        examples.append({
            "tag": tag,
            "input_sections": tag_group.get("sections", []),
            "expected_output": {
                "items": score_entry.get("items", []),
                "summary": score_entry.get("summary", ""),
            },
        })

    return examples


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fewshot_dir = os.path.join(base_dir, "data", "input", "fewshot")
    default_output = os.path.join(fewshot_dir, "fewshot.json")

    parser = argparse.ArgumentParser(description="ゴールデンデータからfew-shot例を生成する")
    parser.add_argument("-o", "--output", default=default_output, help="出力JSONファイルパス")
    args = parser.parse_args()

    # fewshot ディレクトリ内の全ペアを探索
    sorted_files = sorted(glob.glob(os.path.join(fewshot_dir, "sorted_by_tag_*.json")))
    if not sorted_files:
        print(f"ソート済みファイルが見つかりません: {fewshot_dir}")
        return

    all_examples = []
    for sorted_path in sorted_files:
        # sorted_by_tag_XXX.json → report_scores_XXX.json
        basename = os.path.basename(sorted_path)
        company = basename.replace("sorted_by_tag_", "").replace(".json", "")
        scores_path = os.path.join(fewshot_dir, f"report_scores_{company}.json")

        if not os.path.exists(scores_path):
            print(f"  スキップ（スコアファイルなし）: {company}")
            continue

        print(f"  処理中: {company}")
        examples = build_fewshot(sorted_path, scores_path)
        all_examples.extend(examples)
        print(f"    -> {len(examples)} タグ分のfew-shot例を生成")

    # JSON形式で出力
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_examples, f, indent=2, ensure_ascii=False)

    print(f"\n合計 {len(all_examples)} 件のfew-shot例を保存しました: {args.output}")


if __name__ == "__main__":
    main()
