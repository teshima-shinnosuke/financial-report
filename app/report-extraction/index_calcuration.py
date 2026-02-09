import json
import os
import argparse


def _safe_div(a, b):
    """None や 0 除算を安全に処理する割り算。"""
    if a is None or b is None or b == 0:
        return None
    return a / b


def _safe_sub(a, b):
    """None を考慮した引き算。"""
    if a is None or b is None:
        return None
    return a - b


def _safe_add(*values):
    """None を考慮した足し算。全て None なら None を返す。"""
    nums = [v for v in values if v is not None]
    return sum(nums) if nums else None


def _avg(val_curr, val_prev):
    """期首・期末平均。前期データがなければ当期のみ返す。"""
    if val_curr is None:
        return val_prev
    if val_prev is None:
        return val_curr
    return (val_curr + val_prev) / 2


def _pct(value):
    """比率を % 表記の丸め値に変換。"""
    if value is None:
        return None
    return round(value * 100, 2)


def _round_val(value, ndigits=2):
    if value is None:
        return None
    return round(value, ndigits)


# ── ヘルパー: 財務データから値を取り出す ──

def _get_pl(year_data: dict) -> dict:
    return year_data.get("損益計算書", {})


def _get_bs(year_data: dict) -> dict:
    return year_data.get("貸借対照表", {})


def _get_cf(year_data: dict) -> dict:
    return year_data.get("キャッシュ・フロー計算書", {})


def _売上高(pl):
    return (pl.get("売上高") or {}).get("合計")


def _売上原価(pl):
    return (pl.get("売上原価") or {}).get("合計")


def _売上総利益(pl):
    return (pl.get("売上総利益") or {}).get("合計")


def _販管費(pl):
    return (pl.get("販売費及び一般管理費") or {}).get("合計")


def _販管費内訳(pl, key):
    return ((pl.get("販売費及び一般管理費") or {}).get("内訳") or {}).get(key)


def _総資産(bs):
    return (bs.get("資産") or {}).get("総資産")


def _流動資産(bs):
    return ((bs.get("資産") or {}).get("流動資産") or {}).get("合計")


def _流動資産内訳(bs, key):
    return (((bs.get("資産") or {}).get("流動資産") or {}).get("内訳") or {}).get(key)


def _流動負債(bs):
    liab = (bs.get("負債・純資産") or {}).get("負債") or {}
    return ((liab.get("内訳") or {}).get("流動負債") or {}).get("合計")


def _流動負債内訳(bs, key):
    liab = (bs.get("負債・純資産") or {}).get("負債") or {}
    return (((liab.get("内訳") or {}).get("流動負債") or {}).get("内訳") or {}).get(key)


def _固定負債内訳(bs, key):
    liab = (bs.get("負債・純資産") or {}).get("負債") or {}
    return (((liab.get("内訳") or {}).get("固定負債") or {}).get("内訳") or {}).get(key)


def _純資産(bs):
    return ((bs.get("負債・純資産") or {}).get("純資産") or {}).get("合計")


# ── 指標計算 ──

def calc_profitability(pl):
    """1. 収益性指標"""
    revenue = _売上高(pl)
    cogs = _売上原価(pl)
    gross = _売上総利益(pl)
    sga = _販管費(pl)
    op_income = pl.get("営業利益")
    ord_income = pl.get("経常利益")
    net_income = pl.get("当期純利益")
    dep = _販管費内訳(pl, "販売費及び一般管理費_減価償却費")

    return {
        "売上総利益率": _pct(_safe_div(gross, revenue)),
        "原価率": _pct(_safe_div(cogs, revenue)),
        "販管費率": _pct(_safe_div(sga, revenue)),
        "営業利益率": _pct(_safe_div(op_income, revenue)),
        "経常利益率": _pct(_safe_div(ord_income, revenue)),
        "純利益率": _pct(_safe_div(net_income, revenue)),
        "EBITDA": _safe_add(op_income, dep),
    }


