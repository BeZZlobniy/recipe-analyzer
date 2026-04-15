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
    ollama_normalization_model: str = "qwen2.5:7b"
    ollama_timeout_sec: int = 0
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    enable_embedding_retrieval: bool = False

    rag_top_k: int = 4
    rag_max_queries: int = 10
    enable_web_fallback: bool = False
    web_fallback_timeout_sec: int = 0
    web_fallback_max_calls: int = 4
    usda_api_key: str = ""
    usda_base_url: str = "https://api.nal.usda.gov/fdc/v1"
    usda_page_size: int = 6
    usda_max_queries_per_ingredient: int = 3
    usda_foundation_dataset_path: Path = DATA_DIR / "FoodData_Central_foundation_food_json_2025-12-18.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
