import json
import os
import re
import time
from openai import AzureOpenAI
from dotenv import load_dotenv

# .env ファイルをロード
load_dotenv()

DEFAULT_MODEL_ID = "gpt-5-mini"

# 有価証券報告書の分析用タグ（8分類 + その他）
PAGE_TAGS = [
    "経営戦略・中期ビジョン（経営理念、パーパス、中期経営計画、経営課題、重点テーマ、KPI・目標値）",
    "事業・営業・受注戦略（事業ポートフォリオ、セグメント構成、公共/民間比率、提案型営業、選別受注、顧客・案件特性）",
    "生産性・施工オペレーション（施工体制、原価管理、VE・工法改善、BIM/CIM、ICT施工、現場DX）",
    "人的資本・組織運営（人材確保・定着、育成・研修、処遇・賃金、ダイバーシティ、働き方改革・2024年問題）",
    "技術・DX・研究開発（DX推進体制、自社システム・内製化、技術差別化、研究開発テーマ）",
    "サステナビリティ・社会的責任（脱炭素・GX、安全衛生、人権・労働環境、地域貢献、TCFD・ESG指標）",
    "財務・資本政策（経営指標推移、財政状態・経営成績分析、キャッシュフロー分析、配当政策、資本政策・株主還元）",
    "ガバナンス体制（コーポレートガバナンス、取締役会・監査役会構成、内部統制、役員報酬）",
    "株式事務（株式の総数、新株予約権、発行済株式総数、所有者別状況、大株主の状況、自己株式の取得等）",
    "リスクマネジメント・コンプライアンス（市場・価格リスク、人材リスク、災害・BCP、法規制、情報セキュリティ）",
    "その他（表紙、目次、監査報告書など上記に該当しない箇所）",
]


