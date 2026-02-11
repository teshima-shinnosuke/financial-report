"""
Stage 4: Final Assembly
各パイプライン出力を最終JSON（final_report_*.json）に組み立てる。
LLM呼び出しなし。全てプログラム的マッピング。

Usage:
    uv run app/final-assembly/main.py \\
        --code 12044 \\
        --executive-summary  data/final-output/executive-summary-per-company/executive_summary_12044.json \\
        --local-features     data/medium-output/issue-extraction/local-features-per-company/local_features_12044_v1.json \\
        --report-scores      data/medium-output/issue-extraction/report-scores-per-company/report_scores_12044_v1.json \\
        --solution-selection data/medium-output/solution-selection/solution-selection-per-company/solution_selection_12044.json \\
        --roadmap            data/medium-output/solution-selection/roadmaps-per-company/roadmap_12044.json \\
        -o data/final-output/final-report-per-company/final_report_12044.json
"""

import argparse
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 静的ファイル（全社共通）
FINANCIAL_INDICES_PATH = os.path.join(DATA_DIR, "medium-output/report-extraction/financial_indices.json")
SOLUTION_MASTER_PATH = os.path.join(DATA_DIR, "input/solution.json")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# ソースファイル読み込み
# ---------------------------------------------------------------------------

def load_sources(args) -> dict:
    """CLI引数で指定されたファイルを読み込む。"""
    sources = {}

    for key, path in [
        ("executive_summary", args.executive_summary),
        ("local_features", args.local_features),
        ("report_scores", args.report_scores),
        ("solution_selection", args.solution_selection),
        ("roadmap", args.roadmap),
    ]:
        if path and os.path.exists(path):
            sources[key] = load_json(path)
        else:
            if path:
                print(f"[WARN] {key}: {path} not found")
            sources[key] = None

    # financial_indices (全社まとめファイル・静的)
    if os.path.exists(FINANCIAL_INDICES_PATH):
        all_indices = load_json(FINANCIAL_INDICES_PATH)
        sources["financial_indices"] = all_indices.get(args.code)
        if not sources["financial_indices"]:
            print(f"[WARN] financial_indices entry not found for {args.code}")
    else:
        print(f"[WARN] financial_indices.json not found")
        sources["financial_indices"] = None

    # solution.json (施策マスタ・静的)
    sources["solution_master"] = load_json(SOLUTION_MASTER_PATH) if os.path.exists(SOLUTION_MASTER_PATH) else {}

    return sources


# ---------------------------------------------------------------------------
# マッピング関数
# ---------------------------------------------------------------------------

INDUSTRY_ENVIRONMENT = {
    "pest": {
        "political": "市場区分見直し後、プライム企業数は減少傾向にあります（2022年末1,838社→2025年末1,599社）。防災・減災・国土強靭化が需要の下支えとなっております。",
        "economic": "建設業セクターは2023年以降に急伸しております（配当込み指数+165.5%、TOPIX+93.8%）。プライム建設業の時価総額は約31.3兆円に拡大し、利回りは3.68%→2.40%へ圧縮されております。",
        "social": "生産年齢人口の減少と担い手の高齢化が顕在化しております。2024年問題（労働時間制約）が供給能力を構造的に制約する状況にあります。",
        "technological": "BIM/CIM・遠隔臨場・現場IoT・ICT施工が競争力の源泉へ移行しつつあります。地域企業におかれましては、SaaS型・共同利用型での導入が現実的と考えられます。",
    },
    "demand_supply": {
        "都市部": "民間非住宅・再開発・物流施設・インフラ更新など、大型・複合案件が集積しております。",
        "地方": "新設需要は人口要因により縮小傾向にございます。維持修繕・防災・国土強靭化など公共性の高い需要が相対的に重要度を増しております。",
        "構造変化": "担い手制約が受注可能量を絞り込み、価格転嫁・選別受注・高付加価値化・DX投資を促す産業再編圧力として作用しております。",
    },
    "capital_market": {
        "大手ゼネコン": "海外投資家を含む機関投資家の市場規律が直接作用しており、資本コストに基づく経営説明が求められております。",
        "地域建設企業": "資本市場からの要請は、流動性不足・上場維持コスト・M&A（TOB/MBO）による再編圧力として表面化しております。",
    },
    "scenarios": {
        "楽観": "更新・防災需要が堅調に推移し、供給制約を背景に価格転嫁・選別受注が定着いたします。量より質への転換により利益率の向上が見込まれます。",
        "ベース": "需要は緩やかに縮小する一方、維持修繕・公共土木が下支えとなります。地域内連携・共同DXを推進された企業が競争力を維持されると想定されます。",
        "悲観": "担い手の高齢化が想定以上に進行し、供給能力が急落いたします。資本力・人材確保力の差により淘汰圧力が強まり、M&A・上場廃止が加速する恐れがございます。",
    },
}

