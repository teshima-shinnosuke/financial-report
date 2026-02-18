import json
import os
import re
import logging
import argparse
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL_ID = "gpt-5-mini"


def _call_api(prompt: str, max_completion_tokens: int = 3000, model_id: str = DEFAULT_MODEL_ID) -> str:
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


def _parse_json_response(text: str) -> dict:
    """APIレスポンスからJSONを抽出する。"""
    logger = logging.getLogger(__name__)
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            logger.warning(f"JSON未検出。レスポンス先頭200字: {text[:200]}")
    except json.JSONDecodeError as e:
        logger.warning(f"JSONパース失敗: {e}。レスポンス先頭200字: {text[:200]}")
    return {}


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 入力データの抽出・テキスト変換
# ============================================================

def _build_summary_input(
    local_features: dict,
    report_scores: list | dict,
    selection: dict,
    roadmap: dict,
) -> str:
    """4ファイルから必要なキーだけを抽出し、プロンプト用テキストに変換する。"""
    lines = []

    # ① 企業概要 (local_features)
    lines.append("【企業概要】")
    lines.append(f"本社所在地: {local_features.get('本社所在地', '')}")
    lines.append(f"業種分類: {local_features.get('業種分類', '')}")
    lines.append(f"地域特徴: {local_features.get('全体の地域的特徴', '')}")
    lines.append("")

    # ② 現状診断スコア (selection: tag_averages, weak_tags)
    lines.append("【現状診断スコア（5点満点）】")
    for tag, score in selection.get("tag_averages", {}).items():
        lines.append(f"  {tag}: {score}")
    weak_tags = selection.get("weak_tags", [])[:3]
    weak_names = [f"{w['tag']}({w['avg_score']})" for w in weak_tags]
    lines.append(f"弱点上位3分野: {', '.join(weak_names)}")
    lines.append("")

    # ③ 弱点分野の診断サマリ (report_scores)
    lines.append("【弱点分野の診断サマリ】")
    weak_tag_set = {w["tag"] for w in weak_tags}
    scores_list = report_scores[0]["scores"] if isinstance(report_scores, list) else report_scores.get("scores", [])
    for s in scores_list:
        if s["tag"] in weak_tag_set:
            lines.append(f"  {s['tag']}: {s['summary']}")
    lines.append("")

    # ④ 選定施策と地域性・業界特性への対応 (selection)
    lines.append("【選定施策と地域性・業界特性への対応】")
    for sol in selection.get("selected_solutions", []):
        lines.append(f"  施策{sol.get('priority', '?')}: {sol.get('施策名', '')}")
        lines.append(f"    地域性への対応: {sol.get('地域性適合理由', '')}")
        lines.append(f"    業界特性への対応: {sol.get('業界特性適合理由', '')}")
        lines.append(f"    期待効果: {sol.get('expected_impact', '')}")
    lines.append("")

    # ⑤ 効果見通し (roadmap → impact)
    impact = roadmap.get("impact", {})
    qi = impact.get("quantitative_impact", {})
    lines.append("【効果見通し】")
    lines.append(f"  利益率: {qi.get('profit_margin', '')}")
    lines.append(f"  定性効果: {impact.get('qualitative_impact', {}).get('narrative', '')}")
    lines.append("")

    # ⑥ 実行ロードマップの到達像 (roadmap → roadmap)
    rm = roadmap.get("roadmap", {})
    lines.append("【実行ロードマップ（到達像）】")
    lines.append(f"  短期: {rm.get('short_term', {}).get('ideal_state', '')}")
    lines.append(f"  中期: {rm.get('mid_term', {}).get('ideal_state', '')}")
    lines.append(f"  長期: {rm.get('long_term', {}).get('ideal_state', '')}")

    return "\n".join(lines)


# ============================================================
# エグゼクティブサマリ生成
# ============================================================

