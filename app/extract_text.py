import os
import glob
import sys

# パス設定: プロジェクトルートをsys.pathに追加して app モジュールが見つかるようにする
sys.path.append(os.getcwd())

try:
    from app.loader import PDFLoader
except ImportError:
    # スクリプトとして直接実行された場合などのフォールバック
    from loader import PDFLoader

def main():
    # データディレクトリの設定
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    data_dir = os.path.join(project_root, "data")
    txt_dir = os.path.join(data_dir, "txt")
    
    if not os.path.exists(txt_dir):
        os.makedirs(txt_dir)
    
    # PDFファイルの取得
    pdf_files = glob.glob(os.path.join(data_dir, "*.pdf"))
    print(f"Found {len(pdf_files)} PDF files in {data_dir}.")
    
    loader = PDFLoader()
    
    for file_path in pdf_files:
        filename = os.path.basename(file_path)
        print(f"Processing: {filename}...")
        
        try:
            # テキスト抽出 (全ページ)
            text = loader.load_text(file_path)
            
            if not text:
                print(f"  -> Failed to extract text.")
                continue
                
            # 保存先のファイルパス
            txt_filename = os.path.splitext(filename)[0] + ".txt"
            txt_path = os.path.join(txt_dir, txt_filename)
            
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(text)
                
            print(f"  -> Saved to {txt_filename} ({len(text)} chars)")
            
        except Exception as e:
            print(f"  !! Error processing {filename}: {e}")

if __name__ == "__main__":
    main()
