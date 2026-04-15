from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, List

from app.core.config import settings


def ensure_data_dir() -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir


def find_data_file(filename: str) -> Path:
    return ensure_data_dir() / filename


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


def dedupe_texts(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
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


def extract_number(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(value))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_range(value: str) -> tuple[float, float] | None:
    normalized = normalize_text(value)
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)", normalized)
    if not match:
        return None
    left = float(match.group(1).replace(",", "."))
    right = float(match.group(2).replace(",", "."))
    return (left, right) if right >= left else None


def json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;\n]", value) if item.strip()]
    return []
