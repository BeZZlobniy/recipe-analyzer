from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

from app.core.config import settings
from app.core.utils import normalize_text


class UsdaClient:
    def __init__(self) -> None:
        self.base_url = settings.usda_base_url.rstrip("/")

    def search(self, query: str) -> list[dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []

        local_hits, local_score = self._search_foundation_dataset(query)
        if local_hits and local_score >= 2.6:
            return local_hits[: settings.usda_page_size]

        if not settings.usda_api_key:
            return local_hits[: settings.usda_page_size]

        try:
            request_timeout = None if settings.web_fallback_timeout_sec is None or int(settings.web_fallback_timeout_sec) <= 0 else settings.web_fallback_timeout_sec
            response = requests.post(
                f"{self.base_url}/foods/search",
                params={"api_key": settings.usda_api_key},
                json={"query": query, "pageSize": settings.usda_page_size},
                timeout=request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []
        foods = payload.get("foods")
        return foods if isinstance(foods, list) else []

    def food_details(self, fdc_id: int | str) -> dict[str, Any] | None:
        local = self._foundation_by_fdc_id().get(str(fdc_id))
        if local:
            return local

        if not settings.usda_api_key:
            return None

        try:
            request_timeout = None if settings.web_fallback_timeout_sec is None or int(settings.web_fallback_timeout_sec) <= 0 else settings.web_fallback_timeout_sec
            response = requests.get(
                f"{self.base_url}/food/{fdc_id}",
                params={"api_key": settings.usda_api_key},
                timeout=request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _search_foundation_dataset(self, query: str) -> tuple[list[dict[str, Any]], float]:
        query_tokens = self._tokens(query)
        if not query_tokens:
            return [], 0.0

        scored: list[tuple[float, dict[str, Any]]] = []
        for item in self._foundation_foods():
            description = str(item.get("description") or "")
            description_tokens = self._tokens(description)
            if not description_tokens:
                continue
            intersection = len(query_tokens & description_tokens)
            if intersection <= 0:
                continue
            recall = intersection / max(len(query_tokens), 1)
            precision = intersection / max(len(description_tokens), 1)
            jaccard = intersection / max(len(query_tokens | description_tokens), 1)
            exact_bonus = 2.0 if normalize_text(query) == normalize_text(description) else 0.0
            prefix_bonus = 0.5 if normalize_text(description).startswith(normalize_text(query)) else 0.0
            score = recall * 1.8 + precision * 1.2 + jaccard * 1.5 + exact_bonus + prefix_bonus
            if score <= 0:
                continue
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        best_score = scored[0][0] if scored else 0.0
        return [item for _, item in scored[: settings.usda_page_size]], best_score

    def _tokens(self, text: str) -> set[str]:
        return {token for token in normalize_text(text).split() if len(token) >= 3}

    @lru_cache(maxsize=1)
    def _foundation_foods(self) -> list[dict[str, Any]]:
        path = Path(settings.usda_foundation_dataset_path)
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return []
        foods = payload.get("FoundationFoods") if isinstance(payload, dict) else None
        return foods if isinstance(foods, list) else []

    @lru_cache(maxsize=1)
    def _foundation_by_fdc_id(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in self._foundation_foods():
            fdc_id = item.get("fdcId")
            if fdc_id is not None:
                result[str(fdc_id)] = item
        return result


usda_client = UsdaClient()
