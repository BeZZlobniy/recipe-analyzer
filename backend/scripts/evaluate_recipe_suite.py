from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.db import SessionLocal, bootstrap_database
from app.models.recipe_analysis import RecipeAnalysis
from app.models.user import User
from app.modules.evaluation.recipe_suite import EvalInput, evaluate_suite, load_expectations


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate saved recipe-suite analyses against service labels.")
    parser.add_argument("--report", type=Path, default=Path("reports/recipe_suite_latest.json"))
    parser.add_argument("--expectations", type=Path, default=Path("app/data/eval/recipe_expectations.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/recipe_suite_eval_latest.json"))
    parser.add_argument("--db-only", action="store_true", help="Ignore suite report and evaluate all current demo-user analyses from DB.")
    parser.add_argument("--worst", type=int, default=12, help="How many lowest-scoring rows to print.")
    args = parser.parse_args()

    bootstrap_database()
    expectations_path = args.expectations if args.expectations.is_absolute() else BACKEND_DIR / args.expectations
    expectations = load_expectations(expectations_path)
    inputs = load_eval_inputs(args.report, args.db_only)
    evaluation = evaluate_suite(inputs, expectations)

    output_path = args.output if args.output.is_absolute() else BACKEND_DIR / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")

    print_summary(evaluation, output_path, args.worst)


def load_eval_inputs(report_path: Path, db_only: bool) -> list[EvalInput]:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == settings.demo_username).one()
        if db_only:
            analyses = (
                db.query(RecipeAnalysis)
                .filter(RecipeAnalysis.user_id == user.id)
                .order_by(RecipeAnalysis.id)
                .all()
            )
            return [
                EvalInput(recipe_index=None, profile_name=analysis.profile.name, result=analysis.analysis_result_json or {})
                for analysis in analyses
            ]

        report = _read_report(report_path)
        inputs: list[EvalInput] = []
        for row in report.get("rows") or []:
            if not isinstance(row, dict):
                continue
            analysis = db.get(RecipeAnalysis, row.get("analysis_id")) if row.get("analysis_id") else None
            result = analysis.analysis_result_json if analysis is not None else row
            profile_name = analysis.profile.name if analysis is not None else str(row.get("profile") or "")
            inputs.append(EvalInput(recipe_index=_as_int(row.get("index")), profile_name=profile_name, result=result or {}))
        return inputs


def print_summary(evaluation: dict[str, Any], output_path: Path, worst_count: int) -> None:
    summary = evaluation.get("summary") or {}
    print(f"Evaluated analyses: {evaluation.get('analysis_count', 0)}")
    print(f"Average overall score: {summary.get('average_overall_score')}")
    print(f"Min overall score: {summary.get('min_overall_score')}")
    print(f"Rows below 80: {summary.get('rows_below_80')}")
    print("Category averages:")
    for key, value in (summary.get("category_averages") or {}).items():
        print(f"  {key}: {value}")
    print("Issue counts:")
    for key, value in sorted((summary.get("issue_counts") or {}).items()):
        print(f"  {key}: {value}")

    rows = sorted(evaluation.get("rows") or [], key=lambda item: float(item.get("overall_score") or 0))
    if rows:
        print("Worst rows:")
        for row in rows[: max(worst_count, 0)]:
            issues = compact_row_issues(row)
            print(
                f"  #{row.get('recipe_index')} | {row.get('profile')} | "
                f"{row.get('overall_score')} | {row.get('title')} | {issues}"
            )
    print(f"Eval report saved: {output_path}")


def compact_row_issues(row: dict[str, Any]) -> str:
    issue_parts: list[str] = []
    if row.get("parser", {}).get("missing_required_ingredients"):
        issue_parts.append("missing ingredients")
    if row.get("amounts", {}).get("failed_amounts"):
        issue_parts.append("amounts")
    if row.get("matching", {}).get("suspicious_matches"):
        issue_parts.append("USDA match")
    if row.get("matching", {}).get("unresolved_ingredients"):
        issue_parts.append("unresolved")
    if row.get("rag", {}).get("missing_sources"):
        issue_parts.append("RAG sources")
    if row.get("profile_eval", {}).get("missing_expected_conflicts"):
        issue_parts.append("missed conflict")
    if row.get("profile_eval", {}).get("unexpected_conflicts"):
        issue_parts.append("false conflict")
    if row.get("text_grounding", {}).get("false_claims"):
        issue_parts.append("false claim")
    if row.get("text_grounding", {}).get("profile_noise_phrases"):
        issue_parts.append("profile noise")
    return ", ".join(issue_parts) or "no major flags"


def _read_report(report_path: Path) -> dict[str, Any]:
    path = report_path if report_path.is_absolute() else BACKEND_DIR / report_path
    if not path.exists():
        raise SystemExit(f"Suite report not found: {path}. Use --db-only or run run_recipe_suite.py first.")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
