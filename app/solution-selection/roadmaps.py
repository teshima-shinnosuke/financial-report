import json
import os
import re
import logging
import argparse
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL_ID = "gpt-5-mini"


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


def _extract_code(filename: str) -> str:
    """ファイル名から企業コードを抽出する。"""
    match = re.search(r"(\d+)", filename)
    return match.group(1) if match else "unknown"


# ============================================================
# ヘルパー：入力データのテキスト変換
# ============================================================

def _build_financial_summary(indices: dict) -> str:
    """財務指標データを効果試算用テキストに変換する。"""
    if not indices:
        return "（財務指標データなし）"

    lines = []
    info = indices.get("企業情報", {})
    lines.append(f"企業コード: {info.get('コード')}, 所在地: {info.get('本社所在地')}, "
                 f"業種: {info.get('業種分類')}, 従業員: {info.get('従業員数（連結）')}名")

    for yd in indices.get("指標", []):
        year = yd.get("YEAR", "?")
        parts = []
        prof = yd.get("収益性指標", {})
        if prof:
            parts.append(f"売上総利益率{prof.get('売上総利益率')}%, "
                         f"営業利益率{prof.get('営業利益率')}%")
        safe = yd.get("安全性・財務健全性", {})
        if safe:
            parts.append(f"自己資本比率{safe.get('自己資本比率')}%, "
                         f"D/E{safe.get('D/Eレシオ')}")
        cf = yd.get("キャッシュフロー関連指標", {})
        if cf:
            parts.append(f"営業CFマージン{cf.get('営業CFマージン')}%")
        eff = yd.get("効率性指標", {})
        if eff:
            parts.append(f"ROE{eff.get('ROE')}%, ROA{eff.get('ROA')}%")
        constr = yd.get("建設業特有指標", {})
        if constr:
            parts.append(f"売上債権回転{constr.get('売上債権回転期間（日）')}日")
        lines.append(f"  {year}年: {', '.join(parts)}")

    return "\n".join(lines)


def _build_selection_text(selection: dict) -> str:
    """selection JSONから施策情報をテキスト化する。
    selection内の課題適合理由・地域性適合理由・業界特性適合理由に
    local_features / outer_factor / solutions_master の情報は既に含まれている。
    """
    lines = []
    for sol in selection.get("selected_solutions", []):
        lines.append(f"【施策{sol.get('priority', '?')}】{sol.get('施策名', '')}")
        lines.append(f"  課題適合理由: {sol.get('課題適合理由', '')}")
        lines.append(f"  地域性適合理由: {sol.get('地域性適合理由', '')}")
        lines.append(f"  業界特性適合理由: {sol.get('業界特性適合理由', '')}")
        lines.append(f"  期待効果: {sol.get('expected_impact', '')}")
        weak = sol.get("対応する弱点", [])
        if weak:
            lines.append(f"  対応する弱点: {', '.join(weak)}")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# 1. 効果試算（impact）
# ============================================================

def generate_impact(
    selection: dict,
    financial_indices: dict,
    model_id: str = DEFAULT_MODEL_ID,
) -> dict:
    """
    効果試算セクションを生成する。
    Mid レベル: 業界水準ベースのレンジ提示 + 財務指標データとの接続。
    """
    financial_text = _build_financial_summary(financial_indices)
    selection_text = _build_selection_text(selection)

    prompt = f"""あなたは建設業の経営コンサルタントです。
以下の企業の財務指標と選定施策を踏まえ、効果試算セクションを生成してください。

【方針】
- 試算前提は「控えめ（コンサバティブ）」に設定する。楽観的な仮定は避ける。
- 定量効果は、当社の直近財務指標を起点に「同業上位水準を参考にした改善レンジ」で表現する。
  例: 「営業利益率 3.05% → 4.0〜5.0%（同業上位水準を参考に+1〜2pt改善を想定）」
- 定性効果は、受注安定性・人材定着・中長期競争力の3軸で簡潔に記載する。

【企業の財務指標推移】
{financial_text}

【選定施策】
{selection_text}

【出力形式（JSON）】
{{
  "assumptions": [
    "仮定条件1（控えめな前提）",
    "仮定条件2"
  ],
  "conservativeness_note": "本試算が控えめな前提である理由（50字程度）",
  "quantitative_impact": {{
    "revenue": "売上への影響（レンジ表現、100字程度）",
    "profit_margin": "利益率への影響（当社の現在値→目標レンジ、100字程度）",
    "cash_flow": "CFへの影響（100字程度）",
    "calculation_notes": "試算ロジックの補足（200字程度）"
  }},
  "qualitative_impact": {{
    "effects": [
      "受注安定性に関する定性効果",
      "人材定着に関する定性効果",
      "中長期競争力に関する定性効果"
    ],
    "narrative": "定性効果の総合説明（200字程度）"
  }}
}}

【制約】
- JSON形式のみで回答。
- 定量効果は必ず当社の直近指標値を起点にレンジで表現。
- 仮定条件は具体的かつ検証可能な形で記載。
- 全体で2000字以内。"""

    result = _call_api(prompt, max_completion_tokens=4000, model_id=model_id)
    parsed = _parse_json_response(result)

    return {
        "id": "impact",
        "title": "効果試算",
        **parsed,
    }


