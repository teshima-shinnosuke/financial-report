import csv
import json
import os
import argparse


# 列名の分類マッピング
COMPANY_INFO_COLS = [
    "コード", "本社所在地", "市場・商品区分",
    "従業員数（連結）", "資本金（億円）", "業種分類", "YEAR",
]

PL_COLS = {
    "売上高": {
        "売上高": "売上高",
        "売上高_商品売上高": "商品売上高",
        "売上高_完成工事高": "完成工事高",
        "売上高_不動産事業売上高": "不動産事業売上高",
    },
    "売上原価": {
        "売上原価": "売上原価",
        "売上原価_完成工事原価": "完成工事原価",
        "売上原価_不動産事業売上原価": "不動産事業売上原価",
        "売上原価_商品売上原価": "商品売上原価",
    },
    "売上総利益": {
        "売上総利益": "売上総利益",
        "売上総利益_完成工事総利益": "完成工事総利益",
    },
    "販売費及び一般管理費": {
        "販売費及び一般管理費": "販売費及び一般管理費",
        "販売費及び一般管理費_広告宣伝費": "広告宣伝費",
        "販売費及び一般管理費_減価償却費": "減価償却費",
        "販売費及び一般管理費_租税公課": "租税公課",
        "販売費及び一般管理費_賃借料": "賃借料",
        "販売費及び一般管理費_研究開発費": "研究開発費",
        "販売費及び一般管理費_人件費": "人件費",
        "販売費及び一般管理費_その他": "その他",
    },
    "営業損益": {
        "営業利益": "営業利益",
    },
    "営業外損益": {
        "営業外収益": "営業外収益",
        "営業外費用": "営業外費用",
    },
    "経常損益以下": {
        "経常利益": "経常利益",
        "特別利益": "特別利益",
        "特別損失": "特別損失",
        "税金等調整前当期純利益": "税金等調整前当期純利益",
        "法人税等": "法人税等",
        "当期純利益": "当期純利益",
    },
}

BS_COLS = {
    "流動資産": {
        "流動資産": "流動資産合計",
        "流動資産_現金及び預金": "現金及び預金",
        "流動資産_受取手形及び売掛金": "受取手形及び売掛金",
        "流動資産_完成工事未収入金": "完成工事未収入金",
        "流動資産_商品及び製品": "商品及び製品",
        "流動資産_販売用不動産": "販売用不動産",
        "流動資産_未成工事支出金": "未成工事支出金",
        "流動資産_原材料及び貯蔵品": "原材料及び貯蔵品",
        "流動資産_短期有価証券": "短期有価証券",
        "流動資産_貸倒引当金": "貸倒引当金",
    },
    "有形固定資産": {
        "有形固定資産": "有形固定資産合計",
        "有形固定資産_建物及び構築物": "建物及び構築物",
        "有形固定資産_機械装置及び車両運搬具": "機械装置及び車両運搬具",
        "有形固定資産_土地": "土地",
        "有形固定資産_リース資産": "リース資産",
        "有形固定資産_建設仮勘定": "建設仮勘定",
        "有形固定資産_工具器具及び備品": "工具器具及び備品",
        "有形固定資産_減価償却累計額": "減価償却累計額",
    },
    "無形固定資産": {
        "無形固定資産": "無形固定資産合計",
        "無形固定資産_ソフトウェア": "ソフトウェア",
        "無形固定資産_のれん": "のれん",
    },
    "投資その他の資産": {
        "投資その他の資産": "投資その他の資産合計",
        "投資その他の資産_投資有価証券": "投資有価証券",
        "投資その他の資産_投資不動産": "投資不動産",
        "投資その他の資産_長期貸付金": "長期貸付金",
        "投資その他の資産_繰延税金資産": "繰延税金資産",
    },
    "固定資産・資産合計": {
        "固定資産": "固定資産合計",
        "総資産": "資産合計",
    },
    "流動負債": {
        "流動負債": "流動負債合計",
        "流動負債_支払手形及び買掛金": "支払手形及び買掛金",
        "流動負債_工事未払金": "工事未払金",
        "流動負債_短期借入金": "短期借入金",
        "流動負債_未払法人税等": "未払法人税等",
        "流動負債_未成工事受入金": "未成工事受入金",
        "流動負債_賞与引当金": "賞与引当金",
        "流動負債_製品保証引当金": "製品保証引当金",
        "流動負債_工事損失引当金": "工事損失引当金",
        "流動負債_1年内返済予定長期借入金": "1年内返済予定長期借入金",
    },
    "固定負債": {
        "固定負債": "固定負債合計",
        "固定負債_社債": "社債",
        "固定負債_長期借入金": "長期借入金",
        "固定負債_退職給付に係る負債": "退職給付に係る負債",
        "固定負債_リース債務": "リース債務",
        "固定負債_資産除去債務": "資産除去債務",
        "固定負債_その他": "その他",
    },
    "負債合計": {
        "負債": "負債合計",
    },
    "純資産": {
        "純資産": "純資産合計",
        "純資産_資本金": "資本金",
        "純資産_資本剰余金": "資本剰余金",
        "純資産_利益剰余金": "利益剰余金",
        "純資産_自己株式": "自己株式",
        "純資産_その他の包括利益累計額": "その他の包括利益累計額",
        "純資産_非支配株主持分": "非支配株主持分",
    },
}

