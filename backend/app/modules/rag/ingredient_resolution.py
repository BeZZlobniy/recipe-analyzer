from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.utils import normalize_text
from app.models.external_lookup_cache import ExternalLookupCache
from app.models.product import Product
from app.modules.rag.usda_client import usda_client
from app.modules.rag.usda_resolution_utils import (
    build_queries,
    candidate_ids,
    extract_nutrients,
    is_exact_candidate,
    is_safe_candidate,
    piece_estimate,
    score_candidate,
    serialize_product,
)
from app.modules.structuring.schemas import StructuredRecipe
from app.services.ollama_service import ollama_service


class RagIngredientResolutionService:
    def resolve(self, db: Session, recipe_text: str, recipe: StructuredRecipe) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for ingredient in recipe.ingredients:
            queries = build_queries(ingredient.name_canonical, ingredient.name_en)[: settings.usda_max_queries_per_ingredient]
            top_candidates = self._search_candidates(db, queries)
            selection = self._select_candidate(recipe_text, recipe.title, ingredient.model_dump(), top_candidates)
            product = db.get(Product, selection["selected_product_id"]) if selection.get("selected_product_id") else None
            matched_product = serialize_product(product)
            resolved.append(
                {
                    "ingredient": ingredient.model_dump(),
                    "match_status": "matched" if matched_product else "unresolved",
                    "matched_name": matched_product.get("display_name_ru") if matched_product else None,
                    "matched_source": matched_product.get("source") if matched_product else None,
                    "match_method": selection.get("match_method", "unresolved"),
                    "match_confidence": selection.get("confidence", "low"),
                    "selection_reason": selection.get("reason"),
                    "nutrition_source": matched_product.get("source") if matched_product and matched_product.get("nutrients_per_100g") else "unknown",
                    "nutrition_confidence": "medium" if matched_product else "low",
                    "matched_product": matched_product,
                    "top_candidates": top_candidates,
                    "usda_queries": queries,
                    "canonical_query_en": next((item for item in queries if item.isascii()), None),
                }
            )
        return resolved

    def _search_candidates(self, db: Session, queries: list[str]) -> list[dict[str, Any]]:
        scored: dict[int, dict[str, Any]] = {}
        for query_index, query in enumerate(queries):
            for rank, product in enumerate(self._products_for_query(db, query)):
                score = score_candidate(product, query, rank, query_index)
                if score <= 0:
                    continue
                current = scored.get(product.id)
                if current is None or score > current["score"]:
                    scored[product.id] = {
                        "product_id": product.id,
                        "score": score,
                        "strategy": "usda_search",
                        "display_name_ru": product.display_name_ru,
                        "display_name_en": product.display_name_en,
                        "category": product.category,
                        "source": product.source,
                    }
        return sorted(scored.values(), key=lambda item: item["score"], reverse=True)[: settings.usda_page_size]

    def _products_for_query(self, db: Session, query: str) -> list[Product]:
        normalized = normalize_text(query)
        if not normalized:
            return []

        cached = db.scalar(
            select(ExternalLookupCache).where(
                ExternalLookupCache.provider == "usda_search",
                ExternalLookupCache.query_normalized == normalized,
            )
        )
        if cached:
            ids = candidate_ids(cached.response_json)
            if ids:
                products = db.scalars(select(Product).where(Product.id.in_(ids))).all()
                by_id = {item.id: item for item in products}
                return [by_id[item_id] for item_id in ids if item_id in by_id]

        raw_foods = usda_client.search(query)
        hydrated = [self._upsert_product(db, item, query) for item in raw_foods]
        hydrated = [item for item in hydrated if item is not None]
        cache = cached or ExternalLookupCache(
            provider="usda_search",
            query_raw=query,
            query_normalized=normalized,
            query_lang="en" if normalized.isascii() else "ru",
            response_json={},
        )
        if cached is None:
            db.add(cache)
        cache.response_json = {"query": query, "candidate_product_ids": [item.id for item in hydrated], "count": len(hydrated)}
        db.commit()
        return hydrated

    def _upsert_product(self, db: Session, payload: dict[str, Any], query: str) -> Product | None:
        fdc_id = payload.get("fdcId")
        if fdc_id is None:
            return None
        details = None
        nutrients = extract_nutrients(payload)
        if not nutrients:
            details = usda_client.food_details(fdc_id)
            if not details:
                return None
            nutrients = extract_nutrients(details)
        if not nutrients:
            return None

        source_product_id = str(fdc_id)
        product = db.scalar(select(Product).where(Product.source == "usda", Product.source_product_id == source_product_id))
        display_name = (details or {}).get("description") or payload.get("description") or query
        category = (details or {}).get("dataType") or payload.get("dataType") or "USDA"
        grams_per_piece_estimate = piece_estimate(display_name)
        if product is None:
            product = Product(
                source="usda",
                source_product_id=source_product_id,
                display_name_ru=display_name,
                display_name_en=display_name,
                category=category,
                nutrients_json=nutrients,
                grams_per_piece_estimate=grams_per_piece_estimate,
                data_confidence="high" if category in {"Survey (FNDDS)", "SR Legacy", "Foundation"} else "medium",
                notes="Imported from USDA FoodData Central.",
            )
            db.add(product)
            db.flush()
        else:
            product.display_name_ru = display_name
            product.display_name_en = display_name
            product.category = category
            product.nutrients_json = nutrients
            product.grams_per_piece_estimate = grams_per_piece_estimate
            product.data_confidence = "high" if category in {"Survey (FNDDS)", "SR Legacy", "Foundation"} else "medium"
        return product

    def _select_candidate(
        self,
        recipe_text: str,
        recipe_title: str,
        ingredient_payload: dict[str, Any],
        candidate_products: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not candidate_products:
            return {"selected_product_id": None, "confidence": "low", "reason": "Кандидаты USDA не найдены.", "match_method": "unresolved"}
        top = candidate_products[0]
        second_score = candidate_products[1]["score"] if len(candidate_products) > 1 else 0.0

        if is_exact_candidate(ingredient_payload, top):
            return {
                "selected_product_id": top["product_id"],
                "confidence": "high",
                "reason": "Выбран точный кандидат USDA по английскому названию ингредиента.",
                "match_method": "usda_exact_name",
            }
        if len(candidate_products) == 1 and is_safe_candidate(ingredient_payload, top):
            return {
                "selected_product_id": top["product_id"],
                "confidence": "medium",
                "reason": "USDA вернула один релевантный кандидат.",
                "match_method": "usda_single_candidate",
            }
        if is_safe_candidate(ingredient_payload, top) and top["score"] >= 4.0 and top["score"] - second_score >= 0.3:
            return {
                "selected_product_id": top["product_id"],
                "confidence": "medium",
                "reason": "Выбран лучший релевантный USDA-кандидат без необходимости LLM-разрешения.",
                "match_method": "usda_rank_fallback",
            }
        if top["score"] < 2.8:
            return {"selected_product_id": None, "confidence": "low", "reason": "USDA shortlist слишком слабый для надежного выбора.", "match_method": "unresolved"}

        try:
            payload = ollama_service.resolve_product_candidate(
                recipe_text=recipe_text,
                recipe_title=recipe_title,
                ingredient_payload=ingredient_payload,
                candidate_products=candidate_products,
            )
        except Exception:
            payload = None
        if isinstance(payload, dict) and payload.get("selected_product_id") is not None:
            payload["match_method"] = "llm_usda_resolution"
            return payload
        if top["score"] >= 4.5 and is_safe_candidate(ingredient_payload, top):
            return {
                "selected_product_id": top["product_id"],
                "confidence": "low",
                "reason": "LLM недоступна, выбран лучший USDA-кандидат по рейтингу.",
                "match_method": "usda_rank_fallback",
            }
        return {"selected_product_id": None, "confidence": "low", "reason": "LLM не выбрала надежный USDA-кандидат.", "match_method": "unresolved"}

    def clear_legacy_off_data(self, db: Session) -> None:
        db.execute(delete(ExternalLookupCache).where(ExternalLookupCache.provider.like("openfoodfacts%")))
        db.execute(delete(Product).where(Product.source == "openfoodfacts"))
        db.commit()


rag_ingredient_resolution_service = RagIngredientResolutionService()
