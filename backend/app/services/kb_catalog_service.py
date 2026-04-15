from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from app.core.config import settings
from app.core.utils import ensure_data_dir, maybe_fix_mojibake, normalize_spaces, normalize_text


class KnowledgeBaseCatalogService:
    EXPECTED_FILES = [
        "kb_common_allergens.txt",
        "kb_cooking_method_health_impact.txt",
        "kb_diabetes.txt",
        "kb_gluten_free.txt",
        "kb_hidden_allergen_sources.txt",
        "kb_high_protein.txt",
        "kb_hyperlipidemia.txt",
        "kb_hypertension.txt",
        "kb_lactose_intolerance.txt",
        "kb_low_carb.txt",
        "kb_low_sodium.txt",
        "kb_mediterranean_diet.txt",
        "kb_nutrition_thresholds.txt",
        "kb_portion_size_rules.txt",
        "kb_recipe_substitutions.txt",
        "kb_sat_fat_and_sodium_rules.txt",
        "kb_vegan.txt",
        "kb_vegetarian.txt",
        "kb_weight_loss.txt",
    ]

    def __init__(self) -> None:
        self.sources_dir = ensure_data_dir() / "kb_sources"
        self.kb_path = ensure_data_dir() / "knowledge_base.json"
        self.emb_path = ensure_data_dir() / "knowledge_base_embeddings.npy"
        self.meta_path = ensure_data_dir() / "knowledge_base_embeddings_meta.json"

    def ensure_built(self) -> None:
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self._import_bundle_files()
        fingerprint = self._sources_fingerprint()
        current_fingerprint = None
        if self.meta_path.exists():
            try:
                current_fingerprint = json.loads(self.meta_path.read_text(encoding="utf-8")).get("sources_fingerprint")
            except Exception:
                current_fingerprint = None
        if self.kb_path.exists() and fingerprint == current_fingerprint:
            return

        kb_chunks = self._build_chunks()
        self.kb_path.write_text(json.dumps(kb_chunks, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.emb_path.exists():
            self.emb_path.unlink()
        self.meta_path.write_text(
            json.dumps({"sources_fingerprint": fingerprint, "count": len(kb_chunks)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _import_bundle_files(self) -> None:
        bundle_dir = settings.kb_bundle_dir
        if not bundle_dir.exists():
            return
        for filename in self.EXPECTED_FILES:
            source = bundle_dir / filename
            if not source.exists():
                continue
            target = self.sources_dir / filename
            if not target.exists() or source.stat().st_mtime > target.stat().st_mtime:
                shutil.copy2(source, target)

    def _build_chunks(self) -> list[dict]:
        chunks: list[dict] = []
        index = 1
        for path in sorted(self.sources_dir.glob("*.txt")):
            text = maybe_fix_mojibake(path.read_text(encoding="utf-8-sig"))
            parts = self._split_document(str(text))
            tags = self._tags_from_filename(path.name)
            for part in parts:
                chunk_text = normalize_spaces(part)
                if len(chunk_text) < 80:
                    continue
                chunks.append(
                    {
                        "id": f"kb_new_{index}",
                        "source": path.name,
                        "text": chunk_text,
                        "tags": tags,
                    }
                )
                index += 1
        return chunks

    def _split_document(self, text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n")
        blocks = [block.strip() for block in re.split(r"\n\s*\n+", normalized) if block.strip()]
        merged: list[str] = []
        buffer = ""
        for block in blocks:
            block = normalize_spaces(block)
            if not buffer:
                buffer = block
            elif len(buffer) < 280:
                buffer = f"{buffer}\n\n{block}"
            else:
                merged.append(buffer)
                buffer = block
        if buffer:
            merged.append(buffer)
        return merged

    def _tags_from_filename(self, filename: str) -> list[str]:
        base = filename.replace(".txt", "")
        tokens = [token for token in base.split("_") if token not in {"kb", "and"}]
        tags = [normalize_text(token) for token in tokens]
        if "allergens" in base:
            tags.extend(["allergy", "restrictions"])
        if "vegetarian" in base or "vegan" in base:
            tags.extend(["diet"])
        if "nutrition" in base or "fat" in base or "sodium" in base:
            tags.extend(["nutrition"])
        if "cooking" in base or "substitutions" in base:
            tags.extend(["recommendations"])
        return sorted({tag for tag in tags if tag})

    def _sources_fingerprint(self) -> str:
        payload = []
        for path in sorted(self.sources_dir.glob("*.txt")):
            payload.append(f"{path.name}:{path.stat().st_size}:{int(path.stat().st_mtime)}")
        return hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()


kb_catalog_service = KnowledgeBaseCatalogService()
