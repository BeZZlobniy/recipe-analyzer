from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
DEFAULT_KB_BUNDLE_DIR = Path.home() / "Downloads" / "rag_kb_txt_bundle"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8")

    app_name: str = "Recipe Analyzer MVP"
    secret_key: str = "recipe-analyzer-dev-secret"
    session_cookie_name: str = "recipe_analyzer_session"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'app.db').as_posix()}"
    data_dir: Path = DATA_DIR
    kb_bundle_dir: Path = DEFAULT_KB_BUNDLE_DIR

    demo_username: str = "admin"
    demo_password: str = "admin"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_analysis_model: str = "qwen2.5:7b"
    ollama_analysis_fallback_models: list[str] = Field(default_factory=lambda: ["qwen3.5:4b", "qwen2.5:3b"])
    ollama_normalization_model: str = "qwen2.5:7b"
    ollama_normalization_fallback_models: list[str] = Field(default_factory=lambda: ["qwen3.5:4b", "qwen2.5:3b"])
    ollama_timeout_sec: int = 180
    ollama_analysis_timeout_sec: int = 180
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_device: str = "auto"
    enable_embedding_retrieval: bool = True

    usda_request_timeout_sec: int = 30
    usda_api_key: str = ""
    usda_base_url: str = "https://api.nal.usda.gov/fdc/v1"
    usda_page_size: int = 6
    usda_max_queries_per_ingredient: int = 3
    usda_foundation_dataset_path: Path = DATA_DIR / "FoodData_Central_foundation_food_json_2025-12-18.json"

    def resolve_embedding_device(self) -> str:
        import torch

        requested = self.embedding_device.strip().lower()
        if requested not in {"auto", "cpu", "cuda"}:
            raise ValueError("EMBEDDING_DEVICE must be one of: auto, cpu, cuda")
        if requested == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if requested == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("EMBEDDING_DEVICE is set to cuda, but CUDA is unavailable in this environment.")
        return requested


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
