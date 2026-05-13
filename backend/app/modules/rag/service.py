from __future__ import annotations

import re
from typing import Any

from app.core.utils import dedupe_texts, format_portions, normalize_spaces, normalize_text
from app.modules.rag.retrieval import SOURCE_HINT_PREFIX, retrieval_service
from app.modules.structuring.schemas import StructuredRecipe
from app.services.ollama_service import ollama_service


class RagService:
    def retrieve_context(
        self,
        recipe_text: str,
        recipe: StructuredRecipe,
        matched_ingredients: list[dict[str, Any]],
        nutrition_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        profile_context = nutrition_result.get("profile_context") or {}
        ingredient_context = self._build_ingredient_context(matched_ingredients, nutrition_result)

        profile_queries: list[str] = []
        profile_queries.extend(profile_context.get("rag_queries") or [])
        profile_queries.extend(profile_context.get("profile_items") or [])
        profile_queries.extend(
            [
                f"{item.get('kind')}: {item.get('value')}"
                for item in profile_context.get("profile_constraints") or []
                if isinstance(item, dict) and item.get("value")
            ]
        )

        ingredient_queries: list[str] = [recipe.title, recipe_text[:500]]
        ingredient_queries.extend([item.name_canonical for item in recipe.ingredients[:12]])
        ingredient_queries.extend([item.name_raw for item in recipe.ingredients[:12]])
        ingredient_queries.extend([item.get("matched_name") for item in ingredient_context if item.get("matched_name")])
        ingredient_queries.extend([item.get("matched_category") for item in ingredient_context if item.get("matched_category")])
        ingredient_queries.extend([item.get("name_canonical") for item in ingredient_context if item.get("name_canonical")])
        ingredient_queries.extend([item.get("name_raw") for item in ingredient_context if item.get("name_raw")])

        nutrition_signals = self._build_nutrition_signals(nutrition_result)
        signal_queries = [item["label"] for item in nutrition_signals]
        if (nutrition_result.get("portion_guidance") or {}).get("recommended_recipe_servings", 1) > 1:
            signal_queries.append("portion size rules")
        source_hints = self._kb_source_hints(profile_context, ingredient_context, nutrition_result, nutrition_signals, recipe)

        queries = [
            *(f"{SOURCE_HINT_PREFIX}{source}" for source in source_hints),
            *dedupe_texts(profile_queries)[:18],
            *dedupe_texts(ingredient_queries)[:14],
            *dedupe_texts(signal_queries)[:4],
        ]
        return retrieval_service.search(dedupe_texts(queries), top_k=10)

    def _kb_source_hints(
        self,
        profile_context: dict[str, Any],
        ingredient_context: list[dict[str, Any]],
        nutrition_result: dict[str, Any],
        nutrition_signals: list[dict[str, Any]],
        recipe: StructuredRecipe,
    ) -> list[str]:
        hints: list[str] = []
        diet_code = profile_context.get("diet_code")
        goal_code = profile_context.get("goal_code")
        allergy_codes = set(profile_context.get("allergy_codes") or [])
        restriction_food_codes = set(profile_context.get("restriction_food_codes") or [])
        disease_codes = set(profile_context.get("disease_codes") or [])
        preference_codes = set(profile_context.get("preference_codes") or [])

        if diet_code == "vegan":
            hints.extend(["kb_vegan.txt", "kb_vegetarian.txt"])
        elif diet_code == "vegetarian":
            hints.append("kb_vegetarian.txt")
        elif diet_code == "low_carb":
            hints.append("kb_low_carb.txt")
        elif diet_code == "mediterranean":
            hints.append("kb_mediterranean_diet.txt")

        if goal_code == "muscle_gain" or "high_protein" in preference_codes:
            hints.extend(["kb_high_protein.txt", "kb_nutrition_thresholds.txt"])
        if goal_code == "fat_loss":
            hints.extend(["kb_weight_loss.txt", "kb_nutrition_thresholds.txt"])

        if "diabetes" in disease_codes:
            hints.extend(["kb_diabetes.txt", "kb_low_carb.txt"])
        if "hypertension" in disease_codes or "low_sodium" in preference_codes:
            hints.extend(["kb_hypertension.txt", "kb_low_sodium.txt"])
        if "gout" in disease_codes:
            hints.append("kb_gout_and_purines.txt")
        if disease_codes & {"kidney", "gerd", "ibs"}:
            hints.append("kb_kidney_and_gi_conditions.txt")

        allergy_like_codes = allergy_codes | restriction_food_codes
        if allergy_like_codes:
            hints.append("kb_common_allergens.txt")
        if "dairy" in allergy_like_codes:
            hints.append("kb_lactose_intolerance.txt")
        if "gluten" in allergy_like_codes:
            hints.append("kb_gluten_free.txt")

        ingredient_text = self._ingredient_signal_text(ingredient_context, recipe)
        if self._has_any(ingredient_text, ("ветчин", "бекон", "колбас", "копчен", "сол", "маринад", "pickle", "ham", "bacon", "sausage", "salt", "sodium", "marinade")):
            hints.extend(["kb_low_sodium.txt", "kb_hypertension.txt"])
        if self._has_any(ingredient_text, ("скумбр", "рыб", "кревет", "морепродукт", "fish", "mackerel", "shrimp", "shellfish")):
            hints.append("kb_common_allergens.txt")
        if self._has_any(ingredient_text, ("молок", "сыр", "сметан", "сливочн", "йогурт", "творог", "milk", "cheese", "sour cream", "butter", "yogurt")):
            hints.extend(["kb_lactose_intolerance.txt", "kb_common_allergens.txt"])
        if self._has_any(ingredient_text, ("пшен", "мука", "хлеб", "сухар", "макарон", "wheat", "flour", "bread", "breadcrumbs", "pasta")):
            hints.extend(["kb_gluten_free.txt", "kb_common_allergens.txt"])
        if self._has_any(ingredient_text, ("сахар", "варенье", "мед", "десерт", "sugar", "jam", "honey", "dessert")):
            hints.extend(["kb_diabetes.txt", "kb_nutrition_thresholds.txt"])
        if self._has_any(ingredient_text, ("мяс", "свинин", "ветчин", "говядин", "куриц", "рыб", "pork", "ham", "beef", "chicken", "fish")):
            hints.extend(["kb_vegetarian.txt", "kb_vegan.txt"])

        signal_codes = {item.get("code") for item in nutrition_signals}
        if "high_sodium" in signal_codes:
            hints.extend(["kb_low_sodium.txt", "kb_hypertension.txt"])
        if signal_codes & {"high_fat", "high_calories", "target_calories_exceeded", "whole_recipe_portion"}:
            hints.extend(["kb_nutrition_thresholds.txt", "kb_portion_size_rules.txt"])
        if (nutrition_result.get("portion_guidance") or {}).get("target_recipe_calories"):
            hints.append("kb_portion_size_rules.txt")

        return dedupe_texts(hints)[:10]

    def _ingredient_signal_text(self, ingredient_context: list[dict[str, Any]], recipe: StructuredRecipe) -> str:
        parts = [recipe.title]
        for item in ingredient_context:
            parts.extend(
                str(item.get(key) or "")
                for key in ("name_raw", "name_canonical", "name_en", "matched_name", "matched_category")
            )
        if not ingredient_context:
            for item in recipe.ingredients:
                parts.extend([item.name_raw, item.name_canonical, item.name_en or ""])
        return normalize_text(" ".join(parts))

    def _has_any(self, text: str, tokens: tuple[str, ...]) -> bool:
        return any(token in text for token in tokens)

    def generate_analysis(
        self,
        recipe_text: str,
        recipe: StructuredRecipe,
        matched_ingredients: list[dict[str, Any]],
        nutrition_result: dict[str, Any],
        profile: dict[str, Any],
        rag_context: list[dict[str, Any]],
    ) -> dict[str, Any]:
        profile_context = nutrition_result.get("profile_context") or {}
        ingredient_context = self._build_ingredient_context(matched_ingredients, nutrition_result)
        nutrition_signals = self._build_nutrition_signals(nutrition_result)

        analysis_input = {
            "recipe_title": recipe.title,
            "recipe_text_excerpt": recipe_text[:1200],
            "structured_recipe": recipe.model_dump(),
            "profile": profile,
            "profile_context": profile_context,
            "ingredient_context": ingredient_context,
            "nutrition_total": nutrition_result["nutrition_total"],
            "nutrition_per_serving": nutrition_result["nutrition_per_serving"],
            "nutrition_signals": nutrition_signals,
            "analysis_quality": nutrition_result["analysis_quality"],
            "unresolved_ingredients": nutrition_result["unresolved_ingredients"],
            "portion_guidance": nutrition_result.get("portion_guidance", {}),
            "rag_context": rag_context,
        }
        try:
            llm_result = ollama_service.generate_profile_analysis(analysis_input)
        except Exception:
            llm_result = None
        return self._merge_with_fallback(recipe, nutrition_result, rag_context, llm_result, nutrition_signals)

    def _merge_with_fallback(
        self,
        recipe: StructuredRecipe,
        nutrition_result: dict[str, Any],
        rag_context: list[dict[str, Any]],
        llm_result: dict[str, Any] | None,
        nutrition_signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fallback = self._fallback_response(recipe, nutrition_result, rag_context, nutrition_signals)
        segmented_blocks = self._extract_valid_profile_blocks(
            llm_result.get("profile_assessment") if isinstance(llm_result, dict) else None,
            fallback["profile_assessment"],
        )
        if segmented_blocks:
            merged = self._merge_segmented_response(recipe, fallback, segmented_blocks)
            merged = self._sanitize_irrelevant_profile_blocks(recipe, merged, fallback, nutrition_result)
            merged = self._sanitize_obvious_personalization_hallucinations(merged, nutrition_result)
            return self._apply_profile_conflict_guards(merged, nutrition_result)

        return self._apply_profile_conflict_guards(fallback, nutrition_result)

    def _extract_valid_profile_blocks(
        self,
        llm: Any,
        fallback: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(llm, dict):
            return {}

        valid: dict[str, dict[str, Any]] = {}
        for key, fallback_block in fallback.items():
            llm_block = llm.get(key)
            if not isinstance(llm_block, dict):
                continue
            summary = normalize_spaces(str(llm_block.get("summary") or ""))
            if len(summary) < 20 or summary.lower() in {"unknown", "ok", "none", "null"}:
                continue
            if self._block_contradicts_fallback_profile(key, summary, fallback_block):
                continue
            evidence = self._text_list(llm_block.get("evidence"))
            recommendations = self._text_list(llm_block.get("recommendations"))
            status = self._normalize_block_status(str(llm_block.get("status") or ""), evidence)
            compatibility = self._normalize_block_compatibility(
                str(llm_block.get("compatibility") or ""),
                status,
                str(fallback_block.get("compatibility") or "medium"),
            )
            block = dict(fallback_block)
            block.update(
                {
                    "summary": summary,
                    "evidence": evidence or self._text_list(fallback_block.get("evidence")),
                    "recommendations": recommendations or self._text_list(fallback_block.get("recommendations")),
                    "status": status,
                    "compatibility": compatibility,
                }
            )
            valid[key] = block
        return valid

    def _block_contradicts_fallback_profile(
        self,
        key: str,
        summary: str,
        fallback_block: dict[str, Any],
    ) -> bool:
        summary_norm = normalize_text(summary)
        fallback_norm = normalize_text(str(fallback_block.get("summary") or ""))
        if key == "allergy_issues":
            has_allergies = "в профиле указаны аллергии" in fallback_norm
            denies_allergies = "не указаны аллерг" in summary_norm or "аллергии не указаны" in summary_norm
            return has_allergies and denies_allergies
        if key == "preference_alignment":
            has_preferences = "предпочтения профиля" in fallback_norm
            denies_preferences = (
                "предпочтения не указаны" in summary_norm
                or "не указаны предпочт" in summary_norm
                or "не предоставлены" in summary_norm
            )
            return has_preferences and denies_preferences
        if key == "disease_issues":
            no_diseases = "заболевания в профиле не указаны" in fallback_norm
            invents_medical_risk = any(token in summary_norm for token in ("натри", "сахар", "жир", "пациент", "заболев"))
            return no_diseases and invents_medical_risk and "не указаны" not in summary_norm
        return False

    def _merge_segmented_response(
        self,
        recipe: StructuredRecipe,
        fallback: dict[str, Any],
        valid_blocks: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        assessment = dict(fallback["profile_assessment"])
        assessment.update(valid_blocks)

        detected_issues = self._text_list(fallback.get("detected_issues"))
        recommendations = self._text_list(fallback.get("recommendations"))
        for block in assessment.values():
            if block.get("status") in {"warning", "conflict"}:
                detected_issues.extend(self._text_list(block.get("evidence")))
            recommendations.extend(self._text_list(block.get("recommendations")))

        return {
            "summary": self._build_segmented_summary(recipe, fallback, assessment),
            "detected_issues": dedupe_texts(detected_issues),
            "recommendations": dedupe_texts(recommendations),
            "warnings": self._text_list(fallback.get("warnings")),
            "compatibility": self._compatibility_from_assessment(fallback["compatibility"], assessment),
            "profile_assessment": assessment,
        }

    def _normalize_block_status(self, status: str, evidence: list[str]) -> str:
        normalized = normalize_text(status)
        if normalized in {"ok", "warning", "conflict"}:
            return normalized
        if "конфликт" in normalized or "conflict" in normalized:
            return "conflict"
        if "нюанс" in normalized or "warning" in normalized or evidence:
            return "warning"
        return "ok"

    def _normalize_block_compatibility(self, value: str, status: str, fallback: str) -> str:
        normalized = normalize_text(value)
        if status == "conflict":
            return "low"
        if status == "warning":
            return "medium"
        if status == "ok":
            return "high"
        if normalized in {"low", "medium", "high"}:
            return normalized
        if "низ" in normalized or "low" in normalized:
            return "low"
        if "сред" in normalized or "medium" in normalized:
            return "medium"
        if "выс" in normalized or "high" in normalized:
            return "high"
        return fallback if fallback in {"low", "medium", "high"} else "medium"

    def _compatibility_for_status(self, status: Any, fallback: str = "medium") -> str:
        normalized = normalize_text(status)
        if normalized == "conflict":
            return "low"
        if normalized == "warning":
            return "medium"
        if normalized == "ok":
            return "high"
        return fallback if fallback in {"low", "medium", "high"} else "medium"

    def _compatibility_from_assessment(
        self,
        fallback: dict[str, str],
        assessment: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        result = dict(fallback)
        goal_block = assessment.get("goal_alignment", {})
        diet_block = assessment.get("additional_restrictions", {})
        if goal_block:
            result["goal"] = self._compatibility_for_status(goal_block.get("status"), result.get("goal", "medium"))
        if diet_block:
            result["diet"] = self._compatibility_for_status(diet_block.get("status"), result.get("diet", "medium"))

        restriction_statuses = [
            normalize_text(assessment.get(key, {}).get("status"))
            for key in ("allergy_issues", "disease_issues", "preference_alignment", "additional_restrictions")
            if isinstance(assessment.get(key), dict)
        ]
        if "conflict" in restriction_statuses:
            result["restriction"] = "low"
        elif "warning" in restriction_statuses:
            result["restriction"] = "medium"
        elif restriction_statuses:
            result["restriction"] = "high"
        return result

    def _build_segmented_summary(
        self,
        recipe: StructuredRecipe,
        fallback: dict[str, Any],
        assessment: dict[str, dict[str, Any]],
    ) -> str:
        conflicts = [str(block.get("title")) for block in assessment.values() if block.get("status") == "conflict"]
        warnings = [str(block.get("title")) for block in assessment.values() if block.get("status") == "warning"]
        if conflicts:
            intro = f"Рецепт «{recipe.title}» имеет прямые конфликты с профилем в блоках: {', '.join(conflicts[:3])}."
        elif warnings:
            intro = f"Рецепт «{recipe.title}» в целом можно адаптировать под профиль, но есть нюансы: {', '.join(warnings[:3])}."
        else:
            intro = f"Рецепт «{recipe.title}» в целом совместим с выбранным профилем по распознанным ингредиентам и нутриентам."
        return intro

    def _sanitize_irrelevant_profile_blocks(
        self,
        recipe: StructuredRecipe,
        result: dict[str, Any],
        fallback: dict[str, Any],
        nutrition_result: dict[str, Any],
    ) -> dict[str, Any]:
        profile_context = nutrition_result.get("profile_context") or {}
        hard_conflict_keys = {
            item["assessment_key"]
            for item in self._detect_hard_profile_conflicts(nutrition_result)
        }
        assessment = dict(result.get("profile_assessment") or {})
        fallback_assessment = fallback.get("profile_assessment") or {}

        for key, block_value in list(assessment.items()):
            if not isinstance(block_value, dict):
                continue
            block = dict(block_value)
            block_text = self._block_text(block)
            replace_with_fallback = False

            if key == "allergy_issues" and not profile_context.get("raw_allergies"):
                replace_with_fallback = block.get("status") != "ok" or bool(self._text_list(block.get("evidence")))
            elif key == "allergy_issues" and key not in hard_conflict_keys and block.get("status") in {"warning", "conflict"}:
                replace_with_fallback = True
            elif key == "disease_issues" and not profile_context.get("raw_diseases"):
                replace_with_fallback = True
            elif self._contains_inapplicable_diet_claim(block_text, profile_context):
                replace_with_fallback = True
            elif (
                key == "additional_restrictions"
                and key not in hard_conflict_keys
                and self._contains_false_vegetarian_claim(block_text, profile_context)
            ):
                replace_with_fallback = True
            elif key == "preference_alignment" and self._contains_false_meat_preference_conflict(block_text, profile_context):
                replace_with_fallback = True

            if replace_with_fallback and key in fallback_assessment:
                assessment[key] = dict(fallback_assessment[key])
                continue

            if block.get("status") == "conflict" and key not in hard_conflict_keys:
                block["status"] = "warning"
            block["compatibility"] = self._compatibility_for_status(
                block.get("status"),
                str(block.get("compatibility") or fallback_assessment.get(key, {}).get("compatibility") or "medium"),
            )
            assessment[key] = block

        sanitized = dict(result)
        sanitized["profile_assessment"] = assessment
        return self._rebuild_response_from_assessment(recipe, sanitized, fallback, profile_context)

    def _rebuild_response_from_assessment(
        self,
        recipe: StructuredRecipe,
        result: dict[str, Any],
        fallback: dict[str, Any],
        profile_context: dict[str, Any],
    ) -> dict[str, Any]:
        assessment = dict(result.get("profile_assessment") or {})
        detected_issues = self._text_list(fallback.get("detected_issues"))
        recommendations = self._text_list(fallback.get("recommendations"))
        has_assessment_issues = False
        for block in assessment.values():
            if not isinstance(block, dict):
                continue
            if block.get("status") in {"warning", "conflict"}:
                has_assessment_issues = True
                detected_issues.extend(self._text_list(block.get("evidence")))
            recommendations.extend(self._text_list(block.get("recommendations")))
        if has_assessment_issues:
            detected_issues = [
                item
                for item in detected_issues
                if "\u044f\u0432\u043d\u044b\u0445 \u043a\u043e\u043d\u0444\u043b\u0438\u043a\u0442\u043e\u0432" not in normalize_text(item)
            ]
        detected_issues = [
            item for item in detected_issues if not self._is_profile_noise_issue(item, profile_context)
        ]

        rebuilt = dict(result)
        rebuilt["detected_issues"] = dedupe_texts(detected_issues)
        rebuilt["recommendations"] = dedupe_texts(recommendations)
        rebuilt["compatibility"] = self._compatibility_from_assessment(fallback["compatibility"], assessment)
        rebuilt["summary"] = self._build_segmented_summary(recipe, fallback, assessment)
        return rebuilt

    def _block_text(self, block: dict[str, Any]) -> str:
        return normalize_text(
            " ".join(
                [
                    str(block.get("summary") or ""),
                    *self._text_list(block.get("evidence")),
                    *self._text_list(block.get("recommendations")),
                ]
            )
        )

    def _contains_inapplicable_diet_claim(self, text: str, profile_context: dict[str, Any]) -> bool:
        diet_code = profile_context.get("diet_code")
        strict_diet_codes = {"vegan", "vegetarian", "pescatarian", "halal", "kosher"}
        if diet_code in strict_diet_codes:
            return False
        return any(
            token in text
            for token in (
                "vegetarian",
                "vegan",
                "\u0432\u0435\u0433\u0435\u0442",
                "\u0432\u0435\u0433\u0430\u043d",
                "\u0440\u0430\u0441\u0442\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u043c\u0443 \u043f\u0438\u0442\u0430\u043d\u0438\u044e",
            )
        )

    def _contains_false_vegetarian_claim(self, text: str, profile_context: dict[str, Any]) -> bool:
        if profile_context.get("diet_code") != "vegetarian":
            return False
        text = normalize_text(text)
        allowed_vegetarian_tokens = (
            "яйц",
            "яиц",
            "яич",
            "egg",
            "молок",
            "сыр",
            "сметан",
            "сливочн",
            "творог",
            "йогурт",
            "milk",
            "cheese",
            "sour cream",
            "butter",
            "yogurt",
            "варенье",
            "jam",
            "preserve",
        )
        conflict_markers = (
            "противореч",
            "конфликт",
            "несовмест",
            "не соответств",
            "не являются раститель",
            "не является раститель",
            "животный продукт",
            "животные продукты",
        )
        return any(token in text for token in allowed_vegetarian_tokens) and any(marker in text for marker in conflict_markers)

    def _contains_false_meat_preference_conflict(self, text: str, profile_context: dict[str, Any]) -> bool:
        raw_preferences = normalize_text(" ".join(str(item) for item in profile_context.get("raw_preferences") or []))
        allows_meat = any(
            token in raw_preferences
            for token in (
                "\u043c\u043e\u0436\u043d\u043e \u043c\u044f\u0441",
                "\u043c\u044f\u0441\u043e \u0438 \u0440\u044b\u0431",
                "meat",
            )
        )
        if not allows_meat:
            return False
        meat_conflict_markers = (
            "\u0431\u0435\u0437 \u043c\u044f\u0441",
            "\u0431\u0435\u0437\u043c\u044f\u0441",
            "\u043f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0438\u0442 \u043c\u044f\u0441",
            "\u043a\u043e\u043d\u0444\u043b\u0438\u043a\u0442\u0443\u0435\u0442 \u0441 \u043c\u044f\u0441",
            "without meat",
            "no meat",
        )
        return any(marker in text for marker in meat_conflict_markers)

    def _text_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value:
            if isinstance(item, dict):
                item = item.get("text") or item.get("recommendation") or item.get("issue") or item.get("name") or ""
            text = normalize_spaces(str(item))
            if text:
                cleaned.append(text)
        return dedupe_texts(cleaned)

    def _apply_profile_conflict_guards(
        self,
        result: dict[str, Any],
        nutrition_result: dict[str, Any],
    ) -> dict[str, Any]:
        profile_context = nutrition_result.get("profile_context") or {}
        conflicts = self._detect_hard_profile_conflicts(nutrition_result)
        if not conflicts:
            return result

        guarded = dict(result)
        existing_issues = [
            item
            for item in self._text_list(guarded.get("detected_issues"))
            if "явных конфликтов" not in normalize_text(item)
            and not self._is_profile_noise_issue(item, profile_context)
        ]
        conflict_issues = [item["issue"] for item in conflicts]
        conflict_recommendations = [item["recommendation"] for item in conflicts]
        guarded["detected_issues"] = dedupe_texts([*conflict_issues, *existing_issues])
        guarded["recommendations"] = dedupe_texts([*conflict_recommendations, *self._text_list(guarded.get("recommendations"))])

        compatibility = dict(guarded.get("compatibility") or {})
        for item in conflicts:
            if item["compatibility_key"] in compatibility:
                compatibility[item["compatibility_key"]] = "low"
        guarded["compatibility"] = compatibility

        assessment = dict(guarded.get("profile_assessment") or {})
        for item in conflicts:
            block = dict(assessment.get(item["assessment_key"]) or {})
            block.setdefault("key", item["assessment_key"])
            block.setdefault("title", item["assessment_title"])
            block["status"] = "conflict"
            block["compatibility"] = "low"
            block["summary"] = item["issue"]
            block["evidence"] = dedupe_texts([item["evidence"], *self._text_list(block.get("evidence"))])
            block["recommendations"] = dedupe_texts([item["recommendation"], *self._text_list(block.get("recommendations"))])
            assessment[item["assessment_key"]] = block
        guarded["profile_assessment"] = assessment

        summary = normalize_spaces(str(guarded.get("summary") or ""))
        if "явных конфликтов" in normalize_text(summary) or not summary:
            guarded["summary"] = conflict_issues[0]
        elif conflict_issues[0] not in summary:
            guarded["summary"] = normalize_spaces(f"{conflict_issues[0]} {summary}")
        return guarded

    def _detect_hard_profile_conflicts(self, nutrition_result: dict[str, Any]) -> list[dict[str, str]]:
        profile_context = nutrition_result.get("profile_context") or {}
        ingredient_context = self._build_ingredient_context(
            nutrition_result.get("matched_ingredients", []),
            nutrition_result,
        )
        if not ingredient_context:
            ingredient_context = [
                item
                for item in (
                    (detail.get("ingredient") if isinstance(detail, dict) else None)
                    for detail in nutrition_result.get("detailed_ingredients", [])
                )
                if isinstance(item, dict)
            ]

        specs = self._profile_conflict_specs(profile_context)
        conflicts: list[dict[str, str]] = []
        for spec in specs:
            matched_names = self._matching_ingredient_names(ingredient_context, spec["tokens"], spec.get("exclude", []))
            if not matched_names:
                continue
            names = self._compact_list(matched_names, limit=4)
            conflicts.append(
                {
                    "issue": f"Прямой конфликт с профилем: {spec['label']}. В рецепте есть: {names}.",
                    "evidence": f"В рецепте найдены: {names}.",
                    "recommendation": spec["recommendation"],
                    "compatibility_key": spec["compatibility_key"],
                    "assessment_key": spec["assessment_key"],
                    "assessment_title": spec["assessment_title"],
                }
            )
        return conflicts

    def _sanitize_obvious_personalization_hallucinations(
        self,
        result: dict[str, Any],
        nutrition_result: dict[str, Any],
    ) -> dict[str, Any]:
        profile_context = nutrition_result.get("profile_context") or {}
        strict_plant_profile = profile_context.get("diet_code") in {"vegan", "vegetarian"}

        sanitized = dict(result)
        removed_issue = False
        if self._is_false_non_plant_claim(normalize_spaces(str(sanitized.get("summary") or ""))):
            sanitized["summary"] = "По распознанным ингредиентам явных конфликтов с растительным типом питания не найдено."
            removed_issue = True

        detected_issues: list[str] = []
        for issue in self._text_list(sanitized.get("detected_issues")):
            if (
                self._is_obvious_personalization_hallucination(issue)
                or self._contains_false_vegetarian_claim(issue, profile_context)
                or self._is_profile_noise_issue(issue, profile_context)
                or self._is_unsupported_preference_claim(issue, profile_context)
                or self._is_unsupported_sodium_issue(issue, nutrition_result)
                or self._is_analysis_artifact_issue(issue)
                or self._is_unsupported_diet_pattern_claim(issue, profile_context)
                or self._is_false_low_carb_allowed_food_claim(issue, profile_context)
                or self._contains_cjk_text(issue)
                or self._is_absent_restriction_precaution(issue, nutrition_result)
            ):
                removed_issue = True
                continue
            detected_issues.append(issue)
        if detected_issues:
            sanitized["detected_issues"] = detected_issues
        elif removed_issue:
            sanitized["detected_issues"] = ["Явных конфликтов с выбранным профилем не выявлено."]

        recommendations = [
            item
            for item in self._text_list(sanitized.get("recommendations"))
            if not self._is_obvious_personalization_hallucination(item)
            and not self._contains_false_vegetarian_claim(item, profile_context)
            and not self._is_unsupported_preference_claim(item, profile_context)
            and not self._is_unsupported_sodium_issue(item, nutrition_result)
            and not self._is_analysis_artifact_issue(item)
            and not self._is_unsupported_diet_pattern_claim(item, profile_context)
            and not self._is_false_low_carb_allowed_food_claim(item, profile_context)
            and not self._contains_cjk_text(item)
            and not self._is_absent_restriction_precaution(item, nutrition_result)
        ]
        if recommendations or removed_issue:
            sanitized["recommendations"] = recommendations

        assessment = dict(sanitized.get("profile_assessment") or {})
        for key, block_value in list(assessment.items()):
            if not isinstance(block_value, dict):
                continue
            block = dict(block_value)
            summary = normalize_spaces(str(block.get("summary") or ""))
            if self._is_false_non_plant_claim(summary):
                block["summary"] = "По распознанным ингредиентам явных конфликтов с растительным типом питания не найдено."
                block["status"] = "ok"
                block["compatibility"] = "high"
                removed_issue = True
            if self._contains_false_vegetarian_claim(summary, profile_context):
                block["summary"] = "По распознанным ингредиентам явных конфликтов с вегетарианским типом питания не найдено."
                block["status"] = "ok"
                block["compatibility"] = "high"
                removed_issue = True
            summary_has_sodium_noise = self._is_unsupported_sodium_issue(summary, nutrition_result)
            summary_has_absent_restriction = self._is_absent_restriction_precaution(summary, nutrition_result)
            block["evidence"] = [
                item
                for item in self._text_list(block.get("evidence"))
                if not self._is_obvious_personalization_hallucination(item)
                and not self._contains_false_vegetarian_claim(item, profile_context)
                and not self._is_unsupported_preference_claim(item, profile_context)
                and not self._is_unsupported_sodium_issue(item, nutrition_result)
                and not self._is_profile_noise_issue(item, profile_context)
                and not self._is_analysis_artifact_issue(item)
                and not self._is_unsupported_diet_pattern_claim(item, profile_context)
                and not self._is_false_low_carb_allowed_food_claim(item, profile_context)
                and not self._contains_cjk_text(item)
                and not self._is_absent_restriction_precaution(item, nutrition_result)
            ]
            block["recommendations"] = [
                item
                for item in self._text_list(block.get("recommendations"))
                if not self._is_obvious_personalization_hallucination(item)
                and not self._contains_false_vegetarian_claim(item, profile_context)
                and not self._is_unsupported_preference_claim(item, profile_context)
                and not self._is_unsupported_sodium_issue(item, nutrition_result)
                and not self._is_analysis_artifact_issue(item)
                and not self._is_unsupported_diet_pattern_claim(item, profile_context)
                and not self._is_false_low_carb_allowed_food_claim(item, profile_context)
                and not self._contains_cjk_text(item)
                and not self._is_absent_restriction_precaution(item, nutrition_result)
            ]
            if summary_has_sodium_noise and not block["evidence"]:
                block["summary"] = "По натрию явного превышения на рекомендованную порцию не видно."
                block["status"] = "ok"
                removed_issue = True
            elif summary_has_absent_restriction:
                block["summary"] = "Прямых конфликтов с указанными ограничениями по ингредиентам не найдено; учитывайте остальные нутриентные ограничения профиля."
                removed_issue = True
            if key != "goal_alignment" and block.get("status") == "warning" and not block["evidence"] and not block["recommendations"]:
                block["status"] = "ok"
            block["compatibility"] = self._compatibility_for_status(
                block.get("status"),
                str(block.get("compatibility") or "medium"),
            )
            assessment[key] = block
        sanitized["profile_assessment"] = assessment

        if removed_issue and strict_plant_profile and not self._detect_hard_profile_conflicts(nutrition_result):
            compatibility = dict(sanitized.get("compatibility") or {})
            if compatibility.get("diet") == "low":
                compatibility["diet"] = "high"
            sanitized["compatibility"] = compatibility

        if assessment:
            sanitized["compatibility"] = self._compatibility_from_assessment(
                sanitized.get("compatibility") or {},
                assessment,
            )

        return sanitized

    def _is_obvious_personalization_hallucination(self, text: str) -> bool:
        return self._is_false_non_plant_claim(text) or self._is_false_gluten_claim(text)

    def _is_profile_noise_issue(self, text: str, profile_context: dict[str, Any]) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        profile_values = [
            *profile_context.get("raw_preferences", []),
            *profile_context.get("raw_restrictions", []),
        ]
        for value in profile_values:
            for phrase in self._profile_noise_phrases(value):
                if phrase and phrase in normalized and len(normalized) <= max(len(phrase) + 40, 80):
                    return True
        if normalized.startswith(("profile ", "profile goal:", "в списке ограничений указано", "в профиле указано")):
            return True
        if normalized.startswith(("используется ", "используются ")) and "остр" not in normalized and len(normalized) <= 90:
            return True
        if "присутств" in normalized and not any(
            token in normalized
            for token in (
                "аллерг",
                "глютен",
                "лактоз",
                "молок",
                "свинин",
                "мяс",
                "рыб",
                "мореп",
                "яйц",
                "орех",
                "сахар",
                "натри",
                "сол",
            )
        ):
            return True
        if normalized.startswith(("не люблю ", "избегаю ", "без мяса", "без рыбы")) and len(normalized) <= 90:
            return True
        return False

    def _is_unsupported_sodium_issue(self, text: str, nutrition_result: dict[str, Any]) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        sodium_terms = ("натри", "сол", "sodium", "salt")
        if not any(term in normalized for term in sodium_terms):
            return False
        sodium_percent = self._metric_percent(nutrition_result.get("nutrition_per_serving") or {}, "sodium")
        if sodium_percent >= 50:
            return False
        problem_markers = (
            "высок",
            "много",
            "избыт",
            "превыш",
            "слишком",
            "значитель",
            "солен",
            "солён",
            "уменьш",
            "сниз",
            "огранич",
            "high",
            "exceed",
            "too much",
            "reduce",
            "limit",
        )
        if any(marker in normalized for marker in problem_markers):
            return True
        return sodium_percent <= 25 and any(marker in normalized for marker in ("%", "мг", "mg"))

    def _is_analysis_artifact_issue(self, text: str) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        return any(
            marker in normalized
            for marker in (
                "percent_of_target",
                "portion_guidance.",
                "portion_guidance:",
                "recommended_recipe_servings",
                "nutrition_signals",
                ".value:",
                "target:",
                "profile goal:",
            )
        )

    def _is_unsupported_diet_pattern_claim(self, text: str, profile_context: dict[str, Any]) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        markers = ("низкоуглевод", "low-carb", "low carb", "кето", "keto")
        if not any(marker in normalized for marker in markers):
            return False
        profile_text = normalize_text(
            " ".join(
                str(item)
                for item in [
                    profile_context.get("raw_diet_type") or "",
                    profile_context.get("raw_goal") or "",
                    *profile_context.get("raw_preferences", []),
                    *profile_context.get("raw_restrictions", []),
                ]
            )
        )
        return not any(marker in profile_text for marker in markers)

    def _is_false_low_carb_allowed_food_claim(self, text: str, profile_context: dict[str, Any]) -> bool:
        if profile_context.get("diet_code") != "low_carb":
            return False
        normalized = normalize_text(text)
        if "низкоуглевод" not in normalized and "low-carb" not in normalized and "low carb" not in normalized:
            return False
        if not any(marker in normalized for marker in ("противореч", "несовмест", "не соответств", "conflict", "incompatible")):
            return False
        allowed_markers = (
            "говядин",
            "мяс",
            "животн",
            "сливочное масло",
            "butter",
            "beef",
            "meat",
            "animal fat",
        )
        return any(marker in normalized for marker in allowed_markers)

    def _contains_cjk_text(self, text: str) -> bool:
        return bool(re.search(r"[\u3400-\u9fff]", str(text or "")))

    def _is_absent_restriction_precaution(self, text: str, nutrition_result: dict[str, Any]) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        if not any(marker in normalized for marker in ("не содержит", "отсутств", "убед", "списке огранич")):
            return False
        ingredient_text = normalize_text(" ".join(self._ingredient_names_from_result(nutrition_result)))
        restricted_groups = (
            ("мореп", "рыб", "кревет", "мид", "fish", "shrimp", "shellfish", "seafood"),
            ("молок", "сыр", "сметан", "сливоч", "творог", "йогурт", "milk", "cheese", "dairy"),
            ("яйц", "egg"),
            ("свинин", "pork"),
        )
        for tokens in restricted_groups:
            if any(token in normalized for token in tokens) and not any(token in ingredient_text for token in tokens):
                return True
        return False

    def _is_unsupported_preference_claim(self, text: str, profile_context: dict[str, Any]) -> bool:
        normalized = normalize_text(text)
        if not normalized or not any(marker in normalized for marker in ("не любит", "не переносит", "избегает")):
            return False
        profile_text = normalize_text(
            " ".join(
                str(item)
                for item in [
                    *profile_context.get("raw_preferences", []),
                    *profile_context.get("raw_restrictions", []),
                ]
            )
        )
        if not profile_text:
            return True
        claim_tokens = self._preference_claim_tokens(normalized)
        profile_tokens = self._preference_claim_tokens(profile_text)
        return bool(claim_tokens) and not self._has_related_preference_token(claim_tokens, profile_tokens)

    def _preference_claim_tokens(self, text: str) -> set[str]:
        ignored = {
            "рецепт",
            "блюдо",
            "содержит",
            "пользователь",
            "который",
            "которая",
            "которые",
            "любит",
            "люблю",
            "избегает",
            "избегаю",
            "переносит",
        }
        return {token for token in re.split(r"[^a-zа-я0-9]+", normalize_text(text)) if len(token) >= 4 and token not in ignored}

    def _has_related_preference_token(self, left: set[str], right: set[str]) -> bool:
        for left_token in left:
            for right_token in right:
                if left_token == right_token or left_token in right_token or right_token in left_token:
                    return True
                if left_token[:4] == right_token[:4]:
                    return True
        return False

    def _profile_noise_phrases(self, value: Any) -> list[str]:
        text = normalize_text(value)
        if not text:
            return []
        phrases = [text]
        phrases.extend(part.strip() for part in re.split(r"[.;\n]+", text) if part.strip())
        return dedupe_texts(phrases)

    def _is_false_non_plant_claim(self, text: str) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        markers = [
            "не является растительной едой",
            "не являются растительной едой",
            "не является растительным продуктом",
            "не являются растительными продуктами",
            "не является растительной пищей",
            "не являются растительной пищей",
            "not plant",
            "not vegan",
            "\u043d\u0435 \u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0440\u0430\u0441\u0442\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u043c \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u043e\u043c",
            "\u043d\u0435 \u044f\u0432\u043b\u044f\u044e\u0442\u0441\u044f \u0440\u0430\u0441\u0442\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u043c\u0438 \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u0430\u043c\u0438",
            "\u044f\u0432\u043b\u044f\u044e\u0442\u0441\u044f \u0436\u0438\u0432\u043e\u0442\u043d\u044b\u043c\u0438 \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u0430\u043c\u0438",
            "\u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0436\u0438\u0432\u043e\u0442\u043d\u044b\u043c \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u043e\u043c",
            "\u0441\u043e\u0434\u0435\u0440\u0436\u0430\u0442 \u0436\u0438\u0432\u043e\u0442\u043d\u044b\u0435 \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u044b",
            "\u0436\u0438\u0432\u043e\u0442\u043d\u044b\u0435 \u0436\u0438\u0440\u044b",
            "\u043d\u0435\u0441\u043e\u0432\u043c\u0435\u0441\u0442\u0438\u043c\u043e \u0441 \u0432\u0435\u0433\u0430\u043d\u0441\u043a\u0438\u043c \u043f\u0438\u0442\u0430\u043d\u0438\u0435\u043c",
            "\u043d\u0435\u0441\u043e\u0432\u043c\u0435\u0441\u0442\u0438\u043c\u044b \u0441 \u0432\u0435\u0433\u0430\u043d\u0441\u043a\u0438\u043c \u043f\u0438\u0442\u0430\u043d\u0438\u0435\u043c",
            "\u043f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0438\u0442 \u0432\u0435\u0433\u0430\u043d",
            "\u043f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0430\u0442 \u0432\u0435\u0433\u0430\u043d",
            "\u043f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0438\u0442 \u0440\u0430\u0441\u0442\u0438\u0442\u0435\u043b",
            "\u043d\u0435 \u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0436\u0438\u0432\u043e\u0442\u043d\u044b\u043c \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u043e\u043c",
            "\u043d\u0435 \u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0436\u0438\u0432\u043e\u0442\u043d\u044b\u043c\u0438 \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u0430\u043c\u0438",
            "\u043d\u0435 \u044f\u0432\u043b\u044f\u044e\u0442\u0441\u044f \u0436\u0438\u0432\u043e\u0442\u043d\u044b\u043c\u0438 \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u0430\u043c\u0438",
        ]
        if not any(marker in normalized for marker in markers):
            return False
        plant_tokens = {
            "лук",
            "onion",
            "помидор",
            "томат",
            "tomato",
            "соль",
            "salt",
            "перец",
            "pepper",
            "чеснок",
            "garlic",
            "вода",
            "water",
            "растительное масло",
            "vegetable oil",
            "оливковое масло",
            "olive oil",
            "картофель",
            "potato",
            "капуста",
            "cabbage",
            "морковь",
            "carrot",
            "огур",
            "cucumber",
            "зелень",
            "петруш",
            "parsley",
            "укроп",
            "dill",
            "базилик",
            "basil",
            "баклаж",
            "eggplant",
            "\u043e\u0440\u0435\u0445",
            "\u0433\u0440\u0435\u0446",
            "walnut",
            "nut",
            "\u0441\u0443\u0445\u0430\u0440",
            "breadcrumbs",
            "пшено",
            "millet",
            "сахар",
            "sugar",
            "уксус",
            "vinegar",
        }
        return any(token in normalized for token in plant_tokens)

    def _is_false_gluten_claim(self, text: str) -> bool:
        normalized = normalize_text(text)
        if self._is_false_millet_wheat_claim(normalized):
            return True
        if "\u0433\u043b\u044e\u0442\u0435\u043d" not in normalized and "gluten" not in normalized:
            return False
        real_gluten_tokens = (
            "\u043f\u0448\u0435\u043d\u0438\u0447",
            "\u043c\u0443\u043a",
            "\u0445\u043b\u0435\u0431",
            "\u0441\u0443\u0445\u0430\u0440",
            "\u0431\u0430\u0433\u0435\u0442",
            "\u0431\u0430\u0442\u043e\u043d",
            "\u0431\u0443\u043b\u043a",
            "\u043b\u0430\u0432\u0430\u0448",
            "wheat",
            "flour",
            "bread",
            "breadcrumbs",
            "baguette",
            "bun",
        )
        if any(token in normalized for token in real_gluten_tokens):
            return False
        false_gluten_tokens = (
            "\u043e\u0440\u0435\u0445",
            "\u0433\u0440\u0435\u0446",
            "\u0441\u043e\u043b\u044c",
            "\u0447\u0435\u0441\u043d\u043e\u043a",
            "\u043b\u0438\u043c\u043e\u043d",
            "\u0437\u0438\u0440",
            "\u043f\u0435\u0440\u0435\u0446",
            "\u0431\u0430\u043a\u043b\u0430\u0436",
            "walnut",
            "salt",
            "garlic",
            "lemon",
            "cumin",
            "pepper",
            "eggplant",
            "\u043f\u0448\u0435\u043d\u043e",
            "\u043f\u0448\u0435\u043d\u043e\u043c",
            "millet",
        )
        return any(token in normalized for token in false_gluten_tokens)

    def _is_false_millet_wheat_claim(self, normalized: str) -> bool:
        if "\u043f\u0448\u0435\u043d\u043e" not in normalized and "\u043f\u0448\u0435\u043d\u043e\u043c" not in normalized and "millet" not in normalized:
            return False
        false_markers = (
            "\u043f\u0448\u0435\u043d\u0438\u0447",
            "\u043f\u0448\u0435\u043d\u0438\u0446",
            "\u043c\u0443\u043a",
            "\u0433\u043b\u044e\u0442\u0435\u043d",
            "wheat",
            "flour",
            "gluten",
        )
        return any(marker in normalized for marker in false_markers)

    def _profile_conflict_specs(self, profile_context: dict[str, Any]) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        diet_code = profile_context.get("diet_code")
        allergy_codes = set(profile_context.get("allergy_codes") or [])
        restriction_food_codes = set(profile_context.get("restriction_food_codes") or [])
        preference_codes = set(profile_context.get("preference_codes") or [])

        if diet_code == "vegan":
            specs.append(
                self._conflict_spec(
                    "Веганский тип питания",
                    ["мяс", "свинин", "ветчин", "говядин", "куриц", "рыб", "кревет", "морепродукт", "яйц", "молок", "сыр", "сметан", "сливочн", "сливк", "мед", "pork", "ham", "beef", "chicken", "fish", "shrimp", "shellfish", "egg", "milk", "cheese", "butter", "cream", "honey"],
                    "Заменить животные продукты растительными альтернативами: бобовыми, тофу, растительным молоком и безглютеновыми крупами при необходимости.",
                    "diet",
                    "additional_restrictions",
                    "Тип питания и ограничения",
                )
            )
        if diet_code == "vegetarian":
            specs.append(
                self._conflict_spec(
                    "Вегетарианский тип питания",
                    ["мяс", "свинин", "ветчин", "говядин", "куриц", "рыб", "кревет", "морепродукт", "pork", "ham", "beef", "chicken", "fish", "shrimp", "shellfish"],
                    "Заменить мясо или рыбу на растительный белок, грибы, бобовые, яйца или молочные продукты, если они допустимы профилем.",
                    "diet",
                    "additional_restrictions",
                    "Тип питания и ограничения",
                )
            )
        if "dairy" in allergy_codes:
            specs.append(
                self._conflict_spec(
                    "Аллергия или непереносимость молочных продуктов",
                    ["молок", "сыр", "сметан", "сливочн", "сливк", "творог", "йогурт", "milk", "cheese", "sour cream", "butter", "cream", "yogurt"],
                    "Исключить молочные ингредиенты или заменить их безлактозными/растительными аналогами с проверенным составом.",
                    "restriction",
                    "allergy_issues",
                    "Аллергии",
                )
            )
        if "gluten" in allergy_codes:
            specs.append(
                self._conflict_spec(
                    "Аллергия или ограничение по глютену",
                    ["пшенич", "мука", "хлеб", "сухар", "макарон", "паста", "багет", "батон", "булк", "лаваш", "wheat", "flour", "bread", "breadcrumbs", "pasta", "baguette", "bun"],
                    "Заменить пшеничные продукты на безглютеновые аналоги и проверить панировку/хлеб на маркировку gluten-free.",
                    "restriction",
                    "allergy_issues",
                    "Аллергии",
                )
            )
        if "eggs" in allergy_codes:
            specs.append(self._conflict_spec("Аллергия на яйца", ["яйц", "egg"], "Исключить яйца или использовать подходящий заменитель.", "restriction", "allergy_issues", "Аллергии"))
        if "fish" in allergy_codes or "shellfish" in allergy_codes:
            specs.append(self._conflict_spec("Аллергия на рыбу или морепродукты", ["рыб", "скумбр", "кревет", "мид", "fish", "mackerel", "shrimp", "shellfish"], "Исключить рыбу и морепродукты, избегая также скрытых источников.", "restriction", "allergy_issues", "Аллергии"))
        if "nuts" in allergy_codes or "peanuts" in allergy_codes:
            specs.append(self._conflict_spec("Аллергия на орехи", ["орех", "грец", "арахис", "nut", "peanut"], "Исключить орехи и проверить возможные следы в продуктах.", "restriction", "allergy_issues", "Аллергии"))
        restriction_only_codes = restriction_food_codes - allergy_codes
        if "dairy" in restriction_only_codes:
            specs.append(self._conflict_spec("Ограничение молочных продуктов", ["молок", "сыр", "сметан", "сливочн", "сливк", "творог", "йогурт", "milk", "cheese", "sour cream", "butter", "cream", "yogurt"], "Исключить молочные ингредиенты или заменить их безлактозными/растительными аналогами.", "restriction", "additional_restrictions", "Тип питания и ограничения"))
        if "gluten" in restriction_only_codes:
            specs.append(self._conflict_spec("Ограничение по глютену", ["пшенич", "мука", "хлеб", "сухар", "макарон", "паста", "багет", "батон", "булк", "лаваш", "wheat", "flour", "bread", "breadcrumbs", "pasta", "baguette", "bun"], "Заменить пшеничные продукты на безглютеновые аналоги.", "restriction", "additional_restrictions", "Тип питания и ограничения"))
        if "eggs" in restriction_only_codes:
            specs.append(self._conflict_spec("Ограничение яиц", ["яйц", "egg"], "Исключить яйца или использовать подходящий заменитель.", "restriction", "additional_restrictions", "Тип питания и ограничения"))
        if restriction_only_codes & {"fish", "shellfish"}:
            specs.append(self._conflict_spec("Ограничение рыбы или морепродуктов", ["рыб", "скумбр", "кревет", "мид", "fish", "mackerel", "shrimp", "shellfish"], "Исключить рыбу и морепродукты, избегая также скрытых источников.", "restriction", "additional_restrictions", "Тип питания и ограничения"))
        if "avoid_pork" in preference_codes:
            specs.append(self._conflict_spec("Предпочтение без свинины", ["свинин", "pork"], "Заменить свинину на допустимый для профиля источник белка.", "restriction", "preference_alignment", "Предпочтения"))
        return specs

    def _conflict_spec(
        self,
        label: str,
        tokens: list[str],
        recommendation: str,
        compatibility_key: str,
        assessment_key: str,
        assessment_title: str,
    ) -> dict[str, Any]:
        return {
            "label": label,
            "tokens": tokens,
            "recommendation": recommendation,
            "compatibility_key": compatibility_key,
            "assessment_key": assessment_key,
            "assessment_title": assessment_title,
        }

    def _matching_ingredient_names(
        self,
        ingredient_context: list[dict[str, Any]],
        tokens: list[str],
        exclude: list[str],
    ) -> list[str]:
        matches: list[str] = []
        for item in ingredient_context:
            text = normalize_text(
                " ".join(
                    str(item.get(key) or "")
                    for key in ("name_raw", "name_canonical", "name_en", "matched_name", "matched_category")
                )
            )
            if not text or self._has_excluded_token(text, exclude):
                continue
            if any(self._token_matches(text, token) for token in tokens):
                matches.append(str(item.get("name_raw") or item.get("name_canonical") or item.get("matched_name") or "").strip())
        return dedupe_texts(matches)

    def _token_matches(self, text: str, token: str) -> bool:
        normalized_token = normalize_text(token)
        if not normalized_token:
            return False
        if normalized_token in {"паста", "pasta"} and any(marker in text for marker in ("томат", "tomato")):
            return False
        if " " in normalized_token:
            return normalized_token in text
        words = set(text.split())
        if normalized_token in words:
            return True
        if normalized_token.isascii():
            return False
        if normalized_token in {"пшен", "РїС€РµРЅ"}:
            return False
        return len(normalized_token) >= 5 and any(word.startswith(normalized_token) for word in words)

    def _has_excluded_token(self, text: str, exclude: list[str]) -> bool:
        return any(self._token_matches(text, token) for token in exclude)

    def _build_ingredient_context(
        self,
        matched_ingredients: list[dict[str, Any]],
        nutrition_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        details_by_name = {
            item["ingredient"]["name_canonical"]: item
            for item in nutrition_result.get("detailed_ingredients", [])
            if isinstance(item, dict) and isinstance(item.get("ingredient"), dict)
        }
        context: list[dict[str, Any]] = []
        for match in matched_ingredients:
            ingredient = match.get("ingredient") or {}
            detailed = details_by_name.get(ingredient.get("name_canonical"), {})
            matched_product = match.get("matched_product") or {}
            nutrients = detailed.get("nutrients") or {}
            context.append(
                {
                    "name_raw": ingredient.get("name_raw"),
                    "name_canonical": ingredient.get("name_canonical"),
                    "name_en": ingredient.get("name_en"),
                    "matched_name": match.get("matched_name") or matched_product.get("display_name_en") or matched_product.get("display_name_ru"),
                    "matched_category": matched_product.get("category"),
                    "match_confidence": match.get("match_confidence"),
                    "estimated_grams": detailed.get("estimated_grams"),
                    "nutrition_resolution_status": detailed.get("nutrition_resolution_status"),
                    "calories": (nutrients.get("calories") if isinstance(nutrients, dict) else None),
                    "protein": (nutrients.get("protein") if isinstance(nutrients, dict) else None),
                    "fat": (nutrients.get("fat") if isinstance(nutrients, dict) else None),
                    "carbs": (nutrients.get("carbs") if isinstance(nutrients, dict) else None),
                    "sodium": (nutrients.get("sodium") if isinstance(nutrients, dict) else None),
                }
            )
        return context

    def _build_nutrition_signals(self, nutrition_result: dict[str, Any]) -> list[dict[str, Any]]:
        signals = self._build_base_nutrition_signals(nutrition_result)
        portion_guidance = nutrition_result.get("portion_guidance") or {}

        if portion_guidance.get("recommended_recipe_servings", 1) <= 1:
            signals.append({"code": "whole_recipe_portion", "label": "Сейчас одна порция трактуется как весь рецепт."})

        return signals

    def _build_base_nutrition_signals(self, nutrition_result: dict[str, Any]) -> list[dict[str, Any]]:
        per_serving = nutrition_result.get("nutrition_per_serving", {})
        portion_guidance = nutrition_result.get("portion_guidance") or {}
        target_recipe_calories = portion_guidance.get("target_recipe_calories")
        calories_value = float(per_serving.get("calories", {}).get("value", 0) or 0)
        calories_percent = float(per_serving.get("calories", {}).get("percent_of_target", 0) or 0)
        fat_percent = float(per_serving.get("fat", {}).get("percent_of_target", 0) or 0)
        sodium_percent = float(per_serving.get("sodium", {}).get("percent_of_target", 0) or 0)
        signals: list[dict[str, Any]] = []
        if fat_percent >= 45:
            signals.append({"code": "high_fat", "label": "Высокая доля жиров на рекомендованную порцию."})
        if sodium_percent >= 80:
            signals.append({"code": "high_sodium", "label": "Высокий натрий на рекомендованную порцию."})
        if target_recipe_calories and calories_value > float(target_recipe_calories):
            signals.append({"code": "target_calories_exceeded", "label": "Калорийность одной рекомендованной порции выше целевого значения."})
        elif calories_percent >= 45:
            signals.append({"code": "high_calories", "label": "Высокая калорийность на рекомендованную порцию."})
        return signals

    def _fallback_response(
        self,
        recipe: StructuredRecipe,
        nutrition_result: dict[str, Any],
        rag_context: list[dict[str, Any]],
        nutrition_signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        portion_guidance = nutrition_result.get("portion_guidance") or {}
        warnings = list(nutrition_result.get("warnings", []))

        if nutrition_result.get("unresolved_ingredients"):
            warnings.append(
                "Не удалось надёжно определить нутриенты для: "
                + ", ".join(nutrition_result["unresolved_ingredients"][:5])
                + "."
            )
        if not rag_context:
            warnings.append("RAG-контекст не найден, анализ сформирован по упрощённому резервному сценарию.")

        issues = [item["label"] for item in nutrition_signals]
        if not issues:
            issues = ["Явных конфликтов с выбранным профилем не выявлено."]

        summary_parts = [f"Рецепт «{recipe.title}» проанализирован для выбранного профиля."]
        if portion_guidance.get("summary"):
            summary_parts.append(str(portion_guidance["summary"]))
        if issues:
            summary_parts.append("Ключевые моменты: " + "; ".join(issues[:2]))

        recommendations = []
        if portion_guidance.get("recommended_recipe_servings", 1) > 1:
            recommendations.append(
                f"Разделить рецепт примерно на {format_portions(int(portion_guidance['recommended_recipe_servings']))}."
            )
        if any(item["code"] in {"high_fat", "high_calories", "target_calories_exceeded"} for item in nutrition_signals):
            recommendations.append("Скорректировать наиболее калорийные и жирные ингредиенты или увеличить число порций.")
        if not recommendations:
            recommendations.append("Повторить анализ при доступном RAG/LLM-контексте для полноценной персонализации.")

        has_goal_issue = any(item["code"] in {"high_fat", "high_sodium", "high_calories", "target_calories_exceeded"} for item in nutrition_signals)
        compatibility = {
            "diet": "medium",
            "restriction": "medium",
            "goal": "medium" if has_goal_issue else "high",
        }

        return {
            "summary": normalize_spaces(" ".join(summary_parts)),
            "detected_issues": dedupe_texts(issues),
            "recommendations": dedupe_texts(recommendations),
            "warnings": dedupe_texts(warnings),
            "compatibility": compatibility,
            "profile_assessment": self._fallback_profile_assessment(nutrition_result, issues, recommendations),
        }

    def _fallback_profile_assessment(
        self, nutrition_result: dict[str, Any], issues: list[str], recommendations: list[str]
    ) -> dict[str, dict[str, Any]]:
        profile_context = nutrition_result.get("profile_context") or {}
        nutrition = nutrition_result.get("nutrition_per_serving") or {}
        ingredient_names = self._ingredient_names_from_result(nutrition_result)
        evidence = [item for item in issues if "Явных конфликтов" not in item]
        neutral_recommendations = [item for item in recommendations if "Повторить анализ" not in item]
        return {
            "goal_alignment": self._fallback_block(
                "goal_alignment",
                "Соответствие цели",
                self._goal_fallback_summary(profile_context, nutrition, evidence),
                evidence,
                neutral_recommendations,
            ),
            "allergy_issues": self._fallback_block(
                "allergy_issues",
                "Аллергии",
                self._allergy_fallback_summary(profile_context, ingredient_names),
                [],
                [],
            ),
            "disease_issues": self._fallback_block(
                "disease_issues",
                "Заболевания",
                self._disease_fallback_summary(profile_context),
                [],
                [],
            ),
            "preference_alignment": self._fallback_block(
                "preference_alignment",
                "Предпочтения",
                self._preference_fallback_summary(profile_context, ingredient_names),
                [],
                [],
            ),
            "additional_restrictions": self._fallback_block(
                "additional_restrictions",
                "Тип питания и ограничения",
                self._diet_fallback_summary(profile_context, ingredient_names, evidence),
                evidence if self._diet_needs_nutrition_evidence(profile_context) else [],
                neutral_recommendations if self._diet_needs_nutrition_evidence(profile_context) else [],
            ),
        }

    def _fallback_block(
        self, key: str, title: str, summary: str, evidence: list[str], recommendations: list[str]
    ) -> dict[str, Any]:
        status = "warning" if evidence else "ok"
        compatibility = "medium" if evidence else "high"
        return {
            "key": key,
            "title": title,
            "status": status,
            "compatibility": compatibility,
            "summary": normalize_spaces(summary),
            "evidence": dedupe_texts(evidence),
            "recommendations": dedupe_texts(recommendations),
        }

    def _goal_fallback_summary(
        self,
        profile_context: dict[str, Any],
        nutrition: dict[str, Any],
        evidence: list[str],
    ) -> str:
        goal = profile_context.get("raw_goal") or "цель профиля"
        calories = self._metric_value(nutrition, "calories")
        protein = self._metric_value(nutrition, "protein")
        if evidence:
            return (
                f"Для цели «{goal}» рецепт в целом можно использовать, но порцию стоит контролировать: "
                f"на рекомендованную порцию приходится около {calories} ккал и {protein} г белка. "
                "Основные нюансы указаны ниже."
            )
        return f"Для цели «{goal}» явных нутриентных конфликтов не видно: порция выглядит умеренной по ключевым показателям."

    def _allergy_fallback_summary(self, profile_context: dict[str, Any], ingredient_names: list[str]) -> str:
        allergies = profile_context.get("raw_allergies") or []
        if not allergies:
            return "В профиле не указаны аллергии, поэтому специальных аллергенных конфликтов не найдено."
        allergies_text = self._compact_list([str(item) for item in allergies], limit=4)
        ingredients_text = self._compact_list(ingredient_names, limit=6)
        return (
            f"В профиле указаны аллергии/непереносимости: {allergies_text}. "
            f"Среди распознанных ингредиентов ({ingredients_text}) прямого совпадения с этими аллергенами не найдено."
        )

    def _disease_fallback_summary(self, profile_context: dict[str, Any]) -> str:
        diseases = profile_context.get("raw_diseases") or []
        if not diseases:
            return "Заболевания в профиле не указаны, поэтому отдельные медицинские ограничения не применялись."
        diseases_text = self._compact_list([str(item) for item in diseases], limit=4)
        return f"В профиле указаны заболевания/состояния: {diseases_text}. Явного прямого конфликта по ингредиентам не найдено."

    def _preference_fallback_summary(self, profile_context: dict[str, Any], ingredient_names: list[str]) -> str:
        preferences = profile_context.get("raw_preferences") or []
        if not preferences:
            return "Пищевые предпочтения в профиле не указаны, дополнительных корректировок по этому блоку нет."
        preferences_text = self._compact_list([str(item) for item in preferences], limit=4)
        ingredient_text = normalize_text(" ".join(ingredient_names))
        if any(token in ingredient_text for token in ("фасол", "греч", "bean", "buckwheat")):
            return f"Предпочтения профиля: {preferences_text}. Рецепт выглядит сытным за счет фасоли/гречки и в целом соответствует этому ожиданию."
        return f"Предпочтения профиля: {preferences_text}. Явного противоречия с составом рецепта не найдено."

    def _diet_fallback_summary(
        self,
        profile_context: dict[str, Any],
        ingredient_names: list[str],
        evidence: list[str],
    ) -> str:
        diet = profile_context.get("raw_diet_type") or "тип питания"
        diet_code = profile_context.get("diet_code")
        ingredients_text = self._compact_list(ingredient_names, limit=7)
        if diet_code in {"vegan", "vegetarian"}:
            return (
                f"Для типа питания «{diet}» прямых конфликтов по составу не видно: "
                f"основные ингредиенты ({ingredients_text}) не относятся к мясу или рыбе."
            )
        if evidence:
            return f"Для типа питания «{diet}» специфических запретов не найдено, но есть нутриентные нюансы по порции."
        return f"Для типа питания «{diet}» явных ограничительных конфликтов по ингредиентам не найдено."

    def _diet_needs_nutrition_evidence(self, profile_context: dict[str, Any]) -> bool:
        return profile_context.get("diet_code") not in {"vegan", "vegetarian"}

    def _ingredient_names_from_result(self, nutrition_result: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for detail in nutrition_result.get("detailed_ingredients") or []:
            if not isinstance(detail, dict):
                continue
            ingredient = detail.get("ingredient") or {}
            if isinstance(ingredient, dict):
                names.append(str(ingredient.get("name_raw") or ingredient.get("name_canonical") or "").strip())
        return dedupe_texts([name for name in names if name])

    def _metric_value(self, nutrition: dict[str, Any], key: str) -> float:
        return round(float(((nutrition.get(key) or {}).get("value") or 0)), 2)

    def _metric_percent(self, nutrition: dict[str, Any], key: str) -> float:
        return round(float(((nutrition.get(key) or {}).get("percent_of_target") or 0)), 2)

    def _compact_list(self, values: list[str], limit: int = 3) -> str:
        cleaned = dedupe_texts([normalize_spaces(str(value)) for value in values if normalize_spaces(str(value))])
        if len(cleaned) <= limit:
            return "; ".join(cleaned)
        return "; ".join(cleaned[:limit]) + f"; ещё {len(cleaned) - limit}"

    def _profile_summary(self, profile_context: dict[str, Any]) -> str:
        items = dedupe_texts(profile_context.get("profile_items") or [])
        return self._compact_list(items, limit=5) if items else "профиль не указан"


rag_service = RagService()
