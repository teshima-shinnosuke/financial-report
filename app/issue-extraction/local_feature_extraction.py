import json
import os
import re
import time
import logging
import argparse
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL_ID = "gpt-5-mini"

# 抽出対象の3カテゴリとそれに対応するタグ
CATEGORY_TAG_MAP = {
    "事業・営業・受注戦略の地域的特徴": "事業・営業・受注戦略",
    "人的資本の地域的特徴": "人的資本・組織運営",
    "財務構造の地域的特徴": "財務・資本政策・ガバナンス",
}

# カテゴリごとの分析観点
CATEGORY_ANALYSIS_POINTS = {
    "事業・営業・受注戦略の地域的特徴": [
        "地域の建設需要の特性（公共工事/民間工事の比率、インフラ整備需要など）",
        "事業ポートフォリオと地域経済との関連性",
        "受注戦略における地域的な特徴（官公庁依存度、地元密着型か広域展開か）",
        "地域固有の事業機会やリスク",
    ],
    "人的資本の地域的特徴": [
        "従業員規模・平均年齢・勤続年数の地域的傾向",
        "人材確保・定着における地域特有の課題",
        "人件費水準と地域の労働市場との関係",
        "人材育成・働き方改革の取り組みの地域差",
    ],
    "財務構造の地域的特徴": [
        "収益構造（売上総利益率、営業利益率）の地域的傾向",
        "財務安全性（自己資本比率、D/Eレシオ）の地域的傾向",
        "キャッシュフロー構造と運転資本管理の特徴",
        "資本効率（ROE、ROA）と成長性の地域差",
    ],
}

# 期待される出力形式の定義
expected_output = {
    "企業コード": "12044",
    "ファイル名": "有価証券報告書（12044）.pdf",
    "本社所在地": "茨城",
    "業種分類": "総合建設・土木",
    "事業・営業・受注戦略の地域的特徴": "茨城県水戸市を拠点に北関東エリアの公共インフラ整備を主力とする。"
    "官公庁発注の道路・橋梁工事を中心に安定受注を確保しつつ、"
    "民間建築や不動産事業で収益多角化を図っている。"
    "2012年に東京都内へ進出し広域展開も進めている。",
    "人的資本の地域的特徴": "従業員204名、平均年齢40.5歳、平均勤続年数14.2年。"
    "M&Aによる人員拡大が近年の特徴で、独自の技術研修施設を活用した"
    "人材育成に注力。地方拠点のため若年人材の確保・定着が課題。",
    "財務構造の地域的特徴": "売上高約122億円規模。自己資本比率14.59%、D/Eレシオ3.65倍と"
    "借入依存度が高い財務構造。営業利益率3.05%と低水準で、"
    "営業CFがマイナス傾向、売上債権回転期間が約150日と長期。",
    "全体の地域的特徴": "茨城県を拠点とする地域密着型の総合建設企業。公共土木主力で"
    "M&Aによる基盤強化と東京進出で広域化を図る一方、"
    "低自己資本比率・営業CFマイナス・若年人材確保が課題。"
    "地域密着型から広域展開へ過渡期にある成長企業。",
}


