from __future__ import annotations

import re

from app.core.utils import normalize_text


class RecipeInputCleaner:
    META_PREFIX_PATTERNS = (
        r"^\s*можешь\s+разобрать.+?:\s*",
        r"^\s*разбери.+?:\s*",
        r"^\s*проанализируй.+?:\s*",
        r"^\s*сделай.+?json\s*:?\s*",
        r"^\s*выдели.+?:\s*",
    )
    RECIPE_START_MARKERS = (
        "ингредиенты",
        "состав",
        "инструкции",
        "приготовление",
        "паста",
        "борщ",
        "салат",
        "суп",
        "карбонара",
    )
    TAIL_PATTERNS = (
        r"теперь вы можете насладиться.+$",
        r"приятного аппетита.*$",
    )

    def clean(self, raw_input: str) -> str:
        text = raw_input.replace("\r\n", "\n").strip()
        text = self._strip_meta_prefix(text)
        text = self._strip_tail(text)
        return text.strip()

    def _strip_meta_prefix(self, text: str) -> str:
        lowered = normalize_text(text)
        if any(marker in lowered for marker in ("ингредиенты", "приготовление", "инструкции")):
            lines = [line for line in text.split("\n")]
            for index, line in enumerate(lines):
                low = normalize_text(line)
                if any(marker in low for marker in self.RECIPE_START_MARKERS):
                    candidate = "\n".join(lines[index:]).strip()
                    if len(candidate) >= max(len(text) * 0.5, 100):
                        text = candidate
                        break
        for pattern in self.META_PREFIX_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
        return text.strip()

    def _strip_tail(self, text: str) -> str:
        result = text
        for pattern in self.TAIL_PATTERNS:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE | re.DOTALL)
        return result.strip()


input_cleaner = RecipeInputCleaner()
