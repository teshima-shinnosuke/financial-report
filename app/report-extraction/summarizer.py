import json
import re
import time
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

# .env ファイルをロード
load_dotenv()

DEFAULT_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

# プロンプト分のトークンと出力トークンを考慮した安全なチャンクサイズ（文字数）
# モデル上限: 32,769トークン、日本語1文字≈1.5トークンとして余裕を持たせる
MAX_CHUNK_CHARS = 18000

STRATEGIES = [
    "企業概要",
    "人的資本戦略",
    "財務戦略",
    "マーケティング戦略",
    "オペレーション戦略",
    "リスク管理",
    "サステナビリティ戦略",
]


def _split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """テキストをチャンクに分割する"""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:max_chars])
        text = text[max_chars:]
    return chunks


def summarize_all_strategies(text: str, model_id: str = DEFAULT_MODEL_ID, api_key: str = None) -> str:
    """
    7つの観点から要約し、JSON形式で返す。
    テキストが長い場合はチャンク分割 → 部分要約 → マージの流れで処理する。
    """
    if not text:
        return "{}"

    chunks = _split_text(text)

    if len(chunks) == 1:
        return _summarize_chunk(chunks[0], model_id=model_id, api_key=api_key)

    # 複数チャンク: 各チャンクを要約してからマージ
    partial_summaries = []
    for i, chunk in enumerate(chunks):
        result = _summarize_chunk(chunk, model_id=model_id, api_key=api_key)
        partial_summaries.append(result)
        if i < len(chunks) - 1:
            time.sleep(2)

    return _merge_summaries(partial_summaries, model_id=model_id, api_key=api_key)


def _summarize_chunk(text: str, model_id: str = DEFAULT_MODEL_ID, api_key: str = None) -> str:
    """1チャンク分の要約を実行"""
    prompt = """
あなたは優秀な証券アナリストです。
以下の有価証券報告書の抜粋から、7つの観点で要約を作成してください。

【制約事項】
1. 出力は**必ず**以下のJSON形式のみにしてください。Markdownのコードブロック（```json ... ```）は不要です。
2. 各項目の要約は200文字程度にしてください。
3. 該当する情報がない場合は「該当情報なし」としてください。

【出力フォーマット（JSON）】
{
  "企業概要": "会社の基本情報、事業内容、沿革の要約...",
  "人的資本戦略": "人材育成、ダイバーシティ、働き方改革の要約...",
  "財務戦略": "売上・利益目標、コスト管理、キャッシュフローの要約...",
  "マーケティング戦略": "営業方針、顧客戦略、事業展開の要約...",
  "オペレーション戦略": "DX推進、生産性向上、業務効率化の要約...",
  "リスク管理": "事業リスクとその対応策の要約...",
  "サステナビリティ戦略": "ESG、環境対応、脱炭素の取り組みの要約..."
}

【テキスト】
""" + text

    return _call_api(prompt, max_tokens=3000, model_id=model_id, api_key=api_key)


def _merge_summaries(partial_results: list[str], model_id: str = DEFAULT_MODEL_ID, api_key: str = None) -> str:
    """複数チャンクの部分要約を統合する"""
    combined = "\n---\n".join(partial_results)

    prompt = """
以下は同一の有価証券報告書を複数パートに分けて要約した結果です。
これらを統合して、7つの観点で最終的な要約を1つのJSONにまとめてください。

【制約事項】
1. 出力は**必ず**以下のJSON形式のみにしてください。
2. 各項目の要約は200文字程度にしてください。
3. 各パートの情報を統合・補完してください。

【出力フォーマット（JSON）】
{
  "企業概要": "統合した要約...",
  "人的資本戦略": "統合した要約...",
  "財務戦略": "統合した要約...",
  "マーケティング戦略": "統合した要約...",
  "オペレーション戦略": "統合した要約...",
  "リスク管理": "統合した要約...",
  "サステナビリティ戦略": "統合した要約..."
}

【部分要約】
""" + combined

    return _call_api(prompt, max_tokens=3000, model_id=model_id, api_key=api_key)


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