CF_COLS = {
    "営業活動によるキャッシュ・フロー": "営業活動によるキャッシュ・フロー",
    "投資活動によるキャッシュ・フロー": "投資活動によるキャッシュ・フロー",
    "財務活動によるキャッシュ・フロー": "財務活動によるキャッシュ・フロー",
    "現金及び現金同等物期末残高": "現金及び現金同等物期末残高",
}

OTHER_COL = "その他・未分類"


def _parse_number(value: str):
    """数値文字列をint/floatに変換する。変換できなければ元の文字列を返す。"""
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _build_section(row: dict, col_mapping: dict) -> dict:
    """列マッピングに従ってrowから値を取り出し、0でない項目のみ含む辞書を返す。"""
    section = {}
    for csv_col, display_name in col_mapping.items():
        if csv_col in row:
            val = _parse_number(row[csv_col])
            if val != 0:
                section[display_name] = val
    return section


def load_financial_data(csv_path: str, company_code: str = None, year: int = None) -> dict:
    """
    CSVファイルから財務諸表データを読み込み、企業→年度→財務諸表の階層構造で返す。

    Args:
        csv_path: financial_data.csv のパス
        company_code: 企業コード（指定時はその企業のみ抽出）
        year: 年度（指定時はその年度のみ抽出）

    Returns:
        {企業コード: {"企業情報": {...}, "年度データ": {年度: {財務諸表...}}}} の辞書
    """
    results = {}

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            code = row.get("コード", "")
            yr = row.get("YEAR", "")

            # フィルタリング
            if company_code and code != str(company_code):
                continue
            if year and yr != str(year):
                continue

            # 企業エントリの初期化
            if code not in results:
                company_info = {}
                for col in COMPANY_INFO_COLS:
                    if col in row and row[col] and col not in ("YEAR",):
                        company_info[col] = _parse_number(row[col]) if col not in ("コード", "本社所在地", "市場・商品区分", "業種分類") else row[col]
                results[code] = {
                    "企業情報": company_info,
                    "年度データ": {},
                }

            # --- 損益計算書 ---
            pl = {}
            for section_name, col_mapping in PL_COLS.items():
                section_data = _build_section(row, col_mapping)
                if section_data:
                    pl[section_name] = section_data

            # --- 貸借対照表 ---
            bs = {}
            for section_name, col_mapping in BS_COLS.items():
                section_data = _build_section(row, col_mapping)
                if section_data:
                    bs[section_name] = section_data

            # --- キャッシュ・フロー計算書 ---
            cf = _build_section(row, CF_COLS)

            # --- その他 ---
            other_val = _parse_number(row.get(OTHER_COL, "0"))

            year_entry = {
                "損益計算書": pl,
                "貸借対照表": bs,
                "キャッシュ・フロー計算書": cf,
            }
            if other_val != 0:
                year_entry["その他"] = other_val

            results[code]["年度データ"][yr] = year_entry

    return results


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_csv = os.path.join(base_dir, "data", "input", "financial-statements", "financial_data.csv")
    default_output = os.path.join(base_dir, "data", "medium-output", "report-extraction", "financial_statements.json")

    parser = argparse.ArgumentParser(description="財務諸表CSVをJSON形式で出力する")
    parser.add_argument("-i", "--input", default=default_csv, help="入力CSVファイルパス")
    parser.add_argument("-c", "--code", default=None, help="企業コード（指定しない場合は全企業）")
    parser.add_argument("-y", "--year", type=int, default=None, help="年度（指定しない場合は全年度）")
    parser.add_argument("-o", "--output", default=default_output, help="出力JSONファイルパス")
    args = parser.parse_args()

    data = load_financial_data(args.input, company_code=args.code, year=args.year)

    json_str = json.dumps(data, indent=2, ensure_ascii=False)

    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"出力完了: {args.output} ({len(data)}件)")
    else:
        print(json_str)


if __name__ == "__main__":
    main()