# ============================================================
# 2. 実行ロードマップ（roadmap）
# ============================================================

def generate_roadmap(
    selection: dict,
    model_id: str = DEFAULT_MODEL_ID,
) -> dict:
    """
    実行ロードマップセクションを生成する。
    フェーズごとに「やること」と「理想状態」を簡潔に示す。
    """
    selection_text = _build_selection_text(selection)

    prompt = f"""あなたは建設業の経営コンサルタントです。
以下の選定施策を踏まえ、実行ロードマップを生成してください。

【方針】
- 短期（0〜1年）・中期（1〜3年）・長期（3年以上）の3フェーズで構成。
- 各フェーズに「やるべきこと」を2〜3行の箇条書きと、「理想状態」を1文で記載する。
- やるべきことは施策横断で、当社の規模・体制で実現可能な範囲に留める。

【選定施策】
{selection_text}

【出力形式（JSON）】
{{
  "short_term": {{
    "actions": ["やるべきこと1", "やるべきこと2"],
    "ideal_state": "このフェーズ終了時の理想状態（1文）"
  }},
  "mid_term": {{
    "actions": ["やるべきこと1", "やるべきこと2"],
    "ideal_state": "このフェーズ終了時の理想状態（1文）"
  }},
  "long_term": {{
    "actions": ["やるべきこと1", "やるべきこと2"],
    "ideal_state": "このフェーズ終了時の理想状態（1文）"
  }}
}}

【制約】
- JSON形式のみで回答。
- 各フェーズのactionsは2〜3項目、各項目は1行（40字以内）。
- ideal_stateは1文（60字以内）。
- 全体で800字以内。"""

    logger = logging.getLogger(__name__)
    result = _call_api(prompt, max_completion_tokens=3000, model_id=model_id)
    logger.info(f"  ロードマップAPI応答(先頭300字): {result[:300]}")
    parsed = _parse_json_response(result)
    logger.info(f"  ロードマップparse結果キー: {list(parsed.keys())}")

    return {
        "id": "roadmap",
        "title": "実行ロードマップ",
        "short_term": parsed.get("short_term", {}),
        "mid_term": parsed.get("mid_term", {}),
        "long_term": parsed.get("long_term", {}),
    }


# ============================================================
# 3. リスクと対応策（risks）
# ============================================================

def generate_risks(
    selection: dict,
    model_id: str = DEFAULT_MODEL_ID,
) -> dict:
    """
    リスクと対応策セクションを生成する。
    Mid レベル: 施策に紐づくリスク + 対応策 + trigger/signal。
    selection内の地域性適合理由・業界特性適合理由に外部環境情報は含まれている。
    """
    selection_text = _build_selection_text(selection)

    prompt = f"""あなたは建設業の経営コンサルタントです。
以下の選定施策を踏まえ、リスクと対応策セクションを生成してください。

【方針】
- リスクは3種類に分けて各1件ずつ:
  1. 実行リスク: 施策の実行段階で発生しうるリスク（施策に紐づけて具体的に）
  2. 外部環境リスク: 市場・規制・マクロ環境の変化によるリスク
  3. 代替案: 施策が想定通り進まない場合の次善策
- 各リスクにtrigger_or_signal（早期警戒指標）を設定する。
  例: 「受注高が前年比▲15%を下回った場合」「営業利益率が2%を下回った場合」
- 対応策は具体的かつ実行可能な内容にする。

【選定施策（地域性・業界特性の根拠を含む）】
{selection_text}

【出力形式（JSON）】
{{
  "risks": [
    {{
      "risk_type": "実行リスク",
      "risk": "リスクの内容（施策名を明示、100字程度）",
      "mitigation": "対応策（100字程度）",
      "trigger_or_signal": "早期警戒指標（定量的な閾値を含む）"
    }},
    {{
      "risk_type": "外部環境リスク",
      "risk": "リスクの内容（100字程度）",
      "mitigation": "対応策（100字程度）",
      "trigger_or_signal": "早期警戒指標"
    }},
    {{
      "risk_type": "代替案",
      "risk": "施策が進まない場合のシナリオ（100字程度）",
      "mitigation": "代替アプローチ（100字程度）",
      "trigger_or_signal": "撤退・方針変更の判断基準"
    }}
  ]
}}

【制約】
- JSON形式のみで回答。
- リスクは必ず3件（実行リスク・外部環境リスク・代替案）。
- 全体で1000字以内。
- trigger_or_signalは可能な限り定量的な基準を含める。"""

    result = _call_api(prompt, max_completion_tokens=3000, model_id=model_id)
    parsed = _parse_json_response(result)

    return {
        "id": "risks",
        "title": "リスクと対応策",
        "risks": parsed.get("risks", []),
    }