def generate_executive_summary(
    local_features: dict,
    report_scores: list | dict,
    selection: dict,
    roadmap: dict,
    model_id: str = DEFAULT_MODEL_ID,
) -> dict:
    """
    4ファイルの抽出情報をもとにエグゼクティブサマリを生成する。
    地域性・業界特性への対応を軸に、ポジティブなトーンでまとめる。
    """
    input_text = _build_summary_input(local_features, report_scores, selection, roadmap)

    prompt = f"""あなたは建設業の経営コンサルタントです。
以下の分析結果をもとに、エグゼクティブサマリーを一つの連続した文章で生成してください。

【方針】
- 読み手は経営層・投資家。簡潔で説得力のある文章にすること。
- 以下の流れを1つの文章としてつなげる（見出しや箇条書きは使わない）:
  1. 企業の現状と地域的な立ち位置（1〜2文）
  2. 最大の経営課題（1文）
  3. 地域性・業界特性を踏まえた提案の要旨（何を・なぜ・どう、3〜4文。地域の機会や業界動向にどう対応するかを具体的に）
  4. 期待効果（定量＋定性、2文）
- リスクやネガティブ要素は記載しない。前向きなトーンで締める。

【分析結果】
{input_text}

【出力形式（JSON）】
{{
  "content": "エグゼクティブサマリー本文（1つの連続した文章、800字以内）"
}}

【制約】
- JSON形式のみで回答。
- contentは1つの文章として自然につなげる。見出し・番号・改行は不要。
- 800字以内。
- 「地域」「業界」のキーワードを自然に含め、施策が当社の立地・環境に即していることを示す。
- 抽象的な表現は避け、数値・施策名を具体的に含める。
- 「です・ます」調の敬語で記述してください。"""

    result = _call_api(prompt, max_completion_tokens=3000, model_id=model_id)
    parsed = _parse_json_response(result)
    content = parsed.get("content", "")

    return {
        "id": "executive_summary",
        "title": "エグゼクティブサマリー",
        "content": content,
        "char_count": len(content),
    }


# ============================================================
# CLI
# ============================================================

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    parser = argparse.ArgumentParser(description="エグゼクティブサマリーの生成")
    parser.add_argument("-c", "--code", required=True, help="企業コード（例: 12044）")
    parser.add_argument("--local-features", default=None, help="local_features_*.json のパス（未指定時はコードで自動検出）")
    parser.add_argument("--report-scores", default=None, help="report_scores_*.json のパス（未指定時はコードで自動検出）")
    parser.add_argument("--selection", default=None, help="solution_selection_*.json のパス（未指定時はコードで自動検出）")
    parser.add_argument("--roadmap", default=None, help="roadmap_*.json のパス（未指定時はコードで自動検出）")
    parser.add_argument("-o", "--output", default=None, help="出力JSONファイルパス（未指定時は自動生成）")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL_ID, help="使用するモデルID")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    logger = logging.getLogger(__name__)

    code = args.code

    # --- ファイルパス解決（CLI引数優先、未指定時はコードで自動検出） ---
    paths = {
        "local_features": args.local_features or os.path.join(
            base_dir, "data", "medium-output", "issue-extraction",
            "local-features-per-company", f"local_features_{code}.json",
        ),
        "report_scores": args.report_scores or os.path.join(
            base_dir, "data", "medium-output", "issue-extraction",
            "report-scores-per-company", f"report_scores_{code}_v2.json",
        ),
        "selection": args.selection or os.path.join(
            base_dir, "data", "medium-output", "solution-selection",
            f"solution_selection_{code}.json",
        ),
        "roadmap": args.roadmap or os.path.join(
            base_dir, "data", "medium-output", "solution-selection",
            "roadmaps-per-company", f"roadmap_{code}.json",
        ),
    }

    # --- データ読み込み ---
    logger.info(f"対象企業コード: {code}")
    data = {}
    for key, path in paths.items():
        if os.path.exists(path):
            data[key] = _load_json(path)
            logger.info(f"  {key}: OK")
        else:
            logger.error(f"  {key}: ファイルなし ({path})")
            return

    # --- 生成 ---
    logger.info("エグゼクティブサマリー生成中...")
    result = generate_executive_summary(
        local_features=data["local_features"],
        report_scores=data["report_scores"],
        selection=data["selection"],
        roadmap=data["roadmap"],
        model_id=args.model,
    )

    # --- 保存 ---
    output_dir = os.path.join(base_dir, "data", "final-output", "executive-summary-per-company")
    output_path = args.output or os.path.join(output_dir, f"executive_summary_{code}.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info(f"保存完了: {output_path}")

    # --- サマリー表示 ---
    content = result.get("content", "")
    logger.info(f"  文字数: {result.get('char_count', 0)}字")
    logger.info(f"  本文: {content[:120]}{'...' if len(content) > 120 else ''}")

    logger.info("処理完了。")


if __name__ == "__main__":
    main()
