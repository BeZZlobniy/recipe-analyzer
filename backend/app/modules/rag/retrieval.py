from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.utils import find_data_file, normalize_text


class RetrievalService:
    def __init__(self) -> None:
        self.kb_path = find_data_file("knowledge_base.json")
        self.emb_path = find_data_file("knowledge_base_embeddings.npy")
        self.meta_path = find_data_file("knowledge_base_embeddings_meta.json")
        self._kb: list[dict[str, Any]] | None = None
        self._embeddings: np.ndarray | None = None
        self._model: SentenceTransformer | None = None

    def search(self, queries: list[str], top_k: int = 5) -> list[dict[str, Any]]:
        kb = self._load_kb()
        if not kb:
            return []
        embedding_results = self._embedding_search(queries, top_k) if settings.enable_embedding_retrieval else []
        lexical_results = self._lexical_search(queries, top_k * 2)
        merged: dict[str, dict[str, Any]] = {}
        for item in embedding_results + lexical_results:
            key = item["id"]
            if key not in merged or item["score"] > merged[key]["score"]:
                merged[key] = item
        filtered = self._filter_relevance(list(merged.values()), queries)
        return sorted(filtered, key=lambda item: item["score"], reverse=True)[:top_k]

    def _embedding_search(self, queries: list[str], top_k: int) -> list[dict[str, Any]]:
        try:
            kb = self._load_kb()
            embeddings = self._load_embeddings(kb)
            model = self._get_model()
            vector = model.encode([" ".join(queries)], convert_to_numpy=True, normalize_embeddings=True)[0]
            scores = embeddings @ vector
            indices = np.argsort(-scores)[:top_k]
            return [
                {
                    "id": kb[index]["id"],
                    "source": kb[index]["source"],
                    "text": kb[index]["text"],
                    "tags": kb[index].get("tags", []),
                    "score": float(scores[index]),
                }
                for index in indices
            ]
        except Exception:
            return []

    def _lexical_search(self, queries: list[str], top_k: int) -> list[dict[str, Any]]:
        tokens = {token for query in queries for token in normalize_text(query).split() if len(token) >= 4}
        scored = []
        for chunk in self._load_kb():
            text = normalize_text(chunk.get("text"))
            overlap = sum(1 for token in tokens if token in text)
            tag_overlap = sum(1 for token in tokens if token in " ".join(chunk.get("tags", [])))
            score = float(overlap + tag_overlap * 1.5) / max(len(tokens), 1)
            if score > 0:
                scored.append(
                    {
                        "id": chunk["id"],
                        "source": chunk["source"],
                        "text": chunk["text"],
                        "tags": chunk.get("tags", []),
                        "score": score,
                    }
                )
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:top_k]

    def _filter_relevance(self, results: list[dict[str, Any]], queries: list[str]) -> list[dict[str, Any]]:
        query_tokens = {token for query in queries for token in normalize_text(query).split() if len(token) >= 4}
        filtered = []
        for item in results:
            text = normalize_text(item.get("text"))
            tags = " ".join(item.get("tags", []))
            overlap = len({token for token in query_tokens if token in text or token in tags})
            if overlap >= 2 or item["score"] >= 0.55:
                filtered.append(item)
        return filtered or results

    def _load_kb(self) -> list[dict[str, Any]]:
        if self._kb is None:
            self._kb = json.loads(self.kb_path.read_text(encoding="utf-8-sig")) if self.kb_path.exists() else []
        return self._kb

    def _load_embeddings(self, kb: list[dict[str, Any]]) -> np.ndarray:
        if self._embeddings is not None:
            return self._embeddings
        kb_hash = hashlib.sha256("\n".join(f"{item['id']}|{item['text']}" for item in kb).encode("utf-8")).hexdigest()
        if self.emb_path.exists() and self.meta_path.exists():
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            if meta.get("kb_hash") == kb_hash and meta.get("model") == settings.embedding_model and meta.get("count") == len(kb):
                emb = np.load(self.emb_path)
                norms = np.linalg.norm(emb, axis=1, keepdims=True) + 1e-12
                self._embeddings = emb / norms
                return self._embeddings
        model = self._get_model()
        emb = model.encode([item["text"] for item in kb], convert_to_numpy=True, normalize_embeddings=True)
        np.save(self.emb_path, emb)
        self.meta_path.write_text(
            json.dumps({"kb_hash": kb_hash, "model": settings.embedding_model, "count": len(kb)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._embeddings = emb
        return emb

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(settings.embedding_model)
        return self._model


retrieval_service = RetrievalService()
