from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from app.core.config import settings


def ensure_data_dir() -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir


def find_data_file(filename: str) -> Path:
    return ensure_data_dir() / filename


def load_data_json(filename: str, default: Any | None = None) -> Any:
    path = find_data_file(filename)
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def maybe_fix_mojibake(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\ufeff", "").replace("ï»¿", "")
    return value


def normalize_text(value: Any) -> str:
    text = str(maybe_fix_mojibake(value) or "").strip().lower()
    text = text.replace("ё", "е").replace("—", "-").replace("–", "-")
    text = re.sub(r"[«»\"“”„‟]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_spaces(value: Any) -> str:
    return re.sub(r"\s+", " ", str(maybe_fix_mojibake(value) or "")).strip()


def dedupe_texts(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen = set()
    for value in values:
        text = normalize_spaces(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def pluralize_ru(value: int, forms: tuple[str, str, str]) -> str:
    mod10 = abs(value) % 10
    mod100 = abs(value) % 100
    if mod10 == 1 and mod100 != 11:
        return forms[0]
    if 2 <= mod10 <= 4 and not 12 <= mod100 <= 14:
        return forms[1]
    return forms[2]


def format_portions(value: int) -> str:
    return f"{value} {pluralize_ru(value, ('порция', 'порции', 'порций'))}"


def parse_range(value: str) -> tuple[float, float] | None:
    normalized = normalize_text(value)
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)", normalized)
    if not match:
        return None
    left = float(match.group(1).replace(",", "."))
    right = float(match.group(2).replace(",", "."))
    return (left, right) if right >= left else None