def _call_api(prompt: str, max_completion_tokens: int = 4000, model_id: str = DEFAULT_MODEL_ID) -> str:
    """Azure OpenAI APIを呼び出す。"""
    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version="2024-12-01-preview",
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _load_reports(input_path: str) -> list[dict]:
    """
    入力パスからレポートを読み込む。
    ファイルパスの場合は単一レポート、ディレクトリの場合は配下の全JSONを読み込む。
    """
    if os.path.isfile(input_path):
        with open(input_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        if isinstance(report, list):
            return report
        return [report]

    reports = []
    for filename in sorted(os.listdir(input_path)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(input_path, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            report = json.load(f)
        reports.append(report)
    return reports


def _get_company_info(report: dict) -> dict:
    """レポートから企業情報を取得する（financial_indicesを持つタグから抽出）。"""
    for tag_group in report.get("tags", []):
        fi = tag_group.get("financial_indices")
        if fi:
            return fi.get("企業情報", {})
    return {}


def _extract_code(report: dict) -> str:
    """レポートから企業コードを取得する。"""
    info = _get_company_info(report)
    code = info.get("コード", "")
    if code:
        return str(code)
    match = re.search(r"(\d+)", report.get("filename", ""))
    return match.group(1) if match else "unknown"


def _get_tag_group(report: dict, tag_name: str) -> dict | None:
    """レポートから特定のタグのデータを取得する。"""
    for tag_group in report.get("tags", []):
        if tag_group.get("tag") == tag_name:
            return tag_group
    return None


def _build_section_text(tag_group: dict, max_chars: int = 3000) -> str:
    """タググループのセクションテキストをまとめる（文字数制限付き）。"""
    parts = []
    total = 0
    for section in tag_group.get("sections", []):
        page = section.get("page", "?")
        text = section.get("text", "")
        part = f"[p.{page}] {text}"
        if total + len(part) > max_chars:
            remaining = max_chars - total
            if remaining > 100:
                parts.append(part[:remaining] + "...（以下省略）")
            break
        parts.append(part)
        total += len(part)
    return "\n\n".join(parts)


def _build_indices_text(financial_indices: dict) -> str:
    """財務指標データを読みやすいテキストに変換する。"""
    if not financial_indices:
        return ""

    lines = []
    info = financial_indices.get("企業情報", {})
    lines.append(
        f"【企業情報】コード: {info.get('コード')}, 所在地: {info.get('本社所在地')}, "
        f"業種: {info.get('業種分類')}, 従業員数: {info.get('従業員数（連結）')}名"
    )

    for yd in financial_indices.get("指標", []):
        year = yd.get("YEAR", "?")
        lines.append(f"\n【{year}年度 財務指標】")
        for category in [
            "収益性指標", "成長性指標", "コスト構造・固定費分析",
            "効率性指標", "安全性・財務健全性",
            "キャッシュフロー関連指標", "建設業特有指標",
        ]:
            data = yd.get(category)
            if data is None:
                continue
            items = [f"{k}: {v}" for k, v in data.items() if v is not None]
            if items:
                lines.append(f"  [{category}] {', '.join(items)}")

    return "\n".join(lines)


def _build_company_summary(report: dict, tag_name: str, max_section_chars: int = 3000) -> str:
    """1企業の特定タグに関するサマリーテキストを構築する。"""
    company_info = _get_company_info(report)
    tag_group = _get_tag_group(report, tag_name)

    header = (
        f"【企業】コード: {company_info.get('コード', '不明')}, "
        f"所在地: {company_info.get('本社所在地', '不明')}, "
        f"業種: {company_info.get('業種分類', '不明')}, "
        f"従業員数: {company_info.get('従業員数（連結）', '不明')}名, "
        f"資本金: {company_info.get('資本金（億円）', '不明')}億円, "
        f"ファイル: {report.get('filename', '不明')}"
    )

    if not tag_group:
        return header + "\n（該当セクションなし）"

    section_text = _build_section_text(tag_group, max_chars=max_section_chars)
    result = header + "\n" + section_text

    if tag_name == "財務・資本政策・ガバナンス" and "financial_indices" in tag_group:
        result += "\n\n" + _build_indices_text(tag_group["financial_indices"])

    return result


def extract_category_feature(
    reports: list[dict],
    category: str,
    model_id: str = DEFAULT_MODEL_ID,
) -> str:
    """
    1カテゴリの地域的特徴をテキストとして抽出する。

    Returns:
        抽出された特徴テキスト
    """
    logger = logging.getLogger(__name__)
    tag_name = CATEGORY_TAG_MAP[category]
    analysis_points = CATEGORY_ANALYSIS_POINTS[category]

    max_chars = 2000 if tag_name == "財務・資本政策・ガバナンス" else 3000

    company_texts = []
    for report in reports:
        summary = _build_company_summary(report, tag_name, max_section_chars=max_chars)
        company_texts.append(summary)

    all_companies_text = "\n\n---\n\n".join(company_texts)
    analysis_items = "\n".join(f"  {i+1}. {point}" for i, point in enumerate(analysis_points))

    prompt = f"""あなたは建設業の有価証券報告書を分析する専門家です。
以下の企業の「{tag_name}」に関するデータを読み、「{category}」を抽出してください。

各企業の本社所在地に着目し、地域ごとの特徴やパターンを分析してください。

【分析の観点】
{analysis_items}

【出力形式（JSON）】
{{"summary": "地域的特徴の分析結果（300〜500字程度）"}}

【制約】
- 必ずJSON形式のみで回答してください。
- summaryは具体的なデータ（数値・固有名詞）を含めて記述してください。
- 地域の建設需要や経済環境との関連を踏まえて記述してください。
- 「です・ます」調の敬語で記述してください。

【分析対象データ】
{all_companies_text}"""

    result = _call_api(prompt, max_completion_tokens=2000, model_id=model_id)

    try:
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            return parsed.get("summary", "")
    except json.JSONDecodeError:
        logger.error(f"    [{category}] JSON解析失敗: {result[:200]}")

    return ""


def extract_overall_feature(
    category_texts: dict[str, str],
    model_id: str = DEFAULT_MODEL_ID,
) -> str:
    """
    3カテゴリの分析結果を統合し、全体的な地域的特徴をテキストとして抽出する。

    Returns:
        統合された特徴テキスト
    """
    logger = logging.getLogger(__name__)

    input_text = "\n\n".join(
        f"【{cat}】\n{text}" for cat, text in category_texts.items()
    )

    prompt = f"""あなたは建設業の有価証券報告書を分析する専門家です。
以下の3カテゴリ（事業・営業・受注戦略、人的資本、財務構造）の地域的特徴の分析結果を統合し、
全体的な地域的特徴を総括してください。

【統合分析の観点】
  1. 事業戦略・人的資本・財務構造の3側面の整合性や関連性
  2. 地域経済・産業構造が経営全体に与える影響
  3. 強み・課題の総合評価

【出力形式（JSON）】
{{"summary": "3側面を統合した全体的な地域的特徴（300〜500字程度）"}}

【制約】
- 必ずJSON形式のみで回答してください。
- 事業面・人材面・財務面を横断した総合的な記述としてください。
- 「です・ます」調の敬語で記述してください。

【3カテゴリの分析結果】
{input_text}"""

    result = _call_api(prompt, max_completion_tokens=2000, model_id=model_id)

    try:
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            return parsed.get("summary", "")
    except json.JSONDecodeError:
        logger.error(f"    [全体] JSON解析失敗: {result[:200]}")

    return ""


def _resolve_output_path(args_output: str, reports: list[dict], is_single_file: bool) -> str:
    """出力パスを解決する。単一ファイル入力の場合はコード付きファイル名にする。"""
    if not is_single_file or len(reports) != 1:
        return args_output

    code = _extract_code(reports[0])
    output_dir = os.path.dirname(args_output)
    return os.path.join(output_dir, f"local_features_{code}.json")


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_input = os.path.join(
        base_dir, "data", "medium-output", "issue-extraction", "sorted-by-tag-per-company"
    )
    default_output = os.path.join(
        base_dir, "data", "medium-output", "issue-extraction", "local_features.json"
    )

    parser = argparse.ArgumentParser(description="sorted_by_tagデータから地域的特徴を抽出する")
    parser.add_argument("-i", "--input", default=default_input, help="入力ディレクトリまたはJSONファイルパス")
    parser.add_argument("-f", "--file", default=None, help="単一ファイルを指定して実行（-i より優先）")
    parser.add_argument("-o", "--output", default=default_output, help="出力JSONファイルパス")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL_ID, help="使用するモデルID")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    logger = logging.getLogger(__name__)

    # 入力パスの決定（-f が優先）
    input_path = args.file if args.file else args.input
    is_single_file = os.path.isfile(input_path)

    # レポート読み込み
    reports = _load_reports(input_path)
    logger.info(f"レポート読み込み完了: {len(reports)} 件")

    if not reports:
        logger.warning("処理対象のレポートが見つかりません。")
        return

    # 出力パスの解決
    output_path = _resolve_output_path(args.output, reports, is_single_file)

    # 企業一覧をログ出力
    for report in reports:
        info = _get_company_info(report)
        logger.info(
            f"  コード: {info.get('コード', '?')}, "
            f"所在地: {info.get('本社所在地', '?')}, "
            f"業種: {info.get('業種分類', '?')}"
        )

    # --- 基本情報の構築 ---
    if len(reports) == 1:
        info = _get_company_info(reports[0])
        base_info = {
            "企業コード": str(info.get("コード", "")),
            "ファイル名": reports[0].get("filename", ""),
            "本社所在地": info.get("本社所在地", ""),
            "業種分類": info.get("業種分類", ""),
        }
    else:
        base_info = {
            "対象ファイル": [r.get("filename", "") for r in reports],
        }

    # --- Step 1: 各カテゴリの地域的特徴を抽出 ---
    category_texts = {}
    for category in CATEGORY_TAG_MAP:
        logger.info(f"  [{category}] 抽出中...")
        text = extract_category_feature(reports, category, model_id=args.model)
        category_texts[category] = text
        logger.info(f"  [{category}] 完了")
        time.sleep(3)

    # --- Step 2: 全体の統合分析 ---
    logger.info("  [全体の地域的特徴] 統合分析中...")
    overall_text = extract_overall_feature(category_texts, model_id=args.model)
    logger.info("  [全体の地域的特徴] 完了")

    # --- 出力の構築 ---
    output = {
        **base_info,
        "事業・営業・受注戦略の地域的特徴": category_texts.get("事業・営業・受注戦略の地域的特徴", ""),
        "人的資本の地域的特徴": category_texts.get("人的資本の地域的特徴", ""),
        "財務構造の地域的特徴": category_texts.get("財務構造の地域的特徴", ""),
        "全体の地域的特徴": overall_text,
    }

    # 保存
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info(f"全処理完了。出力: {output_path}")


if __name__ == "__main__":
    main()
