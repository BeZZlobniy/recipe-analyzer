from __future__ import annotations

import json
from typing import Any


PROFILE_ANALYSIS_BLOCK_KEYS = (
    "goal_alignment",
    "allergy_issues",
    "disease_issues",
    "preference_alignment",
    "additional_restrictions",
)


PROFILE_ANALYSIS_BLOCKS = {
    "goal_alignment": {
        "title": "Соответствие цели",
        "focus": (
            "Оцени только соответствие цели профиля. Используй КБЖУ, натрий, клетчатку, "
            "portion_guidance и nutrition_signals. Не обсуждай аллергии и тип питания, если они не влияют на цель."
        ),
    },
    "allergy_issues": {
        "title": "Аллергии",
        "focus": (
            "Оцени только аллергии и непереносимости. Сопоставь их с ингредиентами и RAG-контекстом. "
            "Если прямого аллергена нет, объясни это по найденным ингредиентам."
        ),
    },
    "disease_issues": {
        "title": "Заболевания",
        "focus": (
            "Оцени только заболевания/состояния из профиля. Учитывай нутриенты и ингредиенты, "
            "например натрий, жирность, сахар, пурины, кислотность, грубую клетчатку, если это релевантно профилю."
        ),
    },
    "preference_alignment": {
        "title": "Предпочтения",
        "focus": (
            "Оцени только пищевые предпочтения пользователя: любимые/нелюбимые продукты, формат блюда, "
            "острота, сытность, сладкое, жареное и другие предпочтения из профиля."
        ),
    },
    "additional_restrictions": {
        "title": "Тип питания и ограничения",
        "focus": (
            "Оцени только тип питания и дополнительные ограничения. Для vegetarian конфликтуют мясо, птица и рыба; "
            "для vegan конфликтуют все животные продукты. Овощи, крупы, бобовые, соль, перец, вода, уксус, сахар "
            "и растительные масла являются растительными продуктами."
        ),
    },
}


PROFILE_BLOCK_TEMPLATE = """Ты формируешь один блок персонализированного RAG-анализа рецепта на русском языке.
Верни только валидный JSON без markdown и текста вне JSON.

Блок: {block_title}
Фокус блока: {block_focus}

Верни ровно такую структуру:
{{"summary":"2-3 конкретных предложения по этому блоку","evidence":["..."],"recommendations":["..."],"compatibility":"low|medium|high","status":"ok|warning|conflict"}}

Правила:
- Используй только данные из INPUT и RAG-контекста.
- Не дублируй общие советы, пиши только про фокус текущего блока.
- Пиши кратко: максимум 2 пункта evidence и максимум 2 пункта recommendations.
- Не предлагай замену продукта, которого нет в рецепте.
- Если блок полностью совместим, recommendations можно оставить пустым; не придумывай лишние действия.
- Если в profile для текущего блока список аллергий, заболеваний или предпочтений пуст, прямо укажи, что этот пункт в профиле не задан, и не переноси сюда ограничения из других блоков.
- Если конфликта нет, не пиши unknown и не оставляй блок пустым: объясни, почему блок совместим.
- status=conflict только при прямом конфликте с профилем; status=warning при заметном нюансе без жесткого запрета; status=ok если блок совместим.
- compatibility=low только при прямом конфликте; medium при нюансах; high если блок хорошо совместим.
- Для vegetarian/vegan НЕ считай конфликтом овощи, фрукты, крупы, бобовые, соль, перец, воду, уксус, сахар и растительные масла.
- Никогда не пиши, что лук, помидоры, соль, перец, чеснок, фасоль, гречка, пшено или зелень не являются растительной едой.
- Молоко, сыр, сметана, сливки и сливочное масло конфликтуют с аллергией/непереносимостью молочных продуктов.
- Мясо, птица и рыба конфликтуют с вегетарианским питанием; любые животные продукты конфликтуют с веганским питанием.
- Если portion_guidance рекомендует разделить рецепт на N порций и это релевантно блоку, добавь рекомендацию в поле recommendations.

INPUT={input_json}"""