# ============================================================
# 統合実行
# ============================================================

def generate_all(
    selection: dict,
    financial_indices: dict,
    model_id: str = DEFAULT_MODEL_ID,
) -> dict:
    """効果試算・ロードマップ・リスクの3セクションを一括生成する。"""
    logger = logging.getLogger(__name__)

    logger.info("  [1/3] 効果試算を生成中...")
    impact = generate_impact(selection, financial_indices, model_id=model_id)
    logger.info("  [1/3] 効果試算 完了")

    logger.info("  [2/3] ロードマップを生成中...")
    roadmap = generate_roadmap(selection, model_id=model_id)
    logger.info("  [2/3] ロードマップ 完了")

    logger.info("  [3/3] リスクと対応策を生成中...")
    risks = generate_risks(selection, model_id=model_id)
    logger.info("  [3/3] リスクと対応策 完了")

    return {
        "企業コード": selection.get("企業コード", "unknown"),
        "filename": selection.get("filename", ""),
        "impact": impact,
        "roadmap": roadmap,
        "risks": risks,
    }


# ============================================================
# CLI エントリポイント
# ============================================================

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    parser = argparse.ArgumentParser(
        description="選定施策に基づく効果試算・ロードマップ・リスク対応策の生成"
    )
    parser.add_argument("-s", "--selection", required=True,
                        help="施策選定JSONファイル（例: solution_selection_12044.json）")
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

    with open(args.selection, "r", encoding="utf-8") as f:
        selection = json.load(f)

    code = selection.get("企業コード", _extract_code(selection.get("filename", "")))
    logger.info(f"対象企業コード: {code}")

    # 財務指標の読み込み（per-company → 全企業ファイルの順で自動検出）
    financial_indices = {}
    per_company_path = os.path.join(
        base_dir, "data", "medium-output", "report-extraction",
        "financial-indices-per-company", f"financial_indices_{code}.json"
    )
    all_indices_path = os.path.join(
        base_dir, "data", "medium-output", "report-extraction", "financial_indices.json"
    )
    if os.path.exists(per_company_path):
        with open(per_company_path, "r", encoding="utf-8") as f:
            financial_indices = json.load(f)
        logger.info("  財務指標: あり")
    elif os.path.exists(all_indices_path):
        with open(all_indices_path, "r", encoding="utf-8") as f:
            all_data = json.load(f)
        financial_indices = all_data.get(code, {})
        if financial_indices:
            logger.info("  財務指標: あり")
        else:
            logger.warning(f"  財務指標: コード '{code}' が見つかりません")
    else:
        logger.warning("  財務指標: なし")

    # --- 生成実行 ---
    logger.info("生成開始...")
    result = generate_all(
        selection=selection,
        financial_indices=financial_indices,
        model_id=args.model,
    )

    # --- 保存 ---
    output_dir = os.path.join(base_dir, "data", "medium-output", "solution-selection", "roadmaps-per-company")
    output_path = args.output or os.path.join(output_dir, f"roadmap_{code}.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info(f"保存完了: {output_path}")

    # サマリー表示
    impact = result.get("impact", {})
    roadmap = result.get("roadmap", {})
    risks = result.get("risks", {})
    logger.info(f"  効果試算: 仮定{len(impact.get('assumptions', []))}件, "
                f"定性効果{len(impact.get('qualitative_impact', {}).get('effects', []))}件")
    logger.info(f"  ロードマップ: 短期{len(roadmap.get('short_term', []))}件, "
                f"中期{len(roadmap.get('mid_term', []))}件, "
                f"長期{len(roadmap.get('long_term', []))}件")
    logger.info(f"  リスク: {len(risks.get('risks', []))}件")

    logger.info("処理完了。")


if __name__ == "__main__":
    main()
