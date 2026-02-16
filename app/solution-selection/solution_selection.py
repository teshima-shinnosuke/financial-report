import json
import os
import re
import logging
import argparse
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL_ID = "gpt-5-mini"

# スコアリングタグ番号とタグ名のマッピング（solution.jsonの着目した課題カテゴリ.no に対応）
TAG_NO_MAP = {
    1: "経営戦略・中期ビジョン",
    2: "事業・営業・受注戦略",
    3: "生産性・施工オペレーション",
    4: "人的資本・組織運営",
    5: "技術・DX・研究開発",
    6: "サステナビリティ・社会的責任",
    7: "財務・資本政策・ガバナンス",
    8: "リスクマネジメント・コンプライアンス",
}

# 低スコアとみなす閾値
LOW_SCORE_THRESHOLD = 3


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


def _extract_code(filename: str) -> str:
    """ファイル名から企業コードを抽出する。"""
    match = re.search(r"(\d+)", filename)
    return match.group(1) if match else "unknown"


def _load_scores(scores_path: str) -> list[dict]:
    """スコアリングJSONを読み込む（ファイルまたはディレクトリ対応）。"""
    if os.path.isfile(scores_path):
        with open(scores_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]

    results = []
    for filename in sorted(os.listdir(scores_path)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(scores_path, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            results.extend(data)
        else:
            results.append(data)
    return results


def _load_local_features(features_path: str) -> list[dict]:
    """local_feature JSONを読み込む（ファイルまたはディレクトリ対応）。"""
    if os.path.isfile(features_path):
        with open(features_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]

    results = []
    for filename in sorted(os.listdir(features_path)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(features_path, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        results.append(data)
    return results


def _compute_tag_averages(score_entry: dict) -> dict[str, float]:
    """1企業のスコアリング結果からタグごとの平均スコアを算出する。"""
    tag_avgs = {}
    for tag_result in score_entry.get("scores", []):
        tag = tag_result.get("tag", "")
        valid_scores = [
            item.get("score") for item in tag_result.get("items", [])
            if item.get("score") is not None
        ]
        if valid_scores:
            tag_avgs[tag] = sum(valid_scores) / len(valid_scores)
        else:
            tag_avgs[tag] = 0.0
    return tag_avgs


def _identify_weak_tags(tag_avgs: dict[str, float], threshold: float = LOW_SCORE_THRESHOLD) -> list[dict]:
    """閾値以下のタグを弱点として抽出する。"""
    weak = []
    for tag, avg in sorted(tag_avgs.items(), key=lambda x: x[1]):
        if avg <= threshold:
            weak.append({"tag": tag, "avg_score": round(avg, 2)})
    return weak


def _find_low_score_items(score_entry: dict, threshold: float = LOW_SCORE_THRESHOLD) -> list[dict]:
    """スコアが閾値以下の個別評価項目を抽出する。"""
    low_items = []
    for tag_result in score_entry.get("scores", []):
        tag = tag_result.get("tag", "")
        for item in tag_result.get("items", []):
            score = item.get("score")
            if score is not None and score <= threshold:
                low_items.append({
                    "tag": tag,
                    "item": item.get("item", ""),
                    "score": score,
                    "rationale": item.get("rationale", ""),
                })
    return low_items


def _match_solutions_to_weaknesses(
    solutions: dict,
    weak_tags: list[dict],
) -> list[dict]:
    """弱点タグに対応する施策を抽出し、関連度順にソートする。"""
    weak_tag_names = {w["tag"] for w in weak_tags}
    weak_tag_scores = {w["tag"]: w["avg_score"] for w in weak_tags}

    candidates = []
    for solution_name, solution_data in solutions.items():
        target_categories = solution_data.get("着目した課題カテゴリ", [])
        matched_tags = []
        for cat in target_categories:
            tag_name = TAG_NO_MAP.get(cat.get("no"))
            if tag_name and tag_name in weak_tag_names:
                matched_tags.append({
                    "tag": tag_name,
                    "avg_score": weak_tag_scores.get(tag_name, 0),
                })

        if matched_tags:
            # マッチしたタグ数とスコアの低さで関連度を計算
            relevance = len(matched_tags) + sum(
                (LOW_SCORE_THRESHOLD + 1 - t["avg_score"]) for t in matched_tags
            )
            candidates.append({
                "施策名": solution_name,
                "施策データ": solution_data,
                "matched_tags": matched_tags,
                "relevance": round(relevance, 2),
            })

    candidates.sort(key=lambda x: x["relevance"], reverse=True)
    return candidates[:3]


def _build_scores_summary(score_entry: dict) -> str:
    """スコアリング結果を読みやすいテキストに変換する。"""
    lines = []
    for tag_result in score_entry.get("scores", []):
        tag = tag_result.get("tag", "")
        items = tag_result.get("items", [])
        valid_scores = [it.get("score") for it in items if it.get("score") is not None]
        avg = sum(valid_scores) / len(valid_scores) if valid_scores else 0
        lines.append(f"\n【{tag}】（平均: {avg:.1f}/5）")
        for item in items:
            score = item.get("score", "?")
            lines.append(f"  - {item.get('item', '?')}: {score}/5")
        summary = tag_result.get("summary", "")
        if summary:
            lines.append(f"  総括: {summary}")
    return "\n".join(lines)


def _build_local_features_text(features: dict) -> str:
    """local_features JSONをテキストに変換する。"""
    lines = []
    for key in ["本社所在地", "業種分類", "事業・営業・受注戦略の地域的特徴",
                 "人的資本の地域的特徴", "財務構造の地域的特徴", "全体の地域的特徴"]:
        value = features.get(key, "")
        if value:
            lines.append(f"【{key}】{value}")
    return "\n\n".join(lines)


def _build_outer_factor_summary(outer_factor_text: str, max_chars: int = 4000) -> str:
    """outer_factor.mdのテキストを要約用に切り出す（エグゼクティブサマリー + 戦略含意を優先）。"""
    sections_to_extract = [
        "## エグゼクティブサマリー",
        "## 戦略含意と五年シナリオ",
    ]

    parts = []
    for section_header in sections_to_extract:
        idx = outer_factor_text.find(section_header)
        if idx == -1:
            continue
        # 次のH2セクションまでを取得
        next_h2 = outer_factor_text.find("\n## ", idx + len(section_header))
        if next_h2 == -1:
            section_text = outer_factor_text[idx:]
        else:
            section_text = outer_factor_text[idx:next_h2]
        parts.append(section_text.strip())

    result = "\n\n".join(parts)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n...（以下省略）"
    return result


def select_solutions(
    score_entry: dict,
    local_features: dict | None,
    outer_factor_text: str,
    solutions: dict,
    model_id: str = DEFAULT_MODEL_ID,
) -> dict:
    """
    1企業に対して最適な施策を選定する。

    Args:
        score_entry: スコアリング結果 {"filename": "...", "scores": [...]}
        local_features: 地域特徴 {"企業コード": "...", ...} or None
        outer_factor_text: 外部環境分析テキスト
        solutions: 施策定義 {"施策名": {...}, ...}
        model_id: 使用するモデルID

    Returns:
        {"企業コード": "...", "filename": "...", "selected_solutions": [...]}
    """
    logger = logging.getLogger(__name__)
    filename = score_entry.get("filename", "")
    code = _extract_code(filename)

    # Step 1: タグ別平均スコアと弱点の特定
    tag_avgs = _compute_tag_averages(score_entry)
    weak_tags = _identify_weak_tags(tag_avgs)
    low_items = _find_low_score_items(score_entry)

    logger.info(f"    弱点タグ: {len(weak_tags)} 件")
    for w in weak_tags:
        logger.info(f"      {w['tag']}: {w['avg_score']}/5")

    # Step 2: 弱点に対応する施策候補のプリフィルタ
    candidates = _match_solutions_to_weaknesses(solutions, weak_tags)
    logger.info(f"    施策候補: {len(candidates)} 件")

    if not candidates:
        logger.warning("    弱点に対応する施策候補が見つかりませんでした。")
        return {
            "企業コード": code,
            "filename": filename,
            "tag_averages": {k: round(v, 2) for k, v in tag_avgs.items()},
            "weak_tags": weak_tags,
            "selected_solutions": [],
        }

    # Step 3: LLMによる施策の適合度評価
    scores_text = _build_scores_summary(score_entry)
    features_text = _build_local_features_text(local_features) if local_features else "（地域特徴データなし）"
    outer_summary = _build_outer_factor_summary(outer_factor_text)

    # 施策候補の情報を構築
    candidate_descriptions = []
    for i, c in enumerate(candidates):
        data = c["施策データ"]
        matched_info = ", ".join(f"{t['tag']}(平均{t['avg_score']})" for t in c["matched_tags"])
        desc = (
            f"{i+1}. {c['施策名']}\n"
            f"   概要: {data.get('施策の概要', '')}\n"
            f"   対応する弱点タグ: {matched_info}\n"
            f"   地域性: {data.get('地域性・業界構造との関係', {}).get('なぜ地域企業に意味があるか', '')}"
        )
        candidate_descriptions.append(desc)
    candidates_text = "\n\n".join(candidate_descriptions)

    # 低スコア項目のテキスト
    low_items_text = "\n".join(
        f"  - [{it['tag']}] {it['item']}（{it['score']}/5）: {it['rationale']}"
        for it in low_items[:20]  # 上位20件に絞る
    )

    prompt = f"""あなたは建設業の経営コンサルタントです。
以下の企業のスコアリング結果・地域特徴・外部環境を踏まえ、提示された施策候補から最適な施策を選定してください。

【企業ファイル名】{filename}

【スコアリング結果の概要】
{scores_text}

【スコアが低い評価項目（具体的な弱点）】
{low_items_text}

【企業の地域的特徴】
{features_text}

【外部環境分析（建設業界）】
{outer_summary}

【施策候補（弱点タグに対応するもの）】
{candidates_text}

【出力形式（JSON）】
{{"selected_solutions": [
  {{
    "施策名": "施策名をそのまま記載",
    "priority": 1,
    "relevance_score": 1-5の整数（5が最も適合）,
    "課題適合理由": "スコアリング結果から読み取れる課題に対して、この施策がなぜ有効か（具体的なスコア値や評価項目を引用、200字程度）",
    "地域性適合理由": "この企業の所在地・地域特性に対して、この施策がなぜ有効か（地域特徴データを引用、200字程度）",
    "業界特性適合理由": "建設業界の外部環境・構造変化に対して、この施策がなぜ有効か（外部環境分析を引用、200字程度）",
    "expected_impact": "期待される改善効果（100字程度）",
    "対応する弱点": ["対応する弱点タグ名"]
  }}
]}}

【制約】
- 必ずJSON形式のみで回答してください。
- 施策は適合度の高い順にpriority=1,2,3と番号を振ってください。候補は3件です。
- relevance_scoreは企業の具体的な弱点・地域特性・外部環境との整合性を総合的に判断してください。
- 課題適合理由・地域性適合理由・業界特性適合理由はそれぞれ独立した観点で、具体的なデータを引用して記述してください。
- 施策名は候補リストの名称をそのまま使用してください。
- 全ての日本語テキストは「です・ます」調の敬語で記述してください。"""

    result = _call_api(prompt, max_completion_tokens=4000, model_id=model_id)

    try:
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            selected = parsed.get("selected_solutions", [])
        else:
            selected = []
    except json.JSONDecodeError:
        logger.error(f"    JSON解析失敗: {result[:200]}")
        selected = []

    return {
        "企業コード": code,
        "filename": filename,
        "tag_averages": {k: round(v, 2) for k, v in tag_avgs.items()},
        "weak_tags": weak_tags,
        "selected_solutions": selected,
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    parser = argparse.ArgumentParser(description="1企業のスコアリング・地域特徴・外部環境を踏まえた施策選定")
    parser.add_argument("-s", "--scores", required=True,
                        help="スコアリングJSONファイル（例: report_scores_12044_v1.json）")
    parser.add_argument("-f", "--features", required=True,
                        help="地域特徴JSONファイル（例: local_features_12044.json）")
    parser.add_argument("--outer", default=os.path.join(base_dir, "data", "input", "outer_factor.md"),
                        help="外部環境分析Markdownファイル")
    parser.add_argument("--solutions", default=os.path.join(base_dir, "data", "input", "solution.json"),
                        help="施策定義JSONファイル")
    parser.add_argument("-o", "--output", default=None,
                        help="出力JSONファイルパス（未指定時は自動生成）")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL_ID,
                        help="使用するモデルID")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    logger = logging.getLogger(__name__)

    # --- データ読み込み ---
    logger.info("データ読み込み中...")

    with open(args.scores, "r", encoding="utf-8") as f:
        scores_data = json.load(f)
    score_entry = scores_data[0] if isinstance(scores_data, list) else scores_data

    with open(args.features, "r", encoding="utf-8") as f:
        local_features = json.load(f)

    with open(args.outer, "r", encoding="utf-8") as f:
        outer_factor_text = f.read()

    with open(args.solutions, "r", encoding="utf-8") as f:
        solutions = json.load(f)

    filename = score_entry.get("filename", "")
    code = _extract_code(filename)
    logger.info(f"対象企業: {filename} (コード: {code})")
    logger.info(f"  地域: {local_features.get('本社所在地', '?')}")

    # --- 施策選定の実行 ---
    result = select_solutions(
        score_entry=score_entry,
        local_features=local_features,
        outer_factor_text=outer_factor_text,
        solutions=solutions,
        model_id=args.model,
    )

    # --- 保存 ---
    output_dir = os.path.join(base_dir, "data", "medium-output", "solution-selection")
    output_path = args.output or os.path.join(output_dir, f"solution_selection_{code}.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info(f"保存完了: {output_path}")

    for sol in result.get("selected_solutions", []):
        logger.info(
            f"  [{sol.get('priority', '?')}] {sol.get('施策名', '?')} "
            f"(適合度: {sol.get('relevance_score', '?')}/5)"
        )

    logger.info("処理完了。")


if __name__ == "__main__":
    main()