def build_recipe_structuring_prompt(recipe_text: str) -> str:
    return (
        "Ты извлекаешь из текста рецепта только название блюда и список ингредиентов.\n"
        "Верни строго один JSON-объект с ключом recipe. Никакого markdown, комментариев и текста вне JSON.\n"
        "Нужный формат:\n"
        '{"recipe":{"title":"...","ingredients":[{"name_ru":"...","name_en":"...","quantity_text":"...","quantity_value":1,"quantity_unit":"шт","optional":false,"llm_grams":180,"gram_confidence":"medium"}],"instructions":[],"tags":[]}}\n'
        "Контекст задачи:\n"
        "- Текст может быть скопирован с сайта и содержать подписи фото, автора, дату, блоки 'Для теста', 'Для начинки', 'Для подачи'.\n"
        "- Ингредиенты нужно брать из раздела продуктов/ингредиентов, а не из пошагового описания.\n"
        "- Если ингредиент указан как 'Мясо (говядина)' или 'Фарш (свинина и говядина)', сохраняй смысл: name_en='beef' или 'ground beef and pork'.\n"
        "- Для молочных продуктов сохраняй конкретику: сыр, молоко, сливки, йогурт, творог, масло.\n"
        "- Для аллергенов и диетических ограничений важны: мясо, рыба, морепродукты, яйца, молочные продукты, орехи, глютен, соя, кунжут.\n"
        "Правила полей:\n"
        "1. name_ru: короткое русское название из рецепта, без лишних описаний, но с важными уточнениями в скобках.\n"
        "2. name_en: короткое английское название продукта для поиска в USDA FoodData Central.\n"
        "   Используй реальный английский пищевой термин, а не транслитерацию: сметана=sour cream, творог=cottage cheese, гречка=buckwheat groats, курица=chicken, лук=onion, скумбрия=mackerel.\n"
        "   Не возвращай smetana, tvorog, grechka, kuritsa, luk, skumbriya, govyadina, svinina и другие латинские записи русских слов.\n"
        "   Если точный термин неизвестен, верни базовую категорию USDA: beef, pork, chicken, fish, milk, cheese, wheat flour, onion, potato, vegetable oil.\n"
        "3. quantity_text: нормализованный текст количества. Если указано 'по вкусу', верни exactly 'по вкусу'.\n"
        "4. quantity_value: число. Если указан диапазон, верни среднее. Если количества нет, верни null.\n"
        "5. quantity_unit: одна из: г, кг, мл, л, шт, ст. л., ч. л., стакан, зубчик, кочан, ломтик, пучок. Если количества нет, верни null.\n"
        "6. optional=true только если ингредиент явно опциональный.\n"
        "7. llm_grams заполняй только если можно разумно оценить массу, а явных граммов нет; иначе null.\n"
        "8. gram_confidence: high|medium|low|null для поля llm_grams.\n"
        "9. Не объединяй разные ингредиенты в один, кроме пары 'соль, перец', если она записана вместе.\n"
        "10. instructions и tags всегда возвращай пустыми массивами.\n"
        f"Рецепт:\n{recipe_text}"
    )


