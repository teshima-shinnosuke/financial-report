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

MANAGEMENT_TAG = "経営戦略・中期ビジョン"

# タグごとの評価項目定義
TAG_SCORING_ITEMS = {
    "経営戦略・中期ビジョン": [
        "経営理念・パーパスについて、事業活動や意思決定と結びついた形で明確に示されているか。",
        "中期経営計画について、売上・利益・ROE等の数値目標が具体的に設定されているか。",
        "中期経営計画について、成長投資・コスト構造・人材施策など実行施策が明示されているか。",
        "経営課題について、財務状況（利益率・CF・財務安全性）と整合した認識が示されているか。",
        "KPIについて、進捗管理やモニタリングの考え方が示されているか。",
    ],
    "事業・営業・受注戦略": [
        "事業ポートフォリオについて、主力事業・成長事業・安定事業の位置づけが明確か。",
        "受注方針について、利益率や原価率を意識した選別受注の姿勢が示されているか。",
        "顧客・案件特性について、自社の強みが収益性の観点から整理されているか。",
        "公共・民間等の事業構成について、収益安定性やリスク分散が意識されているか。",
    ],
    "生産性・施工オペレーション": [
        "原価管理・採算管理について、利益率改善と結びついた取り組みが行われているか。",
        "施工体制について、人員制約や生産性向上を意識した工夫がなされているか。",
        "工法改善・VE活動について、コスト削減や付加価値向上に寄与しているか。",
        "ICT施工・現場DXについて、生産性・工期短縮などの効果が示されているか。",
    ],
    "人的資本・組織運営": [
        "人材確保・定着について、事業成長や生産性との関係で課題認識が示されているか。",
        "人材育成・教育について、中長期的な競争力強化の位置づけが明確か。",
        "人件費について、売上高人件費率や付加価値とのバランスが意識されているか。",
        "働き方改革・2024年問題について、収益性や現場運営への影響を踏まえた対応があるか。",
        "組織運営について、意思決定の迅速化や役割分担の明確化が図られているか。",
    ],
    "技術・DX・研究開発": [
        "技術力について、売上成長や利益率向上に貢献する競争優位として整理されているか。",
        "DX推進について、業務効率化・原価低減など定量効果が意識されているか。",
        "研究開発テーマについて、将来の事業拡大や差別化と接続しているか。",
    ],
    "サステナビリティ・社会的責任": [
        "安全衛生・労働環境について、事業継続や人材定着の観点から十分に対応されているか。",
        "脱炭素・GXについて、コスト・投資・競争力への影響が整理されているか。",
        "ESG対応について、リスク管理や企業価値向上との関係が示されているか。",
    ],
    "財務・資本政策・ガバナンス": [
        "収益性（利益率）について、原価率・販管費率を踏まえた構造的な強み・弱みが認識されているか。\n　［参照指標：売上総利益率、原価率、販管費率、営業利益率］",
        "資本効率（ROE・ROA）について、利益水準および事業モデルとの関係が説明されているか。\n　［参照指標：ROE、ROA、総資産回転率、純利益率］",
        "付加価値創出力について、人件費水準と比較した生産性の課題が認識されているか。\n　［参照指標：付加価値額、人件費率、売上総利益率］",
        "キャッシュフローについて、営業CFが利益・EBITDAと整合的に創出されているか。\n　［参照指標：営業CFマージン、営業CF÷EBITDA、EBITDA］",
        "フリーキャッシュフローについて、成長投資や設備投資を支えられる水準か。\n　［参照指標：フリーキャッシュフロー、営業CF、投資CF］",
        "財務安全性について、自己資本比率や有利子負債水準が事業リスクに見合っているか。\n　［参照指標：自己資本比率、D/Eレシオ、流動比率、当座比率］",
        "資金繰り構造について、運転資本や回収条件がキャッシュフローを圧迫していないか。\n　［参照指標：工事運転資本、売上債権回転期間、仕入債務回転期間、ネット運転資本］",
        "資本政策・ガバナンスについて、財務状況および中長期戦略と整合した意思決定・監督体制が構築されているか。\n　［参照指標：自己資本比率、ROE、D/Eレシオ、フリーキャッシュフロー］",
    ],
    "リスクマネジメント・コンプライアンス": [
        "主要リスクについて、財務影響（利益・CF・資産）を踏まえて整理されているか。",
        "災害・BCP対応について、事業継続・財務安定性の観点で十分か。",
        "人材・労務リスクについて、事業成長への影響が認識されているか。",
    ],
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


def _build_section_text(tag_group: dict) -> str:
    """タググループのセクションテキストをまとめる。"""
    parts = []
    for section in tag_group.get("sections", []):
        page = section.get("page", "?")
        text = section.get("text", "")
        parts.append(f"[p.{page}] {text}")
    return "\n\n".join(parts)


def _build_indices_text(financial_indices: dict) -> str:
    """財務指標データを読みやすいテキストに変換する。"""
    if not financial_indices:
        return ""

    lines = []
    info = financial_indices.get("企業情報", {})
    lines.append(f"【企業情報】コード: {info.get('コード')}, 所在地: {info.get('本社所在地')}, "
                 f"業種: {info.get('業種分類')}, 従業員数: {info.get('従業員数（連結）')}名")

    for yd in financial_indices.get("指標", []):
        year = yd.get("YEAR", "?")
        lines.append(f"\n【{year}年度 財務指標】")
        for category in ["収益性指標", "成長性指標", "コスト構造・固定費分析",
                         "効率性指標", "安全性・財務健全性",
                         "キャッシュフロー関連指標", "建設業特有指標"]:
            data = yd.get(category)
            if data is None:
                continue
            items = [f"{k}: {v}" for k, v in data.items() if v is not None]
            if items:
                lines.append(f"  [{category}] {', '.join(items)}")

    return "\n".join(lines)


def score_tag(
    tag_group: dict,
    model_id: str = DEFAULT_MODEL_ID,
    other_tag_summaries: list[dict] | None = None,
) -> dict:
    """
    1つのタググループに対してスコアリングを実行する。

    Args:
        tag_group: タググループ {"tag": "...", "sections": [...], ...}
        model_id: 使用するモデルID
        other_tag_summaries: 経営戦略タグ用。他タグの評価結果リスト
            [{"tag": "...", "avg_score": 3.5, "summary": "..."}, ...]

    Returns:
        {"tag": "...", "items": [{"item": "...", "score": 1-5, "rationale": "..."}, ...], "summary": "..."}
    """
    tag = tag_group.get("tag", "")
    scoring_items = TAG_SCORING_ITEMS.get(tag)

    if not scoring_items:
        return {"tag": tag, "items": [], "skipped": True}

    # セクションテキストの構築
    section_text = _build_section_text(tag_group)

    # セクションがない場合のハンドリング
    if not section_text.strip():
        # 経営戦略タグかつ他タグサマリーがある場合はAPIで評価する
        if tag == MANAGEMENT_TAG and other_tag_summaries:
            section_text = "（当タグに直接該当するセクションはありません）"
        else:
            items = [
                {"item": item, "score": None, "rationale": "該当セクションなし"}
                for item in scoring_items
            ]
            return {"tag": tag, "items": items, "summary": "該当するセクションが報告書内に見つかりませんでした。"}

    # 財務タグの場合、財務指標データも追加
    financial_text = ""
    if "financial_indices" in tag_group:
        financial_text = "\n\n【財務指標データ】\n" + _build_indices_text(tag_group["financial_indices"])

    # 経営戦略タグ用：他タグの評価サマリーをコンテキストとして追加
    cross_tag_context = ""
    if tag == MANAGEMENT_TAG and other_tag_summaries:
        context_lines = []
        for ts in other_tag_summaries:
            context_lines.append(f"  - {ts['tag']}（平均スコア: {ts['avg_score']:.1f}）: {ts['summary']}")
        cross_tag_context = "\n\n【他タグの評価結果（参考情報）】\n" + "\n".join(context_lines)

    items_text = "\n".join(f"  {i+1}. {item}" for i, item in enumerate(scoring_items))

    # 経営戦略タグ用の追加指示
    management_instruction = ""
    if tag == MANAGEMENT_TAG and other_tag_summaries:
        management_instruction = """
- 「経営戦略・中期ビジョン」は他の全タグを横断的に評価する項目です。上記の【他タグの評価結果】も参考にし、経営戦略が各分野の取り組みと整合的かどうかも踏まえて評価してください。"""

    prompt = f"""あなたは建設業の有価証券報告書を分析する専門家です。
以下の「{tag}」に関するテキストを読み、各評価項目について5段階でスコアリングし、根拠を述べてください。

【スコア基準】
1: 非常に不十分（記載なし or 極めて抽象的）
2: 不十分（断片的な記載のみ）
3: 標準的（一般的な記載はあるが具体性に欠ける）
4: 充実（具体的な取組み・数値が示されている）
5: 非常に充実（先進的・独自性のある取組みが具体的に示されている）

【評価項目】
{items_text}

【出力形式（JSON）】
{{"items": [{{"item": "評価項目名", "score": 1-5の整数, "rationale": "スコアの根拠（2-3文）"}}], "summary": "このタグ全体の総括コメント（200字程度）"}}

【出力例】
{{"items": [{{"item": "経営理念・パーパスについて、事業活動や意思決定と結びついた形で明確に示されているか。", "score": 3, "rationale": "経営理念として「社会基盤の創造」を掲げており方向性は示されているが、具体的な事業活動や意思決定との結びつきについての記載が不足している。"}}, {{"item": "中期経営計画について、売上・利益・ROE等の数値目標が具体的に設定されているか。", "score": 4, "rationale": "中期経営計画において売上高3,000億円、営業利益率5%、ROE8%以上という具体的な数値目標が明示されている。達成時期も2026年度と明確である。"}}], "summary": "経営理念は事業活動と結びついた形で明示されており、中期経営計画では具体的な数値目標も設定されている。一方、KPIの進捗管理体制や実行施策の詳細については記載が不足しており、計画の実効性を担保する仕組みの開示が今後の課題である。"}}

【制約】
- 必ずJSON形式のみで回答してください。余計なテキストは含めないでください。
- 各評価項目について必ず1つずつ、上記の順番通りに回答してください。合計{len(scoring_items)}件の評価を含めてください。
- itemフィールドには評価項目の文言をそのまま記載してください。
- scoreは1〜5の整数のみ使用してください。
- rationaleは具体的な記載内容に基づいて2-3文で記述してください。
- summaryにはこのタグ全体を総括するコメントを200字程度で記述してください。強みと課題の両面に触れてください。{management_instruction}

【分析対象テキスト】
{section_text}{financial_text}{cross_tag_context}"""

    result = _call_api(prompt, max_completion_tokens=4000, model_id=model_id)

    try:
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            items = parsed.get("items", [])
            summary = parsed.get("summary", "")
        else:
            items = []
            summary = ""
    except json.JSONDecodeError:
        items = []
        summary = ""

    # フォールバック: 項目数が合わない場合
    if len(items) != len(scoring_items):
        for i, item_name in enumerate(scoring_items):
            if i >= len(items):
                items.append({"item": item_name, "score": None, "rationale": "評価不能"})

    return {"tag": tag, "items": items, "summary": summary}


def score_report(report: dict, model_id: str = DEFAULT_MODEL_ID) -> dict:
    """
    1つの報告書の全タグをスコアリングする。
    経営戦略・中期ビジョンは他タグのスコアリング完了後に最後に評価する。
    TAG_SCORING_ITEMS に定義された全タグを、セクションの有無に関わらず出力する。
    """
    logger = logging.getLogger(__name__)

    # レポート内のタググループを辞書化（タグ名 -> tag_group）
    tag_group_map = {}
    for tag_group in report.get("tags", []):
        tag_group_map[tag_group.get("tag", "")] = tag_group

    # 経営戦略以外のタグを先にスコアリング
    other_scores = []
    other_tag_summaries = []

    for tag in TAG_SCORING_ITEMS:
        if tag == MANAGEMENT_TAG:
            continue

        tag_group = tag_group_map.get(tag, {"tag": tag, "sections": []})
        logger.info(f"    [{tag}] スコアリング中...")
        result = score_tag(tag_group, model_id=model_id)
        other_scores.append(result)

        for item in result.get("items", []):
            score = item.get("score", "?")
            logger.info(f"      {item.get('item', '?')}: {score}/5")

        # サマリー情報を収集（経営戦略タグ評価時のコンテキスト用）
        valid_scores = [it.get("score") for it in result.get("items", []) if it.get("score") is not None]
        avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
        other_tag_summaries.append({
            "tag": tag,
            "avg_score": avg_score,
            "summary": result.get("summary", ""),
        })

        time.sleep(2)

    # 経営戦略・中期ビジョンを最後にスコアリング（他タグのサマリーをコンテキストとして渡す）
    management_group = tag_group_map.get(MANAGEMENT_TAG, {"tag": MANAGEMENT_TAG, "sections": []})
    logger.info(f"    [{MANAGEMENT_TAG}] スコアリング中...（他タグの評価結果を参照）")
    management_result = score_tag(
        management_group,
        model_id=model_id,
        other_tag_summaries=other_tag_summaries,
    )

    for item in management_result.get("items", []):
        score = item.get("score", "?")
        logger.info(f"      {item.get('item', '?')}: {score}/5")

    # TAG_SCORING_ITEMS の定義順序で結果を並べる
    scores_map = {MANAGEMENT_TAG: management_result}
    for result in other_scores:
        scores_map[result["tag"]] = result

    scores = [scores_map[tag] for tag in TAG_SCORING_ITEMS if tag in scores_map]

    return {
        "filename": report.get("filename", ""),
        "scores": scores,
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_input = os.path.join(base_dir, "data", "medium-output", "issue-extraction", "report_sorted_by_tag.json")
    default_output = os.path.join(base_dir, "data", "medium-output", "issue-extraction", "report_scores.json")

    parser = argparse.ArgumentParser(description="タグごとにスコアリング・根拠抽出を行う")
    parser.add_argument("-i", "--input", default=default_input, help="入力JSONファイルパス")
    parser.add_argument("-o", "--output", default=default_output, help="出力JSONファイルパス")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL_ID, help="使用するモデルID")
    parser.add_argument("-f", "--filename", default=None, help="特定のファイル名のみ処理する（部分一致）")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    logger = logging.getLogger(__name__)

    with open(args.input, "r", encoding="utf-8") as f:
        reports = json.load(f)

    # --filename フィルタ
    if args.filename:
        reports = [r for r in reports if args.filename in r.get("filename", "")]
        logger.info(f"フィルタ適用: '{args.filename}' に一致する {len(reports)} 件を処理")
    else:
        logger.info(f"入力ファイル読み込み完了: {len(reports)} 件")

    if not reports:
        logger.warning("処理対象の報告書が見つかりません。")
        return

    # 既存の結果があれば読み込む
    results = []
    if os.path.exists(args.output):
        try:
            with open(args.output, "r", encoding="utf-8") as f:
                results = json.load(f)
            logger.info(f"既存結果を読み込みました: {len(results)} 件")
        except json.JSONDecodeError:
            results = []

    processed_filenames = {r["filename"] for r in results}

    for report in reports:
        filename = report.get("filename", "")

        if filename in processed_filenames:
            logger.info(f"  スキップ（処理済み）: {filename}")
            continue

        logger.info(f"  処理開始: {filename}")
        scored = score_report(report, model_id=args.model)
        results.append(scored)

        # 1報告書ごとに保存
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"  保存完了: {filename}")

        time.sleep(3)

    logger.info(f"全処理完了。出力: {args.output}")


if __name__ == "__main__":
    main()