FINANCIAL_TAG = "財務・資本政策・ガバナンス"


def shorten_item_name(item_text: str) -> str:
    """スコアリング項目の長い文章から短い項目名を抽出する。"""
    text = re.sub(r"^\d+\.\s*", "", item_text)
    m = re.split(r"について[、，,]?", text)
    if len(m) >= 2 and m[0]:
        return m[0].strip()
    m = re.split(r"[。、]", text)
    return m[0].strip() if m[0] else text[:30]


def extract_scores(scores_data) -> list[dict]:
    """report_scores_*.json からスコアリスト（tag別）を取得。"""
    if isinstance(scores_data, list):
        if len(scores_data) > 0:
            return scores_data[0].get("scores", [])
        return []
    return scores_data.get("scores", [])


def build_tag_items(tag_data: dict) -> dict:
    """tag の items を {短縮名: score} の辞書に変換。"""
    result = {}
    for item in tag_data.get("items", []):
        short_name = shorten_item_name(item["item"])
        result[short_name] = item["score"]
    return result


def find_solution_in_master(initiative_name: str, master: dict) -> list[dict]:
    """施策名で solution.json を部分一致検索し、実例的根拠を返す。"""
    if initiative_name in master:
        return master[initiative_name].get("実例的根拠", [])
    for key, val in master.items():
        if initiative_name in key or key in initiative_name:
            return val.get("実例的根拠", [])
    return []


def parse_strengths_constraints(local_features: dict) -> tuple[list[str], list[str]]:
    """local_features の全体の地域的特徴テキストから強み・制約を分離。"""
    text = local_features.get("全体の地域的特徴", "")
    sentences = re.split(r"[。]", text)
    strengths = []
    constraints = []
    strength_keywords = ["強み", "ポテンシャル", "活かし", "担保", "機会"]
    constraint_keywords = ["課題", "脆弱", "リスク", "圧迫", "マイナス", "制約"]

    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if any(k in s for k in strength_keywords):
            strengths.append(s)
        elif any(k in s for k in constraint_keywords):
            constraints.append(s)

    return strengths, constraints


# ---------------------------------------------------------------------------
# メイン組み立て
# ---------------------------------------------------------------------------

