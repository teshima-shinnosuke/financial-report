import os
import json
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

# .env ファイルをロード
load_dotenv()

DEFAULT_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

def summarize_all_strategies(text: str, model_id: str = DEFAULT_MODEL_ID, api_key: str = None) -> str:
    """
    財務、マーケティング、人事の3つの戦略を一度に要約し、JSON形式で返す
    
    Args:
        text (str): 要約対象のテキスト
        model_id (str): 使用するモデルID
        api_key (str): Hugging Face APIトークン
        
    Returns:
        str: JSON形式の文字列
    """
    if not text:
        return "{}"

    prompt = """
あなたは優秀な証券アナリストです。
以下の有価証券報告書の抜粋から、「財務戦略」「マーケティング戦略」「人事戦略」の3つの観点で要約を作成してください。

【制約事項】
1. 出力は**必ず**以下のJSON形式のみにしてください。Markdownのコードブロック（```json ... ```）は不要です。
2. 各戦略の要約は200文字程度にしてください。
3. 該当する情報がない場合は「該当情報なし」としてください。

【出力フォーマット（JSON）】
{
  "財務戦略": "要約内容...",
  "マーケティング戦略": "要約内容...",
  "人事戦略": "要約内容..."
}

【テキスト】
""" + text

    return _call_api(prompt, max_length=1500, model_id=model_id, api_key=api_key)

def _call_api(prompt: str, max_length: int, model_id: str, api_key: str = None) -> str:
    """
    APIを呼び出して結果を取得する内部関数
    """
    client = InferenceClient(api_key=api_key)
    
    messages = [
        {"role": "user", "content": prompt}
    ]

    try:
        response = client.chat_completion(
            model=model_id,
            messages=messages,
            max_tokens=max_length * 2,
            temperature=0.3, # 少し創造性をもたせるが、フォーマット遵守のため低め
            response_format={"type": "json"},
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        # エラー時もJSONとしてパース可能な形あるいはエラーメッセージを返す
        error_json = {
            "error": f"Error occurred during summarization: {str(e)}"
        }
        return json.dumps(error_json, ensure_ascii=False)

# 使用例
if __name__ == "__main__":
    sample_text = "（サンプルのため省略）"
    # print(summarize_all_strategies(sample_text))
