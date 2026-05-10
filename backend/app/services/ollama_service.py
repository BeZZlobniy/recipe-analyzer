from __future__ import annotations

import json
from typing import Any

import requests

from app.core.config import settings
from app.services.qwen_prompts import (
    build_product_candidate_prompt,
    build_profile_block_prompt,
    build_recipe_structuring_prompt,
    PROFILE_ANALYSIS_BLOCK_KEYS,
)


class OllamaService:
    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self.analysis_model = settings.ollama_analysis_model
        self.normalization_model = settings.ollama_normalization_model
        self.generate_endpoint = f"{self.base_url}/api/generate"
        self._unhealthy_analysis_models: set[str] = set()

    def structure_recipe_json(self, recipe_text: str) -> dict[str, Any]:
        return self._generate_json(
            build_recipe_structuring_prompt(recipe_text),
            {"recipe": {"title": "", "ingredients": [], "instructions": [], "tags": []}},
            model=self.normalization_model,
            fallback_models=settings.ollama_normalization_fallback_models,
        )

    def resolve_product_candidate(
        self,
        recipe_text: str,
        recipe_title: str,
        ingredient_payload: dict[str, Any],
        candidate_products: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._generate_json(
            build_product_candidate_prompt(recipe_text, recipe_title, ingredient_payload, candidate_products),
            {"selected_product_id": None, "confidence": "low", "reason": ""},
        )

    def generate_profile_analysis(self, analysis_input: dict[str, Any]) -> dict[str, Any]:
        blocks: dict[str, Any] = {}
        for block_key in PROFILE_ANALYSIS_BLOCK_KEYS:
            blocks[block_key] = self._generate_json(
                build_profile_block_prompt(analysis_input, block_key),
                {
                    "summary": "",
                    "evidence": [],
                    "recommendations": [],
                    "compatibility": "medium",
                    "status": "unknown",
                },
                model=self.analysis_model,
                fallback_models=settings.ollama_analysis_fallback_models,
                timeout_sec=settings.ollama_analysis_timeout_sec,
                num_predict=450,
                num_ctx=4096,
                mark_unhealthy_on_failure=True,
            )
        return {
            "summary": "",
            "detected_issues": [],
            "recommendations": [],
            "warnings": [],
            "compatibility": {"diet": "medium", "restriction": "medium", "goal": "medium"},
            "profile_assessment": blocks,
            "mode": "segmented",
        }

    def _generate_json(
        self,
        prompt: str,
        fallback: dict[str, Any],
        model: str | None = None,
        fallback_models: list[str] | None = None,
        timeout_sec: int | None = None,
        num_predict: int = 1800,
        num_ctx: int = 8192,
        mark_unhealthy_on_failure: bool = False,
    ) -> dict[str, Any]:
        models = [model or self.model, *(fallback_models or [])]
        seen: set[str] = set()
        for candidate_model in models:
            if candidate_model in seen:
                continue
            if mark_unhealthy_on_failure and candidate_model in self._unhealthy_analysis_models:
                continue
            seen.add(candidate_model)
            payload = self._generate_json_once(
                prompt,
                candidate_model,
                required_keys=set(fallback.keys()),
                timeout_sec=timeout_sec,
                num_predict=num_predict,
                num_ctx=num_ctx,
            )
            if payload is not None:
                return payload
            if mark_unhealthy_on_failure and candidate_model == self.analysis_model:
                self._unhealthy_analysis_models.add(candidate_model)
        return fallback

    def _generate_json_once(
        self,
        prompt: str,
        model: str,
        required_keys: set[str],
        timeout_sec: int | None = None,
        num_predict: int = 1800,
        num_ctx: int = 8192,
    ) -> dict[str, Any] | None:
        raw_timeout = settings.ollama_timeout_sec if timeout_sec is None else timeout_sec
        request_timeout = None if raw_timeout is None or int(raw_timeout) <= 0 else max(int(raw_timeout), 1)
        response_payload = self._request_generate(prompt, model, request_timeout, num_predict=num_predict, num_ctx=num_ctx)
        if response_payload is None:
            return None
        for field in ("response", "thinking"):
            parsed = self._parse_json_text(response_payload.get(field, ""))
            if parsed is not None and self._has_required_shape(parsed, required_keys):
                return parsed
        return None

    def _request_generate(
        self,
        prompt: str,
        model: str,
        request_timeout: int | None,
        num_predict: int = 1800,
        num_ctx: int = 8192,
    ) -> dict[str, Any] | None:
        timeout_attempts = 2 if request_timeout else 1
        for attempt in range(timeout_attempts):
            try:
                response = requests.post(
                    self.generate_endpoint,
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "keep_alive": "30m",
                        "options": {"temperature": 0, "num_predict": num_predict, "num_ctx": num_ctx},
                    },
                    timeout=request_timeout,
                )
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, dict) else None
            except requests.Timeout:
                if attempt + 1 >= timeout_attempts:
                    return None
            except Exception:
                return None
        return None

    def _parse_json_text(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, str) or not raw.strip():
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                parsed = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return None
        return parsed if isinstance(parsed, dict) else None

    def _has_required_shape(self, payload: dict[str, Any], required_keys: set[str]) -> bool:
        return bool(payload) and bool(required_keys & set(payload.keys()))


ollama_service = OllamaService()