def assemble(code: str, sources: dict) -> dict:
    """全ソースから最終JSONを組み立てる。"""

    exec_sum = sources.get("executive_summary") or {}
    fi = sources.get("financial_indices") or {}
    lf = sources.get("local_features") or {}
    ss = sources.get("solution_selection") or {}
    rm = sources.get("roadmap") or {}
    solution_master = sources.get("solution_master", {})

    # --- company_and_region ---
    company_and_region = {
        "企業情報": fi.get("企業情報", {}),
        "事業・営業・受注戦略の地域的特徴": lf.get("事業・営業・受注戦略の地域的特徴", ""),
        "人的資本の地域的特徴": lf.get("人的資本の地域的特徴", ""),
        "財務構造の地域的特徴": lf.get("財務構造の地域的特徴", ""),
        "全体の地域的特徴": lf.get("全体の地域的特徴", ""),
    }

    # --- analysis ---
    tag_averages = ss.get("tag_averages", {})
    scores_list = extract_scores(sources.get("report_scores"))

    financial_tag_data = None
    qualitative_tags = []
    for tag_data in scores_list:
        if tag_data["tag"] == FINANCIAL_TAG:
            financial_tag_data = tag_data
        else:
            qualitative_tags.append(tag_data)

    financial_analysis = {
        "key_metrics": fi.get("指標", []),
        "tag": FINANCIAL_TAG,
        "avg_score": tag_averages.get(FINANCIAL_TAG, 0),
        "items": build_tag_items(financial_tag_data) if financial_tag_data else {},
        "summary": financial_tag_data.get("summary", "") if financial_tag_data else "",
    }

    qual_tags_output = []
    for td in qualitative_tags:
        qual_tags_output.append({
            "tag": td["tag"],
            "avg_score": tag_averages.get(td["tag"], 0),
            "items": build_tag_items(td),
            "summary": td.get("summary", ""),
        })
    qual_tags_output.sort(key=lambda x: x["avg_score"])

    # --- strategy: initiatives ---
    selected = ss.get("selected_solutions", [])[:3]

    # --- strategy: fit_to_company ---
    fit_parts = []
    for sol in selected:
        fit_parts.append(sol.get("地域性適合理由", ""))
        fit_parts.append(sol.get("業界特性適合理由", ""))
    fit_narrative = "\n".join(p for p in fit_parts if p)

    comparisons = []
    for sol in selected:
        examples = find_solution_in_master(sol["施策名"], solution_master)
        for ex in examples:
            comparisons.append({
                "企業名": ex.get("企業名", ""),
                "証券コード": ex.get("証券コード", ""),
                "施策として読み取れる具体的記述": ex.get("施策として読み取れる具体的記述", ""),
            })

    strengths, constraints = parse_strengths_constraints(lf)

    # --- 組み立て ---
    return {
        "meta": {
            "company_code": code,
            "filename": ss.get("filename", lf.get("ファイル名", "")),
            "language": "ja",
        },
        "sections": [
            {
                "id": "executive_summary",
                "title": "エグゼクティブサマリー",
                "content": exec_sum.get("content", ""),
                "char_count": exec_sum.get("char_count", 0),
            },
            {
                "id": "company_overview",
                "title": "企業概要と外部環境",
                "subsections": [
                    {
                        "id": "company_and_region",
                        "title": "企業概要と地域特性",
                        "content": company_and_region,
                    },
                    {
                        "id": "industry_environment",
                        "title": "業界環境",
                        "content": INDUSTRY_ENVIRONMENT,
                    },
                ],
            },
            {
                "id": "analysis",
                "title": "分析と経営課題",
                "content": {
                    "tag_averages": tag_averages,
                    "financial_analysis": financial_analysis,
                    "qualitative_tags": qual_tags_output,
                },
            },
            {
                "id": "strategy",
                "title": "成長戦略・提案内容",
                "subsections": [
                    {
                        "id": "initiatives",
                        "title": "具体施策",
                        "content": {"initiatives": selected},
                    },
                    {
                        "id": "fit_to_company",
                        "title": "当社で成立する理由",
                        "content": {
                            "fit_narrative": fit_narrative,
                            "comparison": comparisons,
                            "company_specific_strengths": strengths,
                            "company_specific_constraints": constraints,
                        },
                    },
                ],
            },
            {
                "id": "impact",
                "title": "効果試算",
                "content": rm.get("impact", {}),
            },
            {
                "id": "roadmap",
                "title": "実行ロードマップ",
                "content": rm.get("roadmap", {}),
            },
            {
                "id": "risks",
                "title": "リスクと対応策",
                "content": rm.get("risks", {}),
            },
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Final Assembly: 最終レポートJSONを生成")
    parser.add_argument("--code", type=str, required=True, help="企業コード (例: 12044)")

    # 動的ファイル（企業ごとに指定）
    parser.add_argument("--executive-summary", type=str, required=True, help="executive_summary_*.json のパス")
    parser.add_argument("--local-features", type=str, required=True, help="local_features_*.json のパス")
    parser.add_argument("--report-scores", type=str, required=True, help="report_scores_*.json のパス")
    parser.add_argument("--solution-selection", type=str, required=True, help="solution_selection_*.json のパス")
    parser.add_argument("--roadmap", type=str, required=True, help="roadmap_*.json のパス")

    # 出力
    parser.add_argument("-o", "--output", type=str, default=None, help="出力先パス (デフォルト: data/final-output/final-report-per-company/final_report_{code}.json)")

    args = parser.parse_args()

    output_path = args.output or os.path.join(
        DATA_DIR, "final-output", "final-report-per-company", f"final_report_{args.code}.json"
    )

    print(f"Code: {args.code}")
    print(f"Input files:")
    print(f"  executive-summary:  {args.executive_summary}")
    print(f"  local-features:     {args.local_features}")
    print(f"  report-scores:      {args.report_scores}")
    print(f"  solution-selection: {args.solution_selection}")
    print(f"  roadmap:            {args.roadmap}")
    print(f"  financial-indices:  {FINANCIAL_INDICES_PATH} (静的)")
    print(f"  solution-master:    {SOLUTION_MASTER_PATH} (静的)")
    print(f"Output: {output_path}")
    print()

    sources = load_sources(args)
    result = assemble(args.code, sources)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"-> {output_path}")
    print("Done.")


if __name__ == "__main__":
    main()
