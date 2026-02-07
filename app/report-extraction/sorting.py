import json
import re
import time
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

# .env ファイルをロード
load_dotenv()

DEFAULT_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

# 有価証券報告書の分析用タグ（8分類 + その他）
PAGE_TAGS = [
    "経営戦略・中期ビジョン（経営理念、パーパス、中期経営計画、経営課題、重点テーマ、KPI・目標値）",
    "事業・営業・受注戦略（事業ポートフォリオ、セグメント構成、公共/民間比率、提案型営業、選別受注、顧客・案件特性）",
    "生産性・施工オペレーション（施工体制、原価管理、VE・工法改善、BIM/CIM、ICT施工、現場DX）",
    "人的資本・組織運営（人材確保・定着、育成・研修、処遇・賃金、ダイバーシティ、働き方改革・2024年問題）",
    "技術・DX・研究開発（DX推進体制、自社システム・内製化、技術差別化、研究開発テーマ）",
    "サステナビリティ・社会的責任（脱炭素・GX、安全衛生、人権・労働環境、地域貢献、TCFD・ESG指標）",
    "財務・資本政策・ガバナンス（財務パフォーマンス、キャッシュフロー、資本政策・株主還元、ガバナンス体制）",
    "リスクマネジメント・コンプライアンス（市場・価格リスク、人材リスク、災害・BCP、法規制、情報セキュリティ）",
    "その他（表紙、目次、監査報告書、株式事務など上記に該当しない箇所）",
]


def tag_pages(pages: list[dict], batch_size: int = 5, model_id: str = DEFAULT_MODEL_ID, api_key: str = None) -> list[dict]:
    """
    ページのリストを受け取り、batch_sizeページごとにAPIでセクション分割・タグ付けする。
    1ページ内の複数セクションをそれぞれ分割し、個別にタグを付与する。

    Args:
        pages: load_pages() の戻り値 [{"page": 1, "text": "..."}, ...]
        batch_size: 1回のAPI呼び出しで処理するページ数
        model_id: 使用するモデルID
        api_key: APIキー

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

【制約事項】
1. 出力は必ずJSON形式のみにしてください。
2. キーはページ番号（文字列）、値はセクションの配列にしてください。
3. 各セクションは {{"tag": "タグ名", "text": "該当テキスト"}} の形式にしてください。
4. tagは上記タグ一覧の番号なし名称部分（括弧内は含めない）を1つだけ選んでください。
5. テキストは原文をそのまま使い、要約や省略はしないでください。
6. 空白ページは {{"tag": "その他", "text": ""}} としてください。

【出力例】
{{"1": [{{"tag": "その他", "text": "有価証券報告書 提出日..."}}], "2": [{{"tag": "経営戦略・中期ビジョン", "text": "当社は..."}}]}}

【ページテキスト】
{pages_text}"""

        result = _call_api(prompt, max_tokens=8000, model_id=model_id, api_key=api_key)

        # レスポンスをパース
        try:
            match = re.search(r'\{.*\}', result, re.DOTALL)
            if match:
                tag_map = json.loads(match.group(0))
            else:
                tag_map = {}
        except json.JSONDecodeError:
            tag_map = {}

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
                        # tags (複数) が返ってきた場合は先頭を採用
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


def _call_api(prompt: str, max_tokens: int, model_id: str, api_key: str = None) -> str:
    """APIを呼び出して結果を取得する内部関数"""
    client = InferenceClient(api_key=api_key)

    messages = [
        {"role": "user", "content": prompt}
    ]

    try:
        response = client.chat_completion(
            model=model_id,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        error_json = {
            "error": f"Error occurred during summarization: {str(e)}"
        }
        return json.dumps(error_json, ensure_ascii=False)
