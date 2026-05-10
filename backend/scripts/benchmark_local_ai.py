from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests
import torch
from sentence_transformers import SentenceTransformer


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings  # noqa: E402
from app.core.utils import find_data_file  # noqa: E402


def load_sample_texts(sample_size: int) -> list[str]:
    kb_path = find_data_file("knowledge_base.json")
    if kb_path.exists():
        raw = json.loads(kb_path.read_text(encoding="utf-8-sig"))
        texts = [str(item.get("text", "")).strip() for item in raw if str(item.get("text", "")).strip()]
        if texts:
            multiplier = max(1, math.ceil(sample_size / len(texts)))
            expanded = (texts * multiplier)[:sample_size]
            return expanded
    return [
        "High-protein breakfast with oats, yogurt, and berries.",
        "Low-sodium dinner with grilled chicken and steamed vegetables.",
        "Gluten-free snack with nuts, apple, and cinnamon.",
        "Weight-loss lunch with quinoa, avocado, and cucumber salad.",
    ] * max(1, math.ceil(sample_size / 4))


def benchmark_embeddings(sample_size: int, repeats: int, batch_size: int) -> dict[str, Any]:
    requested_device = settings.embedding_device
    resolved_device = settings.resolve_embedding_device()
    model = SentenceTransformer(settings.embedding_model, device=resolved_device)
    effective_device = str(next(model.parameters()).device)
    texts = load_sample_texts(sample_size)[:sample_size]

    model.encode(texts[: min(len(texts), batch_size)], batch_size=batch_size, convert_to_numpy=True, normalize_embeddings=True)
    if resolved_device == "cuda":
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()

    durations: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        model.encode(texts, batch_size=batch_size, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        if resolved_device == "cuda":
            torch.cuda.synchronize()
        durations.append(time.perf_counter() - start)

    avg_duration = sum(durations) / len(durations)
    throughput = len(texts) / avg_duration if avg_duration else 0.0
    peak_memory_mb = None
    if resolved_device == "cuda":
        peak_memory_mb = round(torch.cuda.max_memory_allocated() / 1024 / 1024, 2)

    return {
        "requested_device": requested_device,
        "resolved_device": resolved_device,
        "effective_device": effective_device,
        "sample_size": len(texts),
        "repeats": repeats,
        "batch_size": batch_size,
        "avg_duration_sec": round(avg_duration, 4),
        "throughput_texts_per_sec": round(throughput, 2),
        "peak_memory_mb": peak_memory_mb,
    }


def benchmark_ollama(prompt: str) -> dict[str, Any]:
    warmup_payload = {
        "model": settings.ollama_model,
        "prompt": "Reply with OK.",
        "stream": False,
        "options": {"temperature": 0},
    }
    requests.post(f"{settings.ollama_base_url.rstrip('/')}/api/generate", json=warmup_payload, timeout=120).raise_for_status()

    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }
    started_at = time.perf_counter()
    response = requests.post(f"{settings.ollama_base_url.rstrip('/')}/api/generate", json=payload, timeout=300)
    response.raise_for_status()
    elapsed = time.perf_counter() - started_at
    body = response.json()

    eval_count = int(body.get("eval_count") or 0)
    eval_duration_ns = int(body.get("eval_duration") or 0)
    prompt_eval_count = int(body.get("prompt_eval_count") or 0)
    prompt_eval_duration_ns = int(body.get("prompt_eval_duration") or 0)
    eval_tokens_per_sec = round(eval_count / (eval_duration_ns / 1_000_000_000), 2) if eval_duration_ns else None
    prompt_tokens_per_sec = (
        round(prompt_eval_count / (prompt_eval_duration_ns / 1_000_000_000), 2) if prompt_eval_duration_ns else None
    )

    try:
        ollama_ps = subprocess.run(["ollama", "ps"], check=True, capture_output=True, text=True).stdout.strip()
    except Exception as exc:
        ollama_ps = f"unavailable: {exc}"

    return {
        "model": settings.ollama_model,
        "wall_time_sec": round(elapsed, 4),
        "load_duration_sec": round(int(body.get("load_duration") or 0) / 1_000_000_000, 4),
        "prompt_eval_count": prompt_eval_count,
        "prompt_tokens_per_sec": prompt_tokens_per_sec,
        "eval_count": eval_count,
        "eval_tokens_per_sec": eval_tokens_per_sec,
        "response_preview": str(body.get("response", "")).strip()[:160],
        "ollama_ps": ollama_ps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark local Ollama and embedding runtime.")
    parser.add_argument("--sample-size", type=int, default=128)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    result = {
        "system": {
            "torch_version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
            "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        },
        "embeddings": benchmark_embeddings(
            sample_size=max(args.sample_size, 1),
            repeats=max(args.repeats, 1),
            batch_size=max(args.batch_size, 1),
        ),
        "ollama": benchmark_ollama(
            prompt=(
                "Return compact JSON with keys summary and tags. "
                "Summary must be one sentence about a healthy breakfast. "
                'Tags must be an array of 3 short English strings.'
            )
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