def calc_growth(pl_curr, pl_prev):
    """2. 成長性指標"""
    if pl_prev is None:
        return None

    pairs = [
        ("売上高成長率", _売上高(pl_curr), _売上高(pl_prev)),
        ("営業利益成長率", pl_curr.get("営業利益"), pl_prev.get("営業利益")),
        ("経常利益成長率", pl_curr.get("経常利益"), pl_prev.get("経常利益")),
        ("当期純利益成長率", pl_curr.get("当期純利益"), pl_prev.get("当期純利益")),
    ]
    result = {}
    for name, curr, prev in pairs:
        result[name] = _pct(_safe_div(_safe_sub(curr, prev), abs(prev) if prev else None))
    return result


def calc_cost_structure(pl):
    """3. コスト構造・固定費分析"""
    revenue = _売上高(pl)
    gross = _売上総利益(pl)
    personnel = _販管費内訳(pl, "販売費及び一般管理費_人件費")
    dep = _販管費内訳(pl, "販売費及び一般管理費_減価償却費")

    return {
        "人件費率": _pct(_safe_div(personnel, revenue)),
        "減価償却費率": _pct(_safe_div(dep, revenue)),
        "付加価値額（売上総利益−人件費）": _safe_sub(gross, personnel),
    }


def calc_efficiency(pl, bs_curr, bs_prev):
    """4. 効率性指標"""
    revenue = _売上高(pl)
    net_income = pl.get("当期純利益")
    avg_ta = _avg(_総資産(bs_curr), _総資産(bs_prev) if bs_prev else None)
    avg_eq = _avg(_純資産(bs_curr), _純資産(bs_prev) if bs_prev else None)

    return {
        "総資産回転率": _round_val(_safe_div(revenue, avg_ta)),
        "ROA": _pct(_safe_div(net_income, avg_ta)),
        "ROE": _pct(_safe_div(net_income, avg_eq)),
    }


def calc_safety(bs):
    """5. 安全性・財務健全性"""
    ca = _流動資産(bs)
    cl = _流動負債(bs)
    ta = _総資産(bs)
    eq = _純資産(bs)

    cash = _流動資産内訳(bs, "流動資産_現金及び預金")
    ar = _流動資産内訳(bs, "流動資産_受取手形及び売掛金")
    construction_ar = _流動資産内訳(bs, "流動資産_完成工事未収入金")
    quick_assets = _safe_add(cash, ar, construction_ar)

    short_debt = _流動負債内訳(bs, "流動負債_短期借入金")
    short_lt_debt = _流動負債内訳(bs, "流動負債_1年内返済予定長期借入金")
    long_debt = _固定負債内訳(bs, "固定負債_長期借入金")
    interest_bearing = _safe_add(short_debt, short_lt_debt, long_debt)

    return {
        "流動比率": _pct(_safe_div(ca, cl)),
        "当座比率": _pct(_safe_div(quick_assets, cl)),
        "自己資本比率": _pct(_safe_div(eq, ta)),
        "D/Eレシオ": _round_val(_safe_div(interest_bearing, eq)),
    }


def calc_cashflow(pl, cf, cf_prev):
    """6. キャッシュフロー関連指標"""
    revenue = _売上高(pl)
    op_income = pl.get("営業利益")
    dep = _販管費内訳(pl, "販売費及び一般管理費_減価償却費")
    ebitda = _safe_add(op_income, dep)

    op_cf = cf.get("営業活動によるキャッシュ・フロー")
    inv_cf = cf.get("投資活動によるキャッシュ・フロー")
    end_cash = cf.get("現金及び現金同等物期末残高")
    begin_cash = cf_prev.get("現金及び現金同等物期末残高") if cf_prev else None

    return {
        "営業CFマージン": _pct(_safe_div(op_cf, revenue)),
        "フリーキャッシュフロー": _safe_add(op_cf, inv_cf),
        "営業CF÷EBITDA": _round_val(_safe_div(op_cf, ebitda)),
        "現金増減額": _safe_sub(end_cash, begin_cash),
    }


