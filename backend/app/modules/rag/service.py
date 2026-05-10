from __future__ import annotations

from typing import Any

from app.core.utils import dedupe_texts, format_portions, normalize_spaces, normalize_text
from app.modules.rag.retrieval import retrieval_service
from app.modules.structuring.schemas import StructuredRecipe
from app.services.ollama_service import ollama_service


class RagService:
    def retrieve_context(
        self,
        recipe_text: str,
        recipe: StructuredRecipe,
        matched_ingredients: list[dict[str, Any]],
        nutrition_result: dict[str, Any],
        profile: dict[str, Any],
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

        signal_queries = [item["label"] for item in self._build_nutrition_signals(nutrition_result, profile)]
        if (nutrition_result.get("portion_guidance") or {}).get("recommended_recipe_servings", 1) > 1:
            signal_queries.append("portion size rules")

        queries = [
            *dedupe_texts(profile_queries)[:18],
            *dedupe_texts(ingredient_queries)[:14],
            *dedupe_texts(signal_queries)[:4],
        ]
        return retrieval_service.search(dedupe_texts(queries), top_k=10)

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
        nutrition_signals = self._build_nutrition_signals(nutrition_result, profile)

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
        if normalized in {"low", "medium", "high"}:
            return normalized
        if "низ" in normalized or "low" in normalized or status == "conflict":
            return "low"
        if "сред" in normalized or "medium" in normalized or status == "warning":
            return "medium"
        if "выс" in normalized or "high" in normalized or status == "ok":
            return "high"
        return fallback if fallback in {"low", "medium", "high"} else "medium"

    def _compatibility_from_assessment(
        self,
        fallback: dict[str, str],
        assessment: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        result = dict(fallback)
        goal_level = assessment.get("goal_alignment", {}).get("compatibility")
        diet_level = assessment.get("additional_restrictions", {}).get("compatibility")
        if goal_level in {"low", "medium", "high"}:
            result["goal"] = goal_level
        if diet_level in {"low", "medium", "high"}:
            result["diet"] = diet_level

        restriction_levels = [
            str(assessment.get(key, {}).get("compatibility"))
            for key in ("allergy_issues", "disease_issues", "preference_alignment", "additional_restrictions")
        ]
        if "low" in restriction_levels:
            result["restriction"] = "low"
        elif "medium" in restriction_levels:
            result["restriction"] = "medium"
        elif restriction_levels:
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
        conflicts = self._detect_hard_profile_conflicts(nutrition_result)
        if not conflicts:
            return result

        guarded = dict(result)
        existing_issues = [
            item
            for item in self._text_list(guarded.get("detected_issues"))
            if "явных конфликтов" not in normalize_text(item)
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
        if profile_context.get("diet_code") not in {"vegan", "vegetarian"}:
            return result

        sanitized = dict(result)
        removed_issue = False
        if self._is_false_non_plant_claim(normalize_spaces(str(sanitized.get("summary") or ""))):
            sanitized["summary"] = "По распознанным ингредиентам явных конфликтов с растительным типом питания не найдено."
            removed_issue = True

        detected_issues: list[str] = []
        for issue in self._text_list(sanitized.get("detected_issues")):
            if self._is_false_non_plant_claim(issue):
                removed_issue = True
                continue
            detected_issues.append(issue)
        if detected_issues:
            sanitized["detected_issues"] = detected_issues
        elif removed_issue:
            sanitized["detected_issues"] = ["Явных конфликтов с выбранным типом питания по растительным ингредиентам не выявлено."]

        recommendations = [
            item
            for item in self._text_list(sanitized.get("recommendations"))
            if not self._is_false_non_plant_claim(item)
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
            block["evidence"] = [
                item for item in self._text_list(block.get("evidence")) if not self._is_false_non_plant_claim(item)
            ]
            block["recommendations"] = [
                item
                for item in self._text_list(block.get("recommendations"))
                if not self._is_false_non_plant_claim(item)
            ]
            assessment[key] = block
        sanitized["profile_assessment"] = assessment

        if removed_issue and not self._detect_hard_profile_conflicts(nutrition_result):
            compatibility = dict(sanitized.get("compatibility") or {})
            if compatibility.get("diet") == "low":
                compatibility["diet"] = "high"
            sanitized["compatibility"] = compatibility

        return sanitized

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
            "пшено",
            "millet",
            "сахар",
            "sugar",
            "уксус",
            "vinegar",
        }
        return any(token in normalized for token in plant_tokens)

    def _profile_conflict_specs(self, profile_context: dict[str, Any]) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        diet_code = profile_context.get("diet_code")
        allergy_codes = set(profile_context.get("allergy_codes") or [])
        preference_codes = set(profile_context.get("preference_codes") or [])

        if diet_code == "vegan":
            specs.append(
                self._conflict_spec(
                    "Веганский тип питания",
                    ["мяс", "свинин", "говядин", "куриц", "рыб", "яйц", "молок", "сыр", "сметан", "сливочн", "мед", "pork", "beef", "chicken", "fish", "egg", "milk", "cheese", "butter", "honey"],
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
                    ["мяс", "свинин", "говядин", "куриц", "рыб", "pork", "beef", "chicken", "fish"],
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
                    ["молок", "сыр", "сметан", "сливочн", "творог", "йогурт", "milk", "cheese", "sour cream", "butter", "yogurt"],
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
                    ["пшен", "мука", "хлеб", "сухар", "wheat", "flour", "bread", "breadcrumbs"],
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
        if " " in normalized_token:
            return normalized_token in text
        words = set(text.split())
        if normalized_token in words:
            return True
        if normalized_token.isascii():
            return False
        if normalized_token == "пшен":
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

    def _build_nutrition_signals(self, nutrition_result: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
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

    def _compact_list(self, values: list[str], limit: int = 3) -> str:
        cleaned = dedupe_texts([normalize_spaces(str(value)) for value in values if normalize_spaces(str(value))])
        if len(cleaned) <= limit:
            return "; ".join(cleaned)
        return "; ".join(cleaned[:limit]) + f"; ещё {len(cleaned) - limit}"

    def _profile_summary(self, profile_context: dict[str, Any]) -> str:
        items = dedupe_texts(profile_context.get("profile_items") or [])
        return self._compact_list(items, limit=5) if items else "профиль не указан"


rag_service = RagService()
