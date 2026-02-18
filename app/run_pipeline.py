"""
統合パイプライン: PDF → DOCX の全ステージを一括実行する。

Usage:
    uv run app/run_pipeline.py -i data/input/pdfs/有価証券報告書（12044）.pdf

    # 企業コード明示
    uv run app/run_pipeline.py -i data/input/pdfs/有価証券報告書（12044）.pdf -c 12044

    # 確認なしで全ステージ実行
    uv run app/run_pipeline.py -i ... --yes

    # Stage 4 から再開（前回の run_id を指定）
    uv run app/run_pipeline.py -i ... --run-id 12044_20260211_223000 --start-stage 4

ステージ:
    1. Report Extraction   — PDF → タグ付きJSON + 財務指標
    2. Issue Extraction     — スコアリング + 地域特徴抽出
    3. Solution Selection   — 施策選定
    4. Roadmaps             — 効果試算・ロードマップ・リスク
    5. Executive Summary    — エグゼクティブサマリー
    6. Final Assembly       — 最終JSON組み立て
    7. JSON → DOCX          — Word文書生成
"""

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _extract_code(filename: str) -> str:
    match = re.search(r"(\d+)", filename)
    return match.group(1) if match else ""


def _timestamp() -> str:
    """ファイル名用のタイムスタンプ (YYYYMMDD_HHMMSS)。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def confirm(label: str, auto_yes: bool) -> bool:
    """次のステージに進むか確認する。auto_yes=True なら常にTrue。"""
    if auto_yes:
        return True
    answer = input(f"\n次へ進みますか？ [{label}] (Y/n): ").strip().lower()
    if answer in ("", "y", "yes"):
        return True
    print("パイプラインを中断しました。")
    return False


def run(cmd: list[str], label: str):
    """サブプロセスを実行し、失敗時はパイプラインを停止する。"""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  cmd: {' '.join(cmd)}\n")

    start = time.time()
    result = subprocess.run(cmd, cwd=BASE_DIR)
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\n[ERROR] {label} が失敗しました (exit code: {result.returncode})")
        sys.exit(1)

    print(f"\n  -> {label} 完了 ({elapsed:.1f}s)")


def main():
    parser = argparse.ArgumentParser(description="統合パイプライン: PDF → DOCX")
    parser.add_argument("-i", "--input", required=True, help="入力PDFファイルパス")
    parser.add_argument("-c", "--code", default=None, help="企業コード（未指定時はファイル名から自動抽出）")
    parser.add_argument("--csv", default=None, help="財務諸表CSVファイルパス")
    parser.add_argument("-m", "--model", default="gpt-5-mini", help="使用するモデルID")
    parser.add_argument("--no-fewshot", action="store_true", help="few-shot例を使用しない")
    parser.add_argument("-y", "--yes", action="store_true", help="確認なしで全ステージ実行")
    parser.add_argument("--start-stage", type=int, default=1, choices=range(1, 8),
                        help="開始ステージ番号（1-7, デフォルト: 1）")
    parser.add_argument("--run-id", default=None,
                        help="既存の実行ID（途中再開時に指定。例: 12044_20260211_223000）")
    args = parser.parse_args()

    pdf_path = args.input
    code = args.code or _extract_code(os.path.basename(pdf_path))
    if not code:
        print("[ERROR] 企業コードを特定できません。--code で指定してください。")
        sys.exit(1)

    start_stage = args.start_stage

    # 途中再開時: 既存の run_id を使う / 新規時: タイムスタンプで生成
    if args.run_id:
        run_id = args.run_id
        print(f"[再開モード] Stage {start_stage} から再開します")
    else:
        ts = _timestamp()
        run_id = f"{code}_{ts}"

    print(f"企業コード: {code}")
    print(f"実行ID:     {run_id}")
    print(f"入力PDF:    {pdf_path}")
    print(f"モデル:     {args.model}")
    if start_stage > 1:
        print(f"開始ステージ: {start_stage}")

    uv = ["uv", "run"]

    # --- パス定義（企業コード + タイムスタンプで一意に） ---
    tagged_path = os.path.join(
        "data", "medium-output", "report-extraction",
        "report-tagged-per-company", f"report_tagged_{run_id}.json",
    )
    scores_path = os.path.join(
        "data", "medium-output", "issue-extraction",
        "report-scores-per-company", f"report_scores_{run_id}.json",
    )
    features_path = os.path.join(
        "data", "medium-output", "issue-extraction",
        "local-features-per-company", f"local_features_{run_id}.json",
    )
    selection_path = os.path.join(
        "data", "medium-output", "solution-selection",
        "solution-selection-per-company", f"solution_selection_{run_id}.json",
    )
    roadmap_path = os.path.join(
        "data", "medium-output", "solution-selection",
        "roadmaps-per-company", f"roadmap_{run_id}.json",
    )
    exec_summary_path = os.path.join(
        "data", "final-output", "executive-summary-per-company",
        f"executive_summary_{run_id}.json",
    )
    final_report_path = os.path.join(
        "data", "final-output", "final-report-per-company",
        f"final_report_{run_id}.json",
    )
    docx_path = os.path.join(
        "data", "final-output", "docx-per-company",
        f"report_{run_id}.docx",
    )

    pipeline_start = time.time()

    # ========================================
    # Stage 1: Report Extraction
    # ========================================
    if start_stage <= 1:
        cmd = [*uv, "app/report-extraction/main.py", "-i", pdf_path, "-c", code, "-o", tagged_path]
        if args.csv:
            cmd += ["--csv", args.csv]
        run(cmd, "Stage 1: Report Extraction")
        print(f"  出力: {tagged_path}")

        if not confirm("Stage 2: Issue Extraction", args.yes):
            return
    else:
        print(f"\n  [skip] Stage 1 (既存ファイル: {tagged_path})")

    # ========================================
    # Stage 2: Issue Extraction
    # ========================================
    if start_stage <= 2:
        cmd = [*uv, "app/issue-extraction/main.py", "-i", tagged_path, "-m", args.model,
               "--scores-output", scores_path, "--features-output", features_path]
        if args.no_fewshot:
            cmd.append("--no-fewshot")
        run(cmd, "Stage 2: Issue Extraction")
        print(f"  出力: {scores_path}")
        print(f"  出力: {features_path}")

        if not confirm("Stage 3: Solution Selection", args.yes):
            return
    else:
        print(f"\n  [skip] Stage 2 (既存ファイル: {scores_path}, {features_path})")

    # ========================================
    # Stage 3: Solution Selection
    # ========================================
    if start_stage <= 3:
        run(
            [*uv, "app/solution-selection/solution_selection.py",
             "-s", scores_path, "-f", features_path,
             "-o", selection_path, "-m", args.model],
            "Stage 3: Solution Selection",
        )
        print(f"  出力: {selection_path}")

        if not confirm("Stage 4: Roadmaps", args.yes):
            return
    else:
        print(f"\n  [skip] Stage 3 (既存ファイル: {selection_path})")

    # ========================================
    # Stage 4: Roadmaps
    # ========================================
    if start_stage <= 4:
        run(
            [*uv, "app/solution-selection/roadmaps.py",
             "-s", selection_path, "-o", roadmap_path, "-m", args.model],
            "Stage 4: Roadmaps",
        )
        print(f"  出力: {roadmap_path}")

        if not confirm("Stage 5: Executive Summary", args.yes):
            return
    else:
        print(f"\n  [skip] Stage 4 (既存ファイル: {roadmap_path})")

    # ========================================
    # Stage 5: Executive Summary
    # ========================================
    if start_stage <= 5:
        run(
            [*uv, "app/solution-selection/executive_summary.py",
             "-c", code,
             "--local-features", features_path,
             "--report-scores", scores_path,
             "--selection", selection_path,
             "--roadmap", roadmap_path,
             "-o", exec_summary_path, "-m", args.model],
            "Stage 5: Executive Summary",
        )
        print(f"  出力: {exec_summary_path}")

        if not confirm("Stage 6: Final Assembly", args.yes):
            return
    else:
        print(f"\n  [skip] Stage 5 (既存ファイル: {exec_summary_path})")

    # ========================================
    # Stage 6: Final Assembly
    # ========================================
    if start_stage <= 6:
        run(
            [*uv, "app/final-assembly/main.py",
             "--code", code,
             "--executive-summary", exec_summary_path,
             "--local-features", features_path,
             "--report-scores", scores_path,
             "--solution-selection", selection_path,
             "--roadmap", roadmap_path,
             "-o", final_report_path],
            "Stage 6: Final Assembly",
        )
        print(f"  出力: {final_report_path}")

        if not confirm("Stage 7: JSON → DOCX", args.yes):
            return
    else:
        print(f"\n  [skip] Stage 6 (既存ファイル: {final_report_path})")

    # ========================================
    # Stage 7: JSON → DOCX
    # ========================================
    run(
        [*uv, "app/json-to-docx/json-to-docx.py",
         "-i", final_report_path, "-o", docx_path],
        "Stage 7: JSON → DOCX",
    )
    print(f"  出力: {docx_path}")

    total = time.time() - pipeline_start
    print(f"\n{'='*60}")
    print(f"  全パイプライン完了 ({total:.1f}s)")
    print(f"{'='*60}")
    print(f"  実行ID:   {run_id}")
    print(f"  最終JSON: {final_report_path}")
    print(f"  DOCX:     {docx_path}")


if __name__ == "__main__":
    main()