def build_product_candidate_prompt(
    recipe_text: str,
    recipe_title: str,
    ingredient_payload: dict[str, Any],
    candidate_products: list[dict[str, Any]],
) -> str:
    return (
        "Choose the best USDA product candidate for the recipe ingredient.\n"
        "Return JSON only: {\"selected_product_id\":123,\"confidence\":\"high|medium|low\",\"reason\":\"...\"}\n"
        "Rules:\n"
        "- Choose only from the candidate list.\n"
        "- Prefer raw/basic ingredients over prepared meals, sauces, snacks, desserts, sandwiches, mixes and branded composite foods.\n"
        "- Preserve diet/allergen meaning: beef must not resolve to generic sauce; milk/cheese must stay dairy; wheat flour must stay wheat/gluten source.\n"
        "- If all candidates are unsafe or unrelated, return selected_product_id=null and confidence='low'.\n"
        "- Use full recipe context, title and neighboring ingredients to resolve ambiguous Russian names.\n"
        f"Recipe title: {recipe_title}\n"
        f"Recipe text: {recipe_text}\n"
        f"Ingredient: {json.dumps(ingredient_payload, ensure_ascii=False)}\n"
        f"Candidates: {json.dumps(candidate_products, ensure_ascii=False)}"
    )


def build_profile_block_prompt(analysis_input: dict[str, Any], block_key: str) -> str:
    block = PROFILE_ANALYSIS_BLOCKS.get(block_key)
    if block is None:
        raise ValueError(f"Unknown profile analysis block: {block_key}")
    return PROFILE_BLOCK_TEMPLATE.format(
        block_title=block["title"],
        block_focus=block["focus"],
        input_json=json.dumps(_compact_profile_block_input(analysis_input, block_key), ensure_ascii=False),
    )


def _compact_profile_analysis_input(analysis_input: dict[str, Any]) -> dict[str, Any]:
    profile_context = analysis_input.get("profile_context") or {}
    return {
        "recipe_title": analysis_input.get("recipe_title"),
        "profile": _compact_profile(analysis_input.get("profile") or {}, profile_context),
        "ingredients": _compact_ingredients(analysis_input.get("ingredient_context") or []),
        "nutrition_per_serving": analysis_input.get("nutrition_per_serving"),
        "nutrition_total": analysis_input.get("nutrition_total"),
        "nutrition_signals": analysis_input.get("nutrition_signals") or [],
        "portion_guidance": analysis_input.get("portion_guidance") or {},
        "analysis_quality": analysis_input.get("analysis_quality") or {},
        "unresolved_ingredients": analysis_input.get("unresolved_ingredients") or [],
        "rag_context": _compact_rag_context(analysis_input.get("rag_context") or []),
    }


def _compact_profile_block_input(analysis_input: dict[str, Any], block_key: str) -> dict[str, Any]:
    full = _compact_profile_analysis_input(analysis_input)
    return {
        "recipe_title": full["recipe_title"],
        "profile": _compact_profile_for_block(full["profile"], block_key),
        "ingredients": _compact_block_ingredients(full["ingredients"]),
        "nutrition_per_serving": full["nutrition_per_serving"],
        "nutrition_signals": full["nutrition_signals"],
        "portion_guidance": full["portion_guidance"],
        "analysis_quality": full["analysis_quality"],
        "unresolved_ingredients": full["unresolved_ingredients"],
        "rag_context": _select_block_rag_context(full["rag_context"], block_key),
    }


def _compact_profile_for_block(profile: dict[str, Any], block_key: str) -> dict[str, Any]:
    base = {"name": profile.get("name")}
    if block_key == "goal_alignment":
        return {
            **base,
            "goal": profile.get("goal"),
            "goal_code": profile.get("goal_code"),
            "target_recipe_calories": profile.get("target_recipe_calories"),
        }
    if block_key == "allergy_issues":
        return {
            **base,
            "allergies": profile.get("allergies") or [],
            "allergy_codes": profile.get("allergy_codes") or [],
        }
    if block_key == "disease_issues":
        return {
            **base,
            "diseases": profile.get("diseases") or [],
            "disease_codes": profile.get("disease_codes") or [],
        }
    if block_key == "preference_alignment":
        return {
            **base,
            "preferences": profile.get("preferences") or [],
            "preference_codes": profile.get("preference_codes") or [],
            "restrictions": profile.get("restrictions") or "",
        }
    if block_key == "additional_restrictions":
        return {
            **base,
            "diet_type": profile.get("diet_type"),
            "diet_code": profile.get("diet_code"),
            "restrictions": profile.get("restrictions") or "",
        }
    return profile


