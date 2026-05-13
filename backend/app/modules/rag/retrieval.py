from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.utils import find_data_file, normalize_text


SOURCE_HINT_PREFIX = "kb_source:"


class RetrievalService:
    def __init__(self) -> None:
        self.kb_path = find_data_file("knowledge_base.json")
        self.emb_path = find_data_file("knowledge_base_embeddings.npy")
        self.meta_path = find_data_file("knowledge_base_embeddings_meta.json")
        self.device = settings.resolve_embedding_device()
        self._kb: list[dict[str, Any]] | None = None
        self._embeddings: np.ndarray | None = None
        self._model: SentenceTransformer | None = None

    def search(self, queries: list[str], top_k: int = 5) -> list[dict[str, Any]]:
        kb = self._load_kb()
        if not kb:
            return []
        source_hints, clean_queries = self._extract_source_hints(queries)
        queries = clean_queries or queries
        candidate_window = max(top_k * 3, 6)
        embedding_results = self._embedding_search(queries, candidate_window) if settings.enable_embedding_retrieval else []
        lexical_results = self._lexical_search(queries, candidate_window)
        merged = self._merge_rankings(embedding_results, lexical_results)
        filtered = self._filter_relevance(list(merged.values()), queries)
        selected = self._select_balanced_results(filtered, lexical_results, top_k)
        return self._ensure_source_hints(selected, source_hints, queries, top_k)

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

    def _merge_rankings(
        self,
        embedding_results: list[dict[str, Any]],
        lexical_results: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}

        for item in lexical_results:
            merged[item["id"]] = {
                "id": item["id"],
                "source": item["source"],
                "text": item["text"],
                "tags": item.get("tags", []),
                "lexical_score": float(item["score"]),
                "embedding_score": 0.0,
            }

        for item in embedding_results:
            current = merged.get(item["id"])
            if current is None:
                merged[item["id"]] = {
                    "id": item["id"],
                    "source": item["source"],
                    "text": item["text"],
                    "tags": item.get("tags", []),
                    "lexical_score": 0.0,
                    "embedding_score": float(item["score"]),
                }
                continue
            current["embedding_score"] = max(float(item["score"]), float(current.get("embedding_score", 0.0)))

        for item in merged.values():
            lexical_score = float(item.pop("lexical_score", 0.0))
            embedding_score = float(item.pop("embedding_score", 0.0))
            hybrid_bonus = 0.08 if lexical_score > 0 and embedding_score > 0 else 0.0
            # Keep semantic retrieval additive, but do not let it drown obvious lexical matches.
            item["score"] = round(lexical_score + embedding_score * 0.35 + hybrid_bonus, 4)

        return merged

    def _select_balanced_results(
        self,
        results: list[dict[str, Any]],
        lexical_results: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        ranked = sorted(results, key=lambda item: item["score"], reverse=True)
        if not settings.enable_embedding_retrieval:
            return ranked[:top_k]

        by_id = {item["id"]: item for item in ranked}
        lexical_ranked = [by_id[item["id"]] for item in lexical_results if item["id"] in by_id]
        lexical_anchor_count = min(max(2, top_k // 2), len(lexical_ranked), top_k)

        selected: list[dict[str, Any]] = []
        seen: set[str] = set()

        for item in lexical_ranked[:lexical_anchor_count]:
            if item["id"] in seen:
                continue
            selected.append(item)
            seen.add(item["id"])

        for item in ranked:
            if item["id"] in seen:
                continue
            selected.append(item)
            seen.add(item["id"])
            if len(selected) >= top_k:
                break

        return selected[:top_k]

    def _extract_source_hints(self, queries: list[str]) -> tuple[list[str], list[str]]:
        hints: list[str] = []
        clean_queries: list[str] = []
        for query in queries:
            text = str(query or "").strip()
            if not text:
                continue
            if text.startswith(SOURCE_HINT_PREFIX):
                source = text.removeprefix(SOURCE_HINT_PREFIX).strip()
                if source:
                    hints.append(source)
                continue
            clean_queries.append(text)
        return list(dict.fromkeys(hints)), clean_queries

    def _ensure_source_hints(
        self,
        selected: list[dict[str, Any]],
        source_hints: list[str],
        queries: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        if not source_hints or top_k <= 0:
            return selected[:top_k]

        result = list(selected[:top_k])
        hinted_sources = set(source_hints)
        present_sources = {str(item.get("source") or "") for item in result}

        for source in source_hints[:top_k]:
            if source in present_sources:
                continue
            candidate = self._best_chunk_for_source(source, queries)
            if candidate is None:
                continue
            if len(result) < top_k:
                result.append(candidate)
            else:
                replace_index = self._lowest_priority_replacement_index(result, hinted_sources)
                if replace_index is None:
                    break
                result[replace_index] = candidate
            present_sources.add(source)

        return sorted(result, key=lambda item: float(item.get("score") or 0), reverse=True)[:top_k]

    def _best_chunk_for_source(self, source: str, queries: list[str]) -> dict[str, Any] | None:
        query_tokens = {token for query in queries for token in normalize_text(query).split() if len(token) >= 4}
        best: dict[str, Any] | None = None
        best_score = -1.0
        for chunk in self._load_kb():
            if chunk.get("source") != source:
                continue
            text = normalize_text(chunk.get("text"))
            tags = normalize_text(" ".join(chunk.get("tags", [])))
            overlap = sum(1 for token in query_tokens if token in text or token in tags)
            score = 1.0 + overlap / max(len(query_tokens), 1)
            if score > best_score:
                best_score = score
                best = {
                    "id": chunk["id"],
                    "source": chunk["source"],
                    "text": chunk["text"],
                    "tags": chunk.get("tags", []),
                    "score": round(score, 4),
                }
        return best

    def _lowest_priority_replacement_index(self, items: list[dict[str, Any]], protected_sources: set[str]) -> int | None:
        source_counts = Counter(str(item.get("source") or "") for item in items)
        duplicate_candidates = [
            (index, float(item.get("score") or 0))
            for index, item in enumerate(items)
            if source_counts[str(item.get("source") or "")] > 1
        ]
        if duplicate_candidates:
            return min(duplicate_candidates, key=lambda item: item[1])[0]

        candidates = [
            (index, float(item.get("score") or 0))
            for index, item in enumerate(items)
            if str(item.get("source") or "") not in protected_sources
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[1])[0]

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
            self._model = SentenceTransformer(settings.embedding_model, device=self.device)
        return self._model


retrieval_service = RetrievalService()
