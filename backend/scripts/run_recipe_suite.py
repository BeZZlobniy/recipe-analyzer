from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.db import SessionLocal, bootstrap_database
from app.models.profile import UserProfile
from app.models.recipe_analysis import RecipeAnalysis
from app.models.user import User
from app.modules.analysis.service import analysis_service


PROFILE_PLAN = [
    ("Анна, вегетарианка без лактозы", 650.0),
    ("Сергей, набор мышечной массы", 900.0),
    ("Мария, контроль сахара", 500.0),
    ("Ирина, низкая соль", 600.0),
    ("Никита, веган без глютена", 650.0),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local RAG analysis suite on numbered recipe files.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--indexes", type=str, default="", help="Comma-separated recipe indexes to run, e.g. 8,18,19.")
    parser.add_argument("--recipe-dir", type=Path, default=Path("recipes"))
    parser.add_argument("--matrix", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--save-db", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--clear-db", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("reports/recipe_suite_latest.json"))
    args = parser.parse_args()

    bootstrap_database()
    recipe_dir = args.recipe_dir if args.recipe_dir.is_absolute() else settings.data_dir / args.recipe_dir
    recipe_indexes = parse_indexes(args.indexes) if args.indexes else list(range(1, args.limit + 1))
    recipe_paths = [(index, recipe_dir / f"{index}.txt") for index in recipe_indexes]
    missing = [path for _, path in recipe_paths if not path.exists()]
    if missing:
        raise SystemExit(f"Missing recipe files: {', '.join(str(path) for path in missing)}")

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == settings.demo_username).one()
        if args.clear_db:
            deleted = db.query(RecipeAnalysis).filter(RecipeAnalysis.user_id == user.id).delete(synchronize_session=False)
            db.commit()
            print(f"Deleted previous analyses: {deleted}", flush=True)
        profiles = {
            profile.name: profile
            for profile in db.query(UserProfile).filter(UserProfile.user_id == user.id).all()
        }
        rows: list[dict[str, Any]] = []
        for index, recipe_path in recipe_paths:
            recipe_text = recipe_path.read_text(encoding="utf-8-sig")
            plans = PROFILE_PLAN if args.matrix else [PROFILE_PLAN[(index - 1) % len(PROFILE_PLAN)]]
            for profile_name, target_calories in plans:
                profile = profiles.get(profile_name)
                if profile is None:
                    raise SystemExit(f"Profile not found: {profile_name}")

                profile_data = profile_to_dict(profile)
                result = analysis_service.analyze_recipe(
                    db,
                    recipe_text,
                    profile_data,
                    target_recipe_calories=target_calories,
                )
                analysis_id = None
                if args.save_db:
                    analysis = RecipeAnalysis(
                        user_id=user.id,
                        profile_id=profile.id,
                        title=result["title"],
                        recipe_text=recipe_text,
                        structured_recipe_json=result["structured_recipe"],
                        analysis_result_json=result,
                        summary=result["summary"],
                        diet_compatibility=result["compatibility"]["diet"],
                        restriction_compatibility=result["compatibility"]["restriction"],
                        goal_compatibility=result["compatibility"]["goal"],
                    )
                    db.add(analysis)
                    db.commit()
                    db.refresh(analysis)
                    analysis_id = analysis.id
                rows.append(summarize_result(index, recipe_path, profile_name, target_calories, result))
                rows[-1]["analysis_id"] = analysis_id
                print(format_console_row(rows[-1]), flush=True)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "recipe_count": len(recipe_paths),
        "profile_count": len(PROFILE_PLAN) if args.matrix else 1,
        "analysis_count": len(rows),
        "summary": summarize_suite(rows),
        "rows": rows,
    }
    output_path = args.output if args.output.is_absolute() else Path(__file__).resolve().parents[1] / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report saved: {output_path}")


