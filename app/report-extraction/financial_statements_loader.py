import csv
import json
import os
import argparse


def _parse_number(value: str):
    """数値文字列をint/floatに変換する。変換できなければNoneを返す。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return None


def _get(row: dict, col: str):
    """CSVの行から値を取得する。存在しない or 空 or 0 なら None。"""
    val = _parse_number(row.get(col, ""))
    if val == 0:
        return None
    return val


def _build_subtotal(row: dict, total_col: str, detail_cols: list[str]) -> dict:
    """合計 + 内訳の構造を構築する。"""
    return {
        "合計": _get(row, total_col),
        "内訳": {col: _get(row, col) for col in detail_cols},
    }


def _build_pl(row: dict) -> dict:
    """損益計算書を構築する。"""
    return {
        "売上高": _build_subtotal(row, "売上高", [
            "売上高_完成工事高",
            "売上高_商品売上高",
            "売上高_不動産事業売上高",
        ]),
        "売上原価": _build_subtotal(row, "売上原価", [
            "売上原価_完成工事原価",
            "売上原価_商品売上原価",
            "売上原価_不動産事業売上原価",
        ]),
        "売上総利益": _build_subtotal(row, "売上総利益", [
            "売上総利益_完成工事総利益",
        ]),
        "販売費及び一般管理費": _build_subtotal(row, "販売費及び一般管理費", [
            "販売費及び一般管理費_人件費",
            "販売費及び一般管理費_広告宣伝費",
            "販売費及び一般管理費_研究開発費",
            "販売費及び一般管理費_減価償却費",
            "販売費及び一般管理費_賃借料",
            "販売費及び一般管理費_租税公課",
            "販売費及び一般管理費_その他",
        ]),
        "営業利益": _get(row, "営業利益"),
        "営業外収益": _get(row, "営業外収益"),
        "営業外費用": _get(row, "営業外費用"),
        "経常利益": _get(row, "経常利益"),
        "特別利益": _get(row, "特別利益"),
        "特別損失": _get(row, "特別損失"),
        "税金等調整前当期純利益": _get(row, "税金等調整前当期純利益"),
        "法人税等": _get(row, "法人税等"),
        "当期純利益": _get(row, "当期純利益"),
        "その他・未分類": _get(row, "その他・未分類"),
    }


def _build_bs(row: dict) -> dict:
    """貸借対照表を構築する。"""
    return {
        "資産": {
            "流動資産": _build_subtotal(row, "流動資産", [
                "流動資産_現金及び預金",
                "流動資産_短期有価証券",
                "流動資産_受取手形及び売掛金",
                "流動資産_完成工事未収入金",
                "流動資産_未成工事支出金",
                "流動資産_商品及び製品",
                "流動資産_原材料及び貯蔵品",
                "流動資産_販売用不動産",
                "流動資産_貸倒引当金",
            ]),
            "固定資産": {
                "合計": _get(row, "固定資産"),
                "内訳": {
                    "有形固定資産": _build_subtotal(row, "有形固定資産", [
                        "有形固定資産_建物及び構築物",
                        "有形固定資産_機械装置及び車両運搬具",
                        "有形固定資産_工具器具及び備品",
                        "有形固定資産_土地",
                        "有形固定資産_リース資産",
                        "有形固定資産_建設仮勘定",
                        "有形固定資産_減価償却累計額",
                    ]),
                    "無形固定資産": _build_subtotal(row, "無形固定資産", [
                        "無形固定資産_のれん",
                        "無形固定資産_ソフトウェア",
                    ]),
                    "投資その他の資産": _build_subtotal(row, "投資その他の資産", [
                        "投資その他の資産_投資有価証券",
                        "投資その他の資産_投資不動産",
                        "投資その他の資産_長期貸付金",
                        "投資その他の資産_繰延税金資産",
                    ]),
                },
            },
            "総資産": _get(row, "総資産"),
        },
        "負債・純資産": {
            "負債": {
                "合計": _get(row, "負債"),
                "内訳": {
                    "流動負債": _build_subtotal(row, "流動負債", [
                        "流動負債_短期借入金",
                        "流動負債_1年内返済予定長期借入金",
                        "流動負債_支払手形及び買掛金",
                        "流動負債_工事未払金",
                        "流動負債_未成工事受入金",
                        "流動負債_未払法人税等",
                        "流動負債_賞与引当金",
                        "流動負債_工事損失引当金",
                        "流動負債_製品保証引当金",
                    ]),
                    "固定負債": _build_subtotal(row, "固定負債", [
                        "固定負債_社債",
                        "固定負債_長期借入金",
                        "固定負債_リース債務",
                        "固定負債_退職給付に係る負債",
                        "固定負債_資産除去債務",
                        "固定負債_その他",
                    ]),
                },
            },
            "純資産": _build_subtotal(row, "純資産", [
                "純資産_資本金",
                "純資産_資本剰余金",
                "純資産_利益剰余金",
                "純資産_自己株式",
                "純資産_その他の包括利益累計額",
                "純資産_非支配株主持分",
            ]),
        },
    }


def _build_cf(row: dict) -> dict:
    """キャッシュ・フロー計算書を構築する。"""
    return {
        "営業活動によるキャッシュ・フロー": _get(row, "営業活動によるキャッシュ・フロー"),
        "投資活動によるキャッシュ・フロー": _get(row, "投資活動によるキャッシュ・フロー"),
        "財務活動によるキャッシュ・フロー": _get(row, "財務活動によるキャッシュ・フロー"),
        "現金及び現金同等物期末残高": _get(row, "現金及び現金同等物期末残高"),
    }


def load_financial_data(csv_path: str, company_code: str = None, year: int = None) -> dict:
    """
    CSVファイルから財務諸表データを読み込み、企業ごとに構造化して返す。

    Returns:
        {企業コード: {"企業情報": {...}, "財務データ": [{YEAR, 損益計算書, 貸借対照表, CF}]}}
    """
    results = {}

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            code = row.get("コード", "")
            yr = row.get("YEAR", "")

            if company_code and code != str(company_code):
                continue
            if year and yr != str(year):
                continue

            if code not in results:
                results[code] = {
                    "企業情報": {
                        "コード": code or None,
                        "本社所在地": row.get("本社所在地") or None,
                        "市場・商品区分": row.get("市場・商品区分") or None,
                        "従業員数（連結）": _parse_number(row.get("従業員数（連結）", "")),
                        "資本金（億円）": _parse_number(row.get("資本金（億円）", "")),
                        "業種分類": row.get("業種分類") or None,
                    },
                    "財務データ": [],
                }

            year_entry = {
                "YEAR": _parse_number(yr),
                "損益計算書": _build_pl(row),
                "貸借対照表": _build_bs(row),
                "キャッシュ・フロー計算書": _build_cf(row),
            }

            results[code]["財務データ"].append(year_entry)

    return results


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_csv = os.path.join(base_dir, "data", "input", "financial-statements", "financial_data.csv")

    parser = argparse.ArgumentParser(description="1企業の財務諸表CSVをJSON形式で出力する")
    parser.add_argument("-i", "--input", default=default_csv, help="入力CSVファイルパス")
    parser.add_argument("-c", "--code", required=True, help="企業コード")
    parser.add_argument("-o", "--output", default=None, help="出力JSONファイルパス（未指定時は自動生成）")
    args = parser.parse_args()

    data = load_financial_data(args.input, company_code=args.code)

    if not data:
        print(f"企業コード '{args.code}' のデータが見つかりません。")
        return

    output_dir = os.path.join(base_dir, "data", "medium-output", "report-extraction", "financial-statements-per-company")
    output_path = args.output or os.path.join(output_dir, f"financial_statements_{args.code}.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"出力完了: {output_path}")


if __name__ == "__main__":
    main()
