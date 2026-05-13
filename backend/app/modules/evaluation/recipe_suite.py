from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.utils import load_data_json, normalize_text


PROFILE_BLOCKS = (
    "goal_alignment",
    "allergy_issues",
    "disease_issues",
    "preference_alignment",
    "additional_restrictions",
)

ANIMAL_FLAGS = {"meat", "poultry", "fish", "seafood", "dairy", "egg", "honey"}
VEGETARIAN_CONFLICT_FLAGS = {"meat", "poultry", "fish", "seafood"}
VEGAN_CONFLICT_FLAGS = ANIMAL_FLAGS
DIABETES_RISK_FLAGS = {"dessert", "added_sugar", "gluten", "high_calorie"}
HYPERTENSION_RISK_FLAGS = {"high_sodium", "marinade", "processed_meat"}
GOAL_RISK_FLAGS = {"high_calorie", "high_fat", "dessert", "fried_or_oil"}


@dataclass(frozen=True)
class EvalInput:
    recipe_index: int | None
    profile_name: str
    result: dict[str, Any]


def load_expectations(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        import json

        return json.loads(path.read_text(encoding="utf-8-sig"))
    return load_data_json("eval/recipe_expectations.json")


def evaluate_suite(inputs: list[EvalInput], expectations: dict[str, Any] | None = None) -> dict[str, Any]:
    expectations = expectations or load_expectations()
    rows: list[dict[str, Any]] = []
    recipe_by_index = {int(item["index"]): item for item in expectations.get("recipes", [])}
    recipe_by_title = {normalize_text(item.get("title")): item for item in expectations.get("recipes", [])}

    for item in inputs:
        result_title = normalize_text(item.result.get("title"))
        recipe_meta = recipe_by_index.get(int(item.recipe_index or 0)) or recipe_by_title.get(result_title)
        if recipe_meta is None:
            rows.append(_unknown_recipe_row(item))
            continue
        profile_slug, profile_meta = resolve_profile(item.profile_name, expectations)
        rows.append(evaluate_analysis(item.result, recipe_meta, profile_slug, profile_meta, expectations))

    return {
        "analysis_count": len(rows),
        "summary": summarize_eval_rows(rows),
        "rows": rows,
    }


def evaluate_analysis(
    result: dict[str, Any],
    recipe_meta: dict[str, Any],
    profile_slug: str,
    profile_meta: dict[str, Any],
    expectations: dict[str, Any],
) -> dict[str, Any]:
    parser_eval = evaluate_parser(result, recipe_meta)
    amount_eval = evaluate_amounts(result, recipe_meta)
    matching_eval = evaluate_matching(result, expectations)
    rag_eval = evaluate_rag(result, recipe_meta, profile_meta)
    profile_eval = evaluate_profile(result, recipe_meta, profile_slug, profile_meta)
    text_eval = evaluate_text_grounding(result, expectations, profile_meta)

    scores = {
        "parser": parser_eval["score"],
        "amounts": amount_eval["score"],
        "matching": matching_eval["score"],
        "rag": rag_eval["score"],
        "profile": profile_eval["score"],
        "text_grounding": text_eval["score"],
    }
    overall = round(
        scores["parser"] * 0.18
        + scores["amounts"] * 0.12
        + scores["matching"] * 0.18
        + scores["rag"] * 0.12
        + scores["profile"] * 0.28
        + scores["text_grounding"] * 0.12,
        2,
    )

    return {
        "recipe_index": recipe_meta.get("index"),
        "title": result.get("title") or recipe_meta.get("title"),
        "profile": profile_slug,
        "overall_score": overall,
        "scores": scores,
        "parser": parser_eval,
        "amounts": amount_eval,
        "matching": matching_eval,
        "rag": rag_eval,
        "profile_eval": profile_eval,
        "text_grounding": text_eval,
        "analysis_quality": result.get("analysis_quality") or {},
    }


def evaluate_parser(result: dict[str, Any], recipe_meta: dict[str, Any]) -> dict[str, Any]:
    expected = [normalize_text(item) for item in recipe_meta.get("required_ingredients", [])]
    forbidden = [normalize_text(item) for item in recipe_meta.get("must_not_include_ingredients", [])]
    names = _ingredient_names(result)

    missing = [item for item in expected if not _contains_token(names, item)]
    unexpected = [item for item in forbidden if _contains_token(names, item)]
    expected_count = max(len(expected), 1)
    score = 100.0 * (expected_count - len(missing)) / expected_count
    score -= 20.0 * len(unexpected)
    return {
        "score": round(_clamp_score(score), 2),
        "expected_count": len(expected),
        "found_count": len(expected) - len(missing),
        "missing_required_ingredients": missing,
        "unexpected_ingredients": unexpected,
    }


def evaluate_amounts(result: dict[str, Any], recipe_meta: dict[str, Any]) -> dict[str, Any]:
    checks = recipe_meta.get("amount_ranges") or []
    if not checks:
        return {"score": 100.0, "checked_count": 0, "failed_amounts": []}

    failed: list[dict[str, Any]] = []
    details = result.get("detailed_ingredients") or []
    for check in checks:
        detail = _find_detail(details, str(check.get("ingredient") or ""))
        if detail is None:
            failed.append({**check, "actual_g": None, "reason": "ingredient_missing"})
            continue
        grams = detail.get("estimated_grams")
        min_g = float(check.get("min_g", 0))
        max_g = float(check.get("max_g", 10**9))
        if not isinstance(grams, (int, float)) or grams < min_g or grams > max_g:
            failed.append({**check, "actual_g": grams, "reason": detail.get("grams_reason")})

    score = 100.0 * (len(checks) - len(failed)) / max(len(checks), 1)
    return {
        "score": round(_clamp_score(score), 2),
        "checked_count": len(checks),
        "failed_amounts": failed,
    }


def evaluate_matching(result: dict[str, Any], expectations: dict[str, Any]) -> dict[str, Any]:
    suspicious: list[dict[str, Any]] = []
    low_confidence_count = 0
    unresolved_common: list[str] = []
    rules = expectations.get("global_match_rules") or []

    for detail in result.get("detailed_ingredients") or []:
        if not isinstance(detail, dict):
            continue
        ingredient = detail.get("ingredient") or {}
        canonical = normalize_text(ingredient.get("name_canonical") or ingredient.get("name_raw"))
        matched = normalize_text(detail.get("matched_name"))
        if detail.get("match_confidence") == "low":
            low_confidence_count += 1
        if detail.get("nutrition_resolution_status") == "unresolved":
            unresolved_common.append(canonical)
        for rule in rules:
            ingredient_token = normalize_text(rule.get("ingredient"))
            if ingredient_token and ingredient_token not in canonical:
                continue
            banned = [normalize_text(item) for item in rule.get("banned_match_contains", [])]
            hit = next((item for item in banned if item and item in matched), None)
            if hit:
                suspicious.append(
                    {
                        "ingredient": canonical,
                        "matched_name": detail.get("matched_name"),
                        "rule": rule,
                    }
                )

    score = 100.0 - len(suspicious) * 30.0 - low_confidence_count * 3.0 - len(unresolved_common) * 15.0
    return {
        "score": round(_clamp_score(score), 2),
        "suspicious_matches": suspicious,
        "low_confidence_count": low_confidence_count,
        "unresolved_ingredients": unresolved_common,
    }


def evaluate_rag(result: dict[str, Any], recipe_meta: dict[str, Any], profile_meta: dict[str, Any]) -> dict[str, Any]:
    expected = set(recipe_meta.get("expected_kb_sources") or [])
    expected.update(profile_meta.get("expected_kb_sources") or [])
    if not expected:
        return {"score": 100.0, "expected_sources": [], "found_sources": [], "missing_sources": []}

    found = {
        str(item.get("source") or item.get("title") or "")
        for item in result.get("rag_context") or []
        if isinstance(item, dict)
    }
    missing = sorted(source for source in expected if source not in found)
    score = 100.0 * (len(expected) - len(missing)) / max(len(expected), 1)
    return {
        "score": round(_clamp_score(score), 2),
        "expected_sources": sorted(expected),
        "found_sources": sorted(found),
        "missing_sources": missing,
    }


def evaluate_profile(
    result: dict[str, Any],
    recipe_meta: dict[str, Any],
    profile_slug: str,
    profile_meta: dict[str, Any],
) -> dict[str, Any]:
    expected = expected_profile_statuses(recipe_meta, profile_meta)
    assessment = result.get("profile_assessment") or {}
    actual = {
        key: (assessment.get(key) or {}).get("status")
        for key in PROFILE_BLOCKS
    }

    missing_expected_conflicts: list[dict[str, str]] = []
    unexpected_conflicts: list[dict[str, str]] = []
    status_mismatches: list[dict[str, str]] = []
    for block, expected_status in expected.items():
        actual_status = actual.get(block) or "missing"
        if expected_status == "conflict" and actual_status != "conflict":
            missing_expected_conflicts.append({"block": block, "expected": expected_status, "actual": actual_status})
        elif expected_status != "conflict" and actual_status == "conflict":
            unexpected_conflicts.append({"block": block, "expected": expected_status, "actual": actual_status})
        elif expected_status == "ok" and actual_status not in {"ok", "warning"}:
            status_mismatches.append({"block": block, "expected": expected_status, "actual": actual_status})

    compatibility = result.get("compatibility") or {}
    compatibility_errors = _compatibility_errors(expected, compatibility)
    score = (
        100.0
        - len(missing_expected_conflicts) * 35.0
        - len(unexpected_conflicts) * 35.0
        - len(status_mismatches) * 15.0
        - len(compatibility_errors) * 12.0
    )
    return {
        "score": round(_clamp_score(score), 2),
        "profile": profile_slug,
        "expected_statuses": expected,
        "actual_statuses": actual,
        "missing_expected_conflicts": missing_expected_conflicts,
        "unexpected_conflicts": unexpected_conflicts,
        "status_mismatches": status_mismatches,
        "compatibility_errors": compatibility_errors,
    }


def evaluate_text_grounding(
    result: dict[str, Any],
    expectations: dict[str, Any],
    profile_meta: dict[str, Any],
) -> dict[str, Any]:
    issue_texts = _analysis_text_items(result)
    joined = "\n".join(issue_texts).lower()
    false_claims = [
        pattern
        for pattern in expectations.get("false_claim_patterns", [])
        if normalize_text(pattern) in normalize_text(joined)
    ]
    profile_noise = [
        phrase
        for phrase in profile_meta.get("noise_phrases", [])
        if any(_looks_like_profile_noise(item, phrase) for item in result.get("detected_issues") or [])
    ]
    score = 100.0 - len(false_claims) * 25.0 - len(profile_noise) * 8.0
    return {
        "score": round(_clamp_score(score), 2),
        "false_claims": false_claims,
        "profile_noise_phrases": profile_noise,
    }


def expected_profile_statuses(recipe_meta: dict[str, Any], profile_meta: dict[str, Any]) -> dict[str, str]:
    flags = set(recipe_meta.get("flags") or [])
    statuses = {key: "ok" for key in PROFILE_BLOCKS}

    allergy_flags = set(profile_meta.get("allergy_flags") or [])
    if allergy_flags & flags:
        statuses["allergy_issues"] = "conflict"

    diet = profile_meta.get("diet")
    if diet == "vegetarian" and flags & VEGETARIAN_CONFLICT_FLAGS:
        statuses["additional_restrictions"] = "conflict"
    elif diet == "vegan" and flags & VEGAN_CONFLICT_FLAGS:
        statuses["additional_restrictions"] = "conflict"
    elif diet == "low_carb" and flags & {"dessert", "added_sugar", "gluten"}:
        statuses["additional_restrictions"] = "warning"

    disease_flags = set(profile_meta.get("disease_flags") or [])
    if "diabetes" in disease_flags and flags & DIABETES_RISK_FLAGS:
        statuses["disease_issues"] = "warning"
    if "hypertension" in disease_flags and flags & HYPERTENSION_RISK_FLAGS:
        statuses["disease_issues"] = "warning"

    preference_flags = set(profile_meta.get("preference_flags") or [])
    if "avoid_spicy" in preference_flags and "spicy" in flags:
        statuses["preference_alignment"] = "warning"
    if "low_sodium" in preference_flags and flags & HYPERTENSION_RISK_FLAGS:
        statuses["preference_alignment"] = "warning"

    if flags & GOAL_RISK_FLAGS:
        statuses["goal_alignment"] = "warning"
    if profile_meta.get("diet") == "balanced" and "high_protein" in flags:
        statuses["goal_alignment"] = "ok"

    return statuses


def resolve_profile(profile_name: str, expectations: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    normalized = normalize_text(profile_name)
    for slug, profile in (expectations.get("profiles") or {}).items():
        if any(normalize_text(token) in normalized for token in profile.get("name_contains", [])):
            return slug, profile
    return "unknown_profile", {}


def summarize_eval_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    score_keys = ["parser", "amounts", "matching", "rag", "profile", "text_grounding"]
    category_averages = {
        key: round(sum(float(row["scores"].get(key, 0)) for row in rows) / len(rows), 2)
        for key in score_keys
        if "scores" in rows[0]
    }
    issue_counts: Counter[str] = Counter()
    for row in rows:
        if row.get("parser", {}).get("missing_required_ingredients"):
            issue_counts["missing_required_ingredients"] += 1
        if row.get("amounts", {}).get("failed_amounts"):
            issue_counts["amount_out_of_range"] += 1
        if row.get("matching", {}).get("suspicious_matches"):
            issue_counts["suspicious_usda_match"] += 1
        if row.get("matching", {}).get("unresolved_ingredients"):
            issue_counts["unresolved_ingredient"] += 1
        if row.get("rag", {}).get("missing_sources"):
            issue_counts["missing_expected_kb_source"] += 1
        if row.get("profile_eval", {}).get("missing_expected_conflicts"):
            issue_counts["missing_expected_profile_conflict"] += 1
        if row.get("profile_eval", {}).get("unexpected_conflicts"):
            issue_counts["unexpected_profile_conflict"] += 1
        if row.get("text_grounding", {}).get("false_claims"):
            issue_counts["false_claim_text"] += 1
        if row.get("text_grounding", {}).get("profile_noise_phrases"):
            issue_counts["profile_text_in_issues"] += 1

    return {
        "average_overall_score": round(sum(float(row.get("overall_score", 0)) for row in rows) / len(rows), 2),
        "min_overall_score": round(min(float(row.get("overall_score", 0)) for row in rows), 2),
        "category_averages": category_averages,
        "issue_counts": dict(issue_counts),
        "rows_below_80": sum(1 for row in rows if float(row.get("overall_score", 0)) < 80),
    }


def _unknown_recipe_row(item: EvalInput) -> dict[str, Any]:
    return {
        "recipe_index": item.recipe_index,
        "title": item.result.get("title"),
        "profile": item.profile_name,
        "overall_score": 0.0,
        "scores": {},
        "error": "recipe_expectation_not_found",
    }


def _ingredient_names(result: dict[str, Any]) -> list[str]:
    names: list[str] = []
    structured = result.get("structured_recipe") or {}
    for item in structured.get("ingredients") or []:
        if isinstance(item, dict):
            names.append(normalize_text(item.get("name_canonical") or item.get("name_raw")))
    if names:
        return names
    for detail in result.get("detailed_ingredients") or []:
        ingredient = detail.get("ingredient") if isinstance(detail, dict) else None
        if isinstance(ingredient, dict):
            names.append(normalize_text(ingredient.get("name_canonical") or ingredient.get("name_raw")))
    return names


def _contains_token(names: list[str], expected: str) -> bool:
    expected = normalize_text(expected)
    if not expected:
        return True
    expected_tokens = [token for token in expected.split() if token]
    for name in names:
        name = normalize_text(name)
        if expected in name or name in expected:
            return True
        name_tokens = [token for token in name.split() if token]
        if expected_tokens and all(any(_similar_word(expected_token, name_token) for name_token in name_tokens) for expected_token in expected_tokens):
            return True
    return False


def _similar_word(left: str, right: str) -> bool:
    if left == right or left in right or right in left:
        return True
    common_prefix = 0
    for left_char, right_char in zip(left, right):
        if left_char != right_char:
            break
        common_prefix += 1
    return common_prefix >= 3


def _find_detail(details: list[dict[str, Any]], ingredient_token: str) -> dict[str, Any] | None:
    token = normalize_text(ingredient_token)
    for detail in details:
        ingredient = detail.get("ingredient") if isinstance(detail, dict) else None
        if not isinstance(ingredient, dict):
            continue
        name = normalize_text(ingredient.get("name_canonical") or ingredient.get("name_raw"))
        if token in name or name in token:
            return detail
    return None


def _analysis_text_items(result: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for key in ("summary",):
        if result.get(key):
            items.append(str(result[key]))
    for key in ("detected_issues", "recommendations", "warnings"):
        items.extend(str(item) for item in result.get(key) or [])
    for block in (result.get("profile_assessment") or {}).values():
        if not isinstance(block, dict):
            continue
        items.append(str(block.get("summary") or ""))
        items.extend(str(item) for item in block.get("evidence") or [])
        items.extend(str(item) for item in block.get("recommendations") or [])
    return [item for item in items if item.strip()]


def _looks_like_profile_noise(text: Any, phrase: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_phrase = normalize_text(phrase)
    if not normalized_text or not normalized_phrase:
        return False
    return normalized_phrase in normalized_text and len(normalized_text) <= max(len(normalized_phrase) + 40, 80)


def _compatibility_errors(expected: dict[str, str], compatibility: dict[str, str]) -> list[str]:
    errors: list[str] = []
    if expected.get("allergy_issues") == "conflict" and compatibility.get("restriction") != "low":
        errors.append("allergy_conflict_without_low_restriction")
    if expected.get("additional_restrictions") == "conflict" and compatibility.get("diet") != "low":
        errors.append("diet_conflict_without_low_diet")
    if expected.get("goal_alignment") == "warning" and compatibility.get("goal") == "high":
        errors.append("goal_warning_with_high_goal_compatibility")
    return errors


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))