def parse_indexes(value: str) -> list[int]:
    indexes: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            index = int(item)
        except ValueError as exc:
            raise SystemExit(f"Invalid recipe index: {item}") from exc
        if index < 1:
            raise SystemExit(f"Recipe index must be positive: {index}")
        indexes.append(index)
    if not indexes:
        raise SystemExit("--indexes did not contain any recipe index")
    return indexes


def profile_to_dict(profile: UserProfile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "sex": profile.sex,
        "age": profile.age,
        "weight_kg": profile.weight_kg,
        "height_cm": profile.height_cm,
        "diet_type": profile.diet_type,
        "goal": profile.goal,
        "allergies_json": profile.allergies_json or [],
        "diseases_json": profile.diseases_json or [],
        "preferences_json": profile.preferences_json or [],
        "restrictions_text": profile.restrictions_text,
    }


def summarize_result(
    index: int,
    recipe_path: Path,
    profile_name: str,
    target_calories: float,
    result: dict[str, Any],
) -> dict[str, Any]:
    detailed = result.get("detailed_ingredients") or []
    structured = result.get("structured_recipe") or {}
    ingredients = structured.get("ingredients") or []
    heuristic_count = sum(
        1
        for item in ingredients
        if isinstance(item, dict) and item.get("source") == "heuristic_fallback"
    )
    llm_count = sum(
        1
        for item in ingredients
        if isinstance(item, dict) and item.get("source") == "llm_normalized"
    )
    fallback_grams_count = sum(1 for item in detailed if isinstance(item, dict) and item.get("used_fallback_grams"))

    return {
        "index": index,
        "file": recipe_path.name,
        "title": result.get("title"),
        "profile": profile_name,
        "target_recipe_calories": target_calories,
        "ingredient_count": len(ingredients),
        "llm_normalized_count": llm_count,
        "heuristic_fallback_count": heuristic_count,
        "fallback_grams_count": fallback_grams_count,
        "unresolved_count": len(result.get("unresolved_ingredients") or []),
        "rag_context_count": len(result.get("rag_context") or []),
        "quality_score": (result.get("analysis_quality") or {}).get("score"),
        "quality_status": (result.get("analysis_quality") or {}).get("status"),
        "recommended_recipe_servings": (result.get("portion_guidance") or {}).get("recommended_recipe_servings"),
        "calories_per_serving": ((result.get("nutrition_per_serving") or {}).get("calories") or {}).get("value"),
        "compatibility": result.get("compatibility"),
        "issues": result.get("detected_issues") or [],
        "recommendations": result.get("recommendations") or [],
        "warnings": result.get("warnings") or [],
        "unresolved_ingredients": result.get("unresolved_ingredients") or [],
    }


def summarize_suite(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_ingredients = sum(int(row["ingredient_count"] or 0) for row in rows)
    total_heuristic = sum(int(row["heuristic_fallback_count"] or 0) for row in rows)
    total_unresolved = sum(int(row["unresolved_count"] or 0) for row in rows)
    total_rag = sum(int(row["rag_context_count"] or 0) for row in rows)
    total_fallback_grams = sum(int(row["fallback_grams_count"] or 0) for row in rows)
    return {
        "total_ingredients": total_ingredients,
        "heuristic_fallback_ratio": round(total_heuristic / max(total_ingredients, 1), 3),
        "fallback_grams_ratio": round(total_fallback_grams / max(total_ingredients, 1), 3),
        "unresolved_ratio": round(total_unresolved / max(total_ingredients, 1), 3),
        "average_rag_context_count": round(total_rag / max(len(rows), 1), 2),
        "degraded_count": sum(1 for row in rows if row.get("quality_status") == "degraded"),
    }


def format_console_row(row: dict[str, Any]) -> str:
    return (
        f"{row['index']:02d}. {row['title']} | {row['profile']} | "
        f"ingredients={row['ingredient_count']} llm={row['llm_normalized_count']} "
        f"heuristic={row['heuristic_fallback_count']} unresolved={row['unresolved_count']} "
        f"rag={row['rag_context_count']} quality={row['quality_score']}"
    )


if __name__ == "__main__":
    main()