def tag_pages(pages: list[dict], batch_size: int = 5, model_id: str = DEFAULT_MODEL_ID) -> list[dict]:
    """
    ページのリストを受け取り、batch_sizeページごとにAPIでセクション分割・タグ付けする。
    1ページ内の複数セクションをそれぞれ分割し、個別にタグを付与する。

    Args:
        pages: load_pages() の戻り値 [{"page": 1, "text": "..."}, ...]
        batch_size: 1回のAPI呼び出しで処理するページ数
        model_id: 使用するモデルID

    Returns:
        list[dict]: [{"page": 1, "sections": [{"tag": "経営戦略・中期ビジョン", "text": "..."}, ...]}, ...]
    """

    if not pages:
        return []

    tagged_pages = []
    tags_list = "\n".join(f"  {i+1}. {tag}" for i, tag in enumerate(PAGE_TAGS))

    for i in range(0, len(pages), batch_size):
        batch = pages[i:i + batch_size]

        # バッチ内の各ページの全文をまとめる
        pages_text = ""
        for p in batch:
            text = p["text"] if p["text"] else "（空白ページ）"
            pages_text += f"\n--- ページ {p['page']} ---\n{text}\n"

        prompt = f"""あなたは有価証券報告書の構造を理解する専門家です。
以下の各ページのテキストを読み、ページ内のセクションごとにテキストを分割し、最も適切なタグを1つ付けてください。

【タグ一覧（括弧内は小分類の参考キーワード）】
{tags_list}

【出力形式】
1. 出力は必ずJSON形式のみにしてください。説明文やコードブロック記法は不要です。
2. トップレベルは {{"pages": [...]}} とし、配列の各要素は {{"page": ページ番号(数値), "sections": [...]}} の形式にしてください。
3. sections内の各要素は {{"tag": "タグ名", "text": "該当テキスト"}} の形式にしてください。
4. tagは上記タグ一覧の番号なし名称部分（括弧内は含めない）を1つだけ選んでください。
5. テキストは原文をそのまま使い、要約や省略はしないでください。
6. 空白ページは {{"page": N, "sections": [{{"tag": "その他", "text": ""}}]}} としてください。

【期待する出力（この構造を厳守）】
{{"pages": [{{"page": 1, "sections": [{{"tag": "その他", "text": "【表紙】\\n【提出書類】 有価証券報告書\\n..."}}]}}, {{"page": 2, "sections": [{{"tag": "財務・資本政策・ガバナンス", "text": "第一部 【企業情報】\\n..."}}]}}, {{"page": 5, "sections": [{{"tag": "事業・営業・受注戦略", "text": "３ 【事業の内容】\\n..."}}, {{"tag": "人的資本・組織運営", "text": "４ 【関係会社の状況】\\n..."}}]}}]}}

【ページテキスト】
{pages_text}"""

        result = _call_api(prompt, max_completion_tokens=8000, model_id=model_id)

        # レスポンスをパース
        tag_map = {}
        try:
            match = re.search(r'\{.*\}', result, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                # 新形式: {"pages": [{"page": N, "sections": [...]}, ...]}
                if "pages" in parsed and isinstance(parsed["pages"], list):
                    for entry in parsed["pages"]:
                        if isinstance(entry, dict) and "page" in entry:
                            tag_map[str(entry["page"])] = entry.get("sections", [])
                else:
                    # 旧形式フォールバック: {"1": [...], "2": [...]}
                    tag_map = parsed
        except json.JSONDecodeError:
            pass

        for p in batch:
            sections = tag_map.get(str(p["page"]), [{"tag": "その他", "text": p["text"]}])
            # フォールバック処理
            if isinstance(sections, str):
                sections = [{"tag": "その他", "text": p["text"]}]
            elif isinstance(sections, list):
                normalized = []
                for s in sections:
                    if isinstance(s, str):
                        normalized.append({"tag": "その他", "text": s})
                    elif isinstance(s, dict):
                        if "tags" in s and "tag" not in s:
                            s["tag"] = s["tags"][0] if isinstance(s["tags"], list) and s["tags"] else "その他"
                            del s["tags"]
                        if "tag" not in s:
                            s["tag"] = "その他"
                        normalized.append(s)
                    else:
                        normalized.append({"tag": "その他", "text": ""})
                sections = normalized
            tagged_pages.append({"page": p["page"], "sections": sections})

        # バッチ間のレート制限
        if i + batch_size < len(pages):
            time.sleep(2)

    return tagged_pages


import argparse
import logging


def _extract_code(filename: str) -> str:
    match = re.search(r"(\d+)", filename)
    if match:
        return match.group(1)
    return re.sub(r"[^a-zA-Z0-9_]", "", os.path.splitext(filename)[0])


def _call_api(prompt: str, max_completion_tokens: int, model_id: str) -> str:
    """Azure OpenAI APIを呼び出して結果を取得する内部関数"""
    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version="2024-12-01-preview",
    )

    messages = [
        {"role": "user", "content": prompt}
    ]

    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            response_format={"type": "json_object"},
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        error_json = {
            "error": f"Error occurred during summarization: {str(e)}"
        }
        return json.dumps(error_json, ensure_ascii=False)


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    parser = argparse.ArgumentParser(description="1つのページ抽出JSONをタグ付けする")
    parser.add_argument("-i", "--input", required=True, help="入力JSONファイル（report_pages_*.json）")
    parser.add_argument("-o", "--output", default=None, help="出力JSONファイルパス（未指定時は自動生成）")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL_ID, help="使用するモデルID")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    logger = logging.getLogger(__name__)

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    # リスト形式の場合は先頭を取得
    if isinstance(data, list):
        data = data[0]

    filename = data.get("filename", "")
    code = _extract_code(filename)
    pages = data.get("pages", [])
    logger.info(f"対象: {filename} (コード: {code}, {len(pages)}ページ)")

    tagged_pages = tag_pages(pages, batch_size=5, model_id=args.model)
    logger.info(f"タグ付け完了: {len(tagged_pages)}ページ")

    result = {"filename": filename, "pages": tagged_pages}

    output_dir = os.path.join(base_dir, "data", "medium-output", "report-extraction", "report-tagged-per-company")
    output_path = args.output or os.path.join(output_dir, f"report_tagged_{code}.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info(f"保存完了: {output_path}")
