import os
import sys

# スクリプトのディレクトリ（app/）をsys.pathに追加して、直接実行した場合でもインポートできるようにする
# ただし、基本はルートから execute することを想定
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from summarizer import summarize_all_strategies
    from loader import PDFLoader
except ImportError:
    from app.summarizer import summarize_all_strategies
    from app.loader import PDFLoader

from dotenv import load_dotenv

def main():
    # .env ファイルをロード
    load_dotenv()
    
    if not os.getenv("HF_TOKEN"):
        print("Warning: HF_TOKEN is not set in environment variables. Please set it in .env file.")
        
    loader = PDFLoader()
    
    # dataディレクトリのパス
    # このスクリプトが app/main.py にあると仮定して、親ディレクトリの data/ を参照
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_data_dir = os.path.join(base_dir, "data")
    
    import argparse
    parser = argparse.ArgumentParser(description='Summarize financial reports.')
    parser.add_argument('input_path', nargs='?', default=default_data_dir, 
                        help='Path to a PDF file or a directory containing PDFs')
    args = parser.parse_args()
    
    input_path = args.input_path
    
    pdf_files = []
    
    if os.path.isfile(input_path):
        if input_path.lower().endswith('.pdf'):
            pdf_files.append(input_path)
        else:
            print(f"Error: {input_path} is not a PDF file.")
            return
    elif os.path.isdir(input_path):
        if not os.path.exists(input_path):
             print(f"Directory not found: {input_path}")
             return
        # PDFファイルを取得
        files = [os.path.join(input_path, f) for f in os.listdir(input_path) if f.lower().endswith('.pdf')]
        pdf_files.extend(files)
        if not pdf_files:
            print(f"No PDF files found in directory: {input_path}")
            return
        print(f"Found {len(pdf_files)} PDF files in {input_path}.\n")
    else:
        print(f"Error: Input path not found: {input_path}")
        return

    import json
    import time
    import re
    import glob
    import logging

    # ログ設定
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processing.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)

    results = []
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "security_report_summarize.json")
    
    # 読み込み元ディレクトリ (TXT)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    txt_dir = os.path.join(project_root, "data", "txt")
    txt_files = glob.glob(os.path.join(txt_dir, "*.txt"))
    logger.info(f"Found {len(txt_files)} TXT files in {txt_dir}.")

    # 既存の結果があれば読み込む（追記モード的な挙動のため）
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
            logger.info(f"Loaded {len(results)} existing summaries.")
        except json.JSONDecodeError:
            logger.error("Existing JSON file is corrupt inside. Starting fresh.")
            results = []
    
    # 処理済みファイルの判定マップ (filename -> index in results)
    processed_map = {}
    for i, item in enumerate(results):
        base_name = os.path.splitext(item["filename"])[0]
        summaries = item.get("summaries", {})
        if isinstance(summaries, dict) and "error" not in summaries and "財務戦略" in summaries:
             processed_map[base_name] = i

    for file_path in txt_files:
        filename_txt = os.path.basename(file_path)
        base_name = os.path.splitext(filename_txt)[0]
        filename_pdf = base_name + ".pdf" 
        
        # 既に成功して処理済みならスキップ
        if base_name in processed_map:
            logger.info(f"Skipping {filename_pdf} (already successfully processed).")
            continue

        logger.info(f"Processing: {filename_txt}...")
        
        # 既存の結果（エラー含む）があるか探す
        existing_result_index = -1
        for i, item in enumerate(results):
            if os.path.splitext(item["filename"])[0] == base_name:
                existing_result_index = i
                break
        
        # テキスト読み込み (TXTファイルから直接)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            logger.error(f"  -> Failed to read text file: {e}")
            continue
        
        if not text:
            logger.warning(f"  -> Text file is empty.")
            continue
            
        # 要約の実行 (全文)
        input_text = text
        
        # 3つの観点で一括要約
        logger.info(f"  -> Summarizing strategies (API Call) with {len(input_text)} chars...")
        
        # APIのレート制限回避のため少し待機
        time.sleep(2) 
        
        # 関数呼び出し
        json_str = summarize_all_strategies(input_text)
        
        # JSONパースの試行
        extracted_summaries = {}
        try:
            # RegexでJSONブロックを探す ({...})
            match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if match:
                cleaned_json_str = match.group(0)
                extracted_summaries = json.loads(cleaned_json_str)
            else:
                raise json.JSONDecodeError("No JSON object found", json_str, 0)
                
            logger.info(f"  -> Successfully summarized strategies.")
            
        except json.JSONDecodeError:
            logger.error(f"  !! Failed to parse JSON response. Saving raw output.")
            logger.debug(f"Raw output: {json_str}")
            extracted_summaries = {
                "error": "JSON parse error",
                "raw_output": json_str,
                # フォールバック用の空データ
                "財務戦略": "取得失敗",
                "マーケティング戦略": "取得失敗",
                "人事戦略": "取得失敗"
            }
        
        # エラーチェック (APIエラーなど)
        if "error" in extracted_summaries and isinstance(extracted_summaries, dict):
             error_msg = extracted_summaries.get("error", "")
             # raw_output自体がAPIエラーメッセージの場合もある
             raw_out = extracted_summaries.get("raw_output", "")
             
             if "402" in error_msg or "Payment Required" in str(raw_out):
                 logger.critical("  !! API Quota Exceeded. Stopping processing.")
                 return

        file_summary = {
            "filename": filename_pdf, # 出力は一貫性を保つためPDF名にする
            "summaries": extracted_summaries
        }
        
        # 既存のエントリーがあれば更新、なければ追加
        if existing_result_index != -1:
            results[existing_result_index] = file_summary
        else:
            results.append(file_summary)
        
        # 1文書ごとに保存 (安全策)
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            logger.info(f"  -> Saved progress to {output_file}")
        except Exception as e:
            logger.error(f"Error saving to JSON: {e}")
            
        print("-" * 50 + "\n")
        
        # 次のファイルへ行く前に少し長めに待機
        time.sleep(5)

    logger.info(f"All processing completed. Saved to {output_file}")

if __name__ == "__main__":
    main()
