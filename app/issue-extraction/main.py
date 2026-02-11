import os
import sys
import re
import json
import logging
import argparse

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from section_sort import sort_by_tag, _extract_code
from issue_extraction import score_report
from local_feature_extraction import extract_category_feature, extract_overall_feature, CATEGORY_TAG_MAP, _get_company_info

from dotenv import load_dotenv


def main():
    load_dotenv()

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    parser = argparse.ArgumentParser(description="1企業のタグ並び替え・スコアリング・地域特徴抽出を実行する")
    parser.add_argument("-i", "--input", required=True,
                        help="入力JSONファイル（report_tagged_*.json）")
    parser.add_argument("--indices", default=None,
                        help="財務指標JSONファイル（financial_indices_*.json）")
    parser.add_argument("-m", "--model", default="gpt-5-mini",
                        help="使用するモデルID")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    logger = logging.getLogger(__name__)

    # --- データ読み込み ---
    with open(args.input, "r", encoding="utf-8") as f:
        report = json.load(f)
    if isinstance(report, list):
        report = report[0]

    filename = report.get("filename", "")
    code = _extract_code(filename) or re.search(r"(\d+)", filename).group(1)
    logger.info(f"対象ファイル: {filename} (コード: {code})")

    # 財務指標の読み込み（任意）
    indices = None
    if args.indices and os.path.exists(args.indices):
        with open(args.indices, "r", encoding="utf-8") as f:
            indices_data = json.load(f)
        # {コード: {...}} 形式 or 直接データの場合
        if "企業情報" in indices_data:
            indices = indices_data
        elif code in indices_data:
            indices = indices_data[code]
        logger.info(f"  財務指標: あり")
    else:
        # デフォルトパスを探す
        default_indices = os.path.join(
            base_dir, "data", "medium-output", "report-extraction",
            "financial-indices-per-company", f"financial_indices_{code}.json"
        )
        if os.path.exists(default_indices):
            with open(default_indices, "r", encoding="utf-8") as f:
                indices = json.load(f)
            logger.info(f"  財務指標: あり（自動検出）")
        else:
            logger.info(f"  財務指標: なし")

    # ========================================
    # 1. タグごとに並び替え
    # ========================================
    logger.info("[1/3] タグ並び替え中...")
    sorted_report = sort_by_tag(report, indices)
    logger.info(f"  {len(sorted_report['tags'])} タグに分類完了")

    sorted_dir = os.path.join(
        base_dir, "data", "medium-output", "issue-extraction", "sorted-by-tag-per-company"
    )
    sorted_path = os.path.join(sorted_dir, f"sorted_by_tag_{code}.json")
    os.makedirs(sorted_dir, exist_ok=True)
    with open(sorted_path, "w", encoding="utf-8") as f:
        json.dump(sorted_report, f, indent=2, ensure_ascii=False)
    logger.info(f"  保存: {sorted_path}")

    # ========================================
    # 2. スコアリング
    # ========================================
    logger.info("[2/3] スコアリング中...")
    scored = score_report(sorted_report, model_id=args.model)

    scores_dir = os.path.join(
        base_dir, "data", "medium-output", "issue-extraction", "report-scores-per-company"
    )
    scores_path = os.path.join(scores_dir, f"report_scores_{code}_v1.json")
    os.makedirs(scores_dir, exist_ok=True)
    # リスト形式で保存（既存フォーマットと合わせる）
    with open(scores_path, "w", encoding="utf-8") as f:
        json.dump([scored], f, indent=2, ensure_ascii=False)
    logger.info(f"  保存: {scores_path}")

    # ========================================
    # 3. 地域特徴抽出
    # ========================================
    logger.info("[3/3] 地域特徴抽出中...")

    # sorted_report をリストとして渡す（extract_category_feature の入力形式）
    reports_list = [sorted_report]

    # 基本情報の構築
    info = _get_company_info(sorted_report)
    base_info = {
        "企業コード": str(info.get("コード", code)),
        "ファイル名": filename,
        "本社所在地": info.get("本社所在地", ""),
        "業種分類": info.get("業種分類", ""),
    }

    category_texts = {}
    for category in CATEGORY_TAG_MAP:
        logger.info(f"    [{category}] 抽出中...")
        text = extract_category_feature(reports_list, category, model_id=args.model)
        category_texts[category] = text

    logger.info("    [全体の地域的特徴] 統合分析中...")
    overall_text = extract_overall_feature(category_texts, model_id=args.model)

    features_output = {
        **base_info,
        "事業・営業・受注戦略の地域的特徴": category_texts.get("事業・営業・受注戦略の地域的特徴", ""),
        "人的資本の地域的特徴": category_texts.get("人的資本の地域的特徴", ""),
        "財務構造の地域的特徴": category_texts.get("財務構造の地域的特徴", ""),
        "全体の地域的特徴": overall_text,
    }

    features_dir = os.path.join(
        base_dir, "data", "medium-output", "issue-extraction", "local-features-per-company"
    )
    features_path = os.path.join(features_dir, f"local_features_{code}.json")
    os.makedirs(features_dir, exist_ok=True)
    with open(features_path, "w", encoding="utf-8") as f:
        json.dump(features_output, f, indent=2, ensure_ascii=False)
    logger.info(f"  保存: {features_path}")

    logger.info("全処理完了。")


if __name__ == "__main__":
    main()