def calc_construction(pl, bs_curr, bs_prev):
    """7. 建設業・工事業向け特有指標"""
    # 工事運転資本
    constr_ar = _流動資産内訳(bs_curr, "流動資産_完成工事未収入金")
    wip = _流動資産内訳(bs_curr, "流動資産_未成工事支出金")
    constr_ap = _流動負債内訳(bs_curr, "流動負債_工事未払金")
    adv_received = _流動負債内訳(bs_curr, "流動負債_未成工事受入金")
    construction_wc = _safe_sub(_safe_add(constr_ar, wip), _safe_add(constr_ap, adv_received))

    # ネット運転資本（簡易）
    ca = _流動資産(bs_curr)
    cash = _流動資産内訳(bs_curr, "流動資産_現金及び預金")
    cl = _流動負債(bs_curr)
    short_debt = _流動負債内訳(bs_curr, "流動負債_短期借入金")
    net_wc = _safe_sub(
        _safe_sub(ca, cash),
        _safe_sub(cl, short_debt),
    )

    # 売上債権回転期間
    revenue = _売上高(pl)
    ar_curr = _safe_add(
        _流動資産内訳(bs_curr, "流動資産_受取手形及び売掛金"),
        _流動資産内訳(bs_curr, "流動資産_完成工事未収入金"),
    )
    ar_prev = None
    if bs_prev:
        ar_prev = _safe_add(
            _流動資産内訳(bs_prev, "流動資産_受取手形及び売掛金"),
            _流動資産内訳(bs_prev, "流動資産_完成工事未収入金"),
        )
    avg_ar = _avg(ar_curr, ar_prev)
    ar_days = _round_val(_safe_div(avg_ar, revenue) * 365) if _safe_div(avg_ar, revenue) is not None else None

    # 仕入債務回転期間
    cogs = _売上原価(pl)
    ap_curr = _流動負債内訳(bs_curr, "流動負債_工事未払金")
    ap_prev = _流動負債内訳(bs_prev, "流動負債_工事未払金") if bs_prev else None
    avg_ap = _avg(ap_curr, ap_prev)
    ap_days = _round_val(_safe_div(avg_ap, cogs) * 365) if _safe_div(avg_ap, cogs) is not None else None

    return {
        "工事運転資本": construction_wc,
        "ネット運転資本（簡易）": net_wc,
        "売上債権回転期間（日）": ar_days,
        "仕入債務回転期間（日）": ap_days,
    }


# ── メイン処理 ──

def calculate_indices(company_data: dict) -> dict:
    """1社分の全指標を年度ごとに計算する。"""
    fin_years = company_data.get("財務データ", [])
    results = []

    for i, year_data in enumerate(fin_years):
        year = year_data.get("YEAR")
        pl = _get_pl(year_data)
        bs = _get_bs(year_data)
        cf = _get_cf(year_data)

        prev_data = fin_years[i - 1] if i > 0 else None
        pl_prev = _get_pl(prev_data) if prev_data else None
        bs_prev = _get_bs(prev_data) if prev_data else None
        cf_prev = _get_cf(prev_data) if prev_data else None

        year_result = {
            "YEAR": year,
            "収益性指標": calc_profitability(pl),
            "成長性指標": calc_growth(pl, pl_prev),
            "コスト構造・固定費分析": calc_cost_structure(pl),
            "効率性指標": calc_efficiency(pl, bs, bs_prev),
            "安全性・財務健全性": calc_safety(bs),
            "キャッシュフロー関連指標": calc_cashflow(pl, cf, cf_prev),
            "建設業特有指標": calc_construction(pl, bs, bs_prev),
        }
        results.append(year_result)

    return {
        "企業情報": company_data.get("企業情報", {}),
        "指標": results,
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_input = os.path.join(base_dir, "data", "medium-output", "report-extraction", "financial_statements.json")
    default_output = os.path.join(base_dir, "data", "medium-output", "report-extraction", "financial_indices.json")

    parser = argparse.ArgumentParser(description="財務諸表から各種財務指標を算出する")
    parser.add_argument("-i", "--input", default=default_input, help="入力 financial_statements.json パス")
    parser.add_argument("-o", "--output", default=default_output, help="出力 financial_indices.json パス")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        fs_map = json.load(f)

    all_results = {}
    for code, company_data in fs_map.items():
        name = company_data.get("企業情報", {}).get("コード", code)
        print(f"  {name}: 指標計算中...")
        all_results[code] = calculate_indices(company_data)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n指標計算完了: {len(all_results)} 社 -> {args.output}")


if __name__ == "__main__":
    main()
