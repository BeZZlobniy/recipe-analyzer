from __future__ import annotations

from typing import Any

from app.core.utils import dedupe_texts, load_data_json, normalize_text


_ALIASES = load_data_json("fallback/personalization_aliases.json")

DIET_ALIASES = dict(_ALIASES.get("diet_aliases", {}))
GOAL_ALIASES = dict(_ALIASES.get("goal_aliases", {}))
RAG_QUERY_TERMS = dict(_ALIASES.get("rag_query_terms", {}))
ALLERGY_ALIASES = dict(_ALIASES.get("allergy_aliases", {}))
DISEASE_ALIASES = dict(_ALIASES.get("disease_aliases", {}))
PREFERENCE_ALIASES = dict(_ALIASES.get("preference_aliases", {}))
PROFILE_QUERY_TEMPLATES = dict(_ALIASES.get("profile_query_templates", {}))


class PersonalizationService:
    def build_profile_context(self, profile: dict[str, Any]) -> dict[str, Any]:
        raw_allergies = self._list_values(profile.get("allergies_json"))
        raw_diseases = self._list_values(profile.get("diseases_json"))
        raw_preferences = self._list_values(profile.get("preferences_json"))
        raw_restrictions = self._list_values(profile.get("restrictions_text"))
        target_recipe_calories = self._coerce_positive_number(profile.get("target_recipe_calories"))

        diet_code = self._first_alias([profile.get("diet_type")], DIET_ALIASES)
        goal_code = self._first_alias([profile.get("goal")], GOAL_ALIASES)
        allergy_codes = sorted(self._collect_aliases(raw_allergies + raw_restrictions, ALLERGY_ALIASES))
        disease_codes = sorted(self._collect_aliases(raw_diseases + raw_restrictions, DISEASE_ALIASES))
        preference_codes = sorted(self._collect_aliases(raw_preferences + raw_restrictions, PREFERENCE_ALIASES))
        profile_constraints = self._build_profile_constraints(
            diet_type=profile.get("diet_type"),
            goal=profile.get("goal"),
            allergies=raw_allergies,
            diseases=raw_diseases,
            preferences=raw_preferences,
            restrictions=raw_restrictions,
            target_recipe_calories=target_recipe_calories,
        )

        rag_queries = self._build_rag_queries(
            diet_code=diet_code,
            goal_code=goal_code,
            allergy_codes=allergy_codes,
            disease_codes=disease_codes,
            preference_codes=preference_codes,
            profile_constraints=profile_constraints,
            target_recipe_calories=target_recipe_calories,
        )

        profile_items = dedupe_texts(
            [
                profile.get("diet_type"),
                profile.get("goal"),
                *raw_allergies,
                *raw_diseases,
                *raw_preferences,
                *raw_restrictions,
                f"целевые калории {int(target_recipe_calories)}" if target_recipe_calories else None,
            ]
        )

        return {
            "diet_code": diet_code,
            "goal_code": goal_code,
            "raw_diet_type": profile.get("diet_type"),
            "raw_goal": profile.get("goal"),
            "allergy_codes": allergy_codes,
            "disease_codes": disease_codes,
            "preference_codes": preference_codes,
            "target_recipe_calories": target_recipe_calories,
            "profile_constraints": profile_constraints,
            "rag_queries": rag_queries,
            "profile_items": profile_items,
            "raw_allergies": raw_allergies,
            "raw_diseases": raw_diseases,
            "raw_preferences": raw_preferences,
            "raw_restrictions": raw_restrictions,
        }

    def _build_rag_queries(
        self,
        *,
        diet_code: str | None,
        goal_code: str | None,
        allergy_codes: list[str],
        disease_codes: list[str],
        preference_codes: list[str],
        profile_constraints: list[dict[str, str]],
        target_recipe_calories: float | None,
    ) -> list[str]:
        queries: list[str] = []
        for code in [diet_code, goal_code, *allergy_codes, *disease_codes, *preference_codes]:
            if code and code in RAG_QUERY_TERMS:
                queries.append(RAG_QUERY_TERMS[code])
        queries.extend(self._constraint_queries(profile_constraints))
        if target_recipe_calories:
            queries.extend(["portion size rules", "nutrition thresholds"])
        return dedupe_texts(queries)

    def _build_profile_constraints(
        self,
        *,
        diet_type: Any,
        goal: Any,
        allergies: list[str],
        diseases: list[str],
        preferences: list[str],
        restrictions: list[str],
        target_recipe_calories: float | None,
    ) -> list[dict[str, str]]:
        constraints: list[dict[str, str]] = []
        for kind, values in [
            ("diet_type", self._list_values(diet_type)),
            ("goal", self._list_values(goal)),
            ("allergy", allergies),
            ("disease", diseases),
            ("preference", preferences),
            ("restriction", restrictions),
        ]:
            for value in values:
                constraints.append({"kind": kind, "value": value})
        if target_recipe_calories:
            constraints.append({"kind": "target_calories", "value": f"{int(target_recipe_calories)} ккал на порцию рецепта"})
        return constraints

    def _constraint_queries(self, constraints: list[dict[str, str]]) -> list[str]:
        queries: list[str] = []
        for item in constraints:
            value = normalize_text(item.get("value"))
            if not value:
                continue
            for template in PROFILE_QUERY_TEMPLATES.get(item.get("kind") or "", []):
                queries.append(template.format(value=value))
        return queries

    def _first_alias(self, values: list[Any], aliases: dict[str, list[str]]) -> str | None:
        for value in values:
            text = normalize_text(value)
            if not text:
                continue
            for code, patterns in aliases.items():
                if any(pattern in text for pattern in patterns):
                    return code
        return None

    def _collect_aliases(self, values: list[str], aliases: dict[str, list[str]]) -> set[str]:
        matched: set[str] = set()
        for value in values:
            text = normalize_text(value)
            if not text:
                continue
            for code, patterns in aliases.items():
                if any(pattern in text for pattern in patterns):
                    matched.add(code)
        return matched

    def _list_values(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if value is None:
            return []
        text = str(value).strip()
        return [text] if text else []

    def _coerce_positive_number(self, value: Any) -> float | None:
        if value in {None, ""}:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return round(numeric, 2) if numeric > 0 else None


personalization_service = PersonalizationService()
