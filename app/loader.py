from pypdf import PdfReader
import os

class PDFLoader:
    def __init__(self):
        pass

    def load_text(self, file_path: str, max_pages: int = 15, keywords: list = None) -> str:
        """
        PDFファイルからテキストを抽出する。
        キーワードが指定された場合、そのキーワードが含まれる周辺ページを優先的に抽出する。
        
        Args:
            file_path (str): PDFファイルのパス
            max_pages (int): 読み込む最大ページ数
            keywords (list): 重要ページの検索に使用するキーワードリスト
            
        Returns:
            str: 抽出されたテキスト
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            reader = PdfReader(file_path)
            total_pages = len(reader.pages)
            extracted_text = []
            
            # キーワード検索モード
            if keywords:
                target_pages = set()
                # 全ページを走査してキーワードを探す（重い場合は要調整だが、有報程度なら許容範囲）
                # ただし、効率化のため最初の100ページ程度に限定する等の対策も考えられる
                search_limit = min(total_pages, 50) 
                
                for i in range(search_limit):
                    text = reader.pages[i].extract_text()
                    if text:
                        for kw in keywords:
                            if kw in text:
                                target_pages.add(i)
                                break
                
                # 見つかったページとその次ページを取得
                sorted_pages = sorted(list(target_pages))
                final_pages = []
                for p in sorted_pages:
                    if p not in final_pages:
                        final_pages.append(p)
                    if p + 1 < total_pages and (p + 1) not in final_pages:
                        final_pages.append(p + 1)
                        
                # ページ制限
                pages_to_read = final_pages[:max_pages]
                
                # キーワードが見つからなかった、またはページ数が足りない場合は冒頭から埋める
                if len(pages_to_read) < max_pages:
                    for i in range(total_pages):
                        if i not in pages_to_read:
                            pages_to_read.append(i)
                            if len(pages_to_read) >= max_pages:
                                break
                
                pages_to_read.sort()
                
            else:
                # 通常モード（冒頭から）
                pages_to_read = range(min(total_pages, max_pages))
            
            for i in pages_to_read:
                page_text = reader.pages[i].extract_text()
                if page_text:
                    extracted_text.append(page_text)
            
            return "\n".join(extracted_text)
            
        except Exception as e:
            print(f"Error reading PDF {file_path}: {e}")
            return ""