def _compact_profile(profile: dict[str, Any], profile_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": profile.get("name"),
        "diet_type": profile.get("diet_type"),
        "diet_code": profile_context.get("diet_code"),
        "goal": profile.get("goal"),
        "goal_code": profile_context.get("goal_code"),
        "allergies": profile_context.get("raw_allergies") or profile.get("allergies_json") or [],
        "allergy_codes": profile_context.get("allergy_codes") or [],
        "diseases": profile_context.get("raw_diseases") or profile.get("diseases_json") or [],
        "disease_codes": profile_context.get("disease_codes") or [],
        "preferences": profile_context.get("raw_preferences") or profile.get("preferences_json") or [],
        "preference_codes": profile_context.get("preference_codes") or [],
        "restrictions": profile_context.get("raw_restrictions") or profile.get("restrictions_text") or "",
        "target_recipe_calories": profile.get("target_recipe_calories") or profile_context.get("target_recipe_calories"),
    }


def _compact_ingredients(ingredients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in ingredients[:20]:
        compact.append(
            {
                "name": item.get("name_raw") or item.get("name_canonical"),
                "name_en": item.get("name_en"),
                "matched": item.get("matched_name"),
                "grams": item.get("estimated_grams"),
                "calories": item.get("calories"),
                "protein": item.get("protein"),
                "fat": item.get("fat"),
                "carbs": item.get("carbs"),
                "sodium": item.get("sodium"),
            }
        )
    return compact


def _compact_block_ingredients(ingredients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in ingredients[:18]:
        compact.append(
            {
                "name": item.get("name"),
                "name_en": item.get("name_en"),
                "matched": item.get("matched"),
                "grams": item.get("grams"),
                "calories": item.get("calories"),
                "fat": item.get("fat"),
                "sodium": item.get("sodium"),
            }
        )
    return compact


def _compact_rag_context(rag_context: list[dict[str, Any]]) -> list[dict[str, str]]:
    compact: list[dict[str, str]] = []
    for item in rag_context[:6]:
        title = str(item.get("title") or item.get("source") or "").strip()
        text = str(item.get("text") or item.get("content") or item.get("chunk") or "").strip()
        if len(text) > 450:
            text = text[:450].rsplit(" ", 1)[0] + "..."
        compact.append({"title": title, "text": text})
    return compact


def _select_block_rag_context(rag_context: list[dict[str, str]], block_key: str) -> list[dict[str, str]]:
    keywords = {
        "goal_alignment": ("цель", "калор", "жир", "натрий", "клетчат", "portion", "energy"),
        "allergy_issues": ("аллер", "лактоз", "молоч", "глютен", "орех", "яйц", "allergy"),
        "disease_issues": ("диаб", "гиперт", "почки", "жкт", "подаг", "заболев", "disease"),
        "preference_alignment": ("предпоч", "остр", "сыт", "слад", "жарен", "preference"),
        "additional_restrictions": ("веган", "вегет", "пост", "халяль", "кошер", "огранич", "diet"),
    }.get(block_key, ())
    selected: list[dict[str, str]] = []
    for item in rag_context:
        haystack = f"{item.get('title', '')} {item.get('text', '')}".lower()
        if any(keyword in haystack for keyword in keywords):
            selected.append(_trim_rag_item(item, 320))
    if len(selected) < 3:
        for item in rag_context:
            trimmed = _trim_rag_item(item, 280)
            if trimmed not in selected:
                selected.append(trimmed)
            if len(selected) >= 3:
                break
    return selected[:3]


def _trim_rag_item(item: dict[str, str], limit: int) -> dict[str, str]:
    text = str(item.get("text") or "").strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "..."
    return {"title": str(item.get("title") or "").strip(), "text": text}
