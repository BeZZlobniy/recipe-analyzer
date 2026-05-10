# Recipe Analyzer

Локальное веб-приложение для персонализированного анализа рецептов. Система разбирает рецепт из свободного текста, сопоставляет ингредиенты с USDA FoodData Central, рассчитывает КБЖУ и формирует RAG-анализ с учетом профиля пользователя: цели, типа питания, аллергий, заболеваний, предпочтений и дополнительных ограничений.

## Возможности

- Разбор рецепта из текста: название, порции, ингредиенты, количества, единицы измерения и шаги приготовления.
- Нормализация русскоязычных ингредиентов через Qwen/Ollama с резервным эвристическим парсером.
- Перевод ингредиентов на английский для поиска в USDA без простой транслитерации.
- Сопоставление с локальным USDA Foundation dataset и опциональным USDA API.
- Расчет калорий, белков, жиров, углеводов, клетчатки и натрия.
- Персонализация через RAG-слой, а не только через rule-based проверки.
- Отдельные блоки итоговой оценки: цель, аллергии, заболевания, предпочтения, тип питания и ограничения.
- Рекомендация целого количества порций: `1 порция = весь рецепт`, `2 порции = рецепт / 2` и так далее.
- История анализов, подробная страница результата, dashboard и графики.
- Тестовые профили и 20 тестовых рецептов для массового прогона.
- Поддержка GPU для embeddings через `EMBEDDING_DEVICE=auto|cuda|cpu`.

## Архитектура Анализа

1. `input_cleaner` очищает текст рецепта от лишнего шума.
2. `fallback_parser` строит устойчивый базовый разбор рецепта.
3. Qwen через Ollama уточняет структуру рецепта и `name_en` для USDA.
4. `normalization.py` объединяет LLM-результат и эвристику, чтобы не терять количества.
5. `ingredient_resolution.py` ищет USDA-кандидатов, ранжирует их и при необходимости просит Qwen выбрать лучший продукт.
6. `nutrition.py` считает нутриенты и метрики качества сопоставления.
7. `portions.py` подбирает рекомендуемое число порций под целевые калории.
8. `retrieval.py` извлекает релевантный контекст из локальной базы знаний.
9. `rag/service.py` формирует сегментированный персонализированный вывод.

Крупные prompt-шаблоны для Qwen лежат в `backend/app/services/qwen_prompts.py`. Контекстные знания для RAG лежат в `backend/app/data/kb_sources`. Резервные справочники вынесены в JSON-файлы в `backend/app/data/fallback`.

## Стек

- Backend: FastAPI, SQLAlchemy, SQLite, Pydantic.
- Frontend: React, TypeScript, Vite.
- LLM: Ollama, по умолчанию `qwen2.5:7b`.
- Embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Nutrition source: локальный USDA Foundation JSON + опциональный USDA API.
- Tests: pytest, TypeScript build.

## Быстрый Запуск

```powershell
.\setup-app.ps1
.\run-app.ps1
```

Скрипт установки создает Python venv, ставит backend/frontend зависимости, копирует `backend/.env.example` в `backend/.env` и при наличии NVIDIA GPU пытается поставить CUDA-сборку PyTorch.

Адреса после запуска:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Demo login: `admin` / `admin`

## Ручной Запуск

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Для LLM нужен запущенный Ollama и модель:

```powershell
ollama pull qwen2.5:7b
ollama serve
```

## Настройки

Основные переменные в `backend/.env`:

```env
SECRET_KEY=recipe-analyzer-dev-secret
DATABASE_URL=sqlite:///./app.db
CORS_ORIGINS=["http://localhost:5173"]

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_ANALYSIS_MODEL=qwen2.5:7b
OLLAMA_ANALYSIS_FALLBACK_MODELS=["qwen3.5:4b","qwen2.5:3b"]
OLLAMA_NORMALIZATION_MODEL=qwen2.5:7b
OLLAMA_NORMALIZATION_FALLBACK_MODELS=["qwen3.5:4b","qwen2.5:3b"]
OLLAMA_TIMEOUT_SEC=180
OLLAMA_ANALYSIS_TIMEOUT_SEC=180

EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DEVICE=auto
ENABLE_EMBEDDING_RETRIEVAL=true

USDA_REQUEST_TIMEOUT_SEC=30
USDA_API_KEY=your_usda_api_key
```

`EMBEDDING_DEVICE=auto` выбирает CUDA, если PyTorch видит GPU, иначе CPU. Для жесткого требования GPU укажите `EMBEDDING_DEVICE=cuda`: приложение упадет при старте, если CUDA недоступна.

`USDA_API_KEY` необязателен. Без него используется локальный Foundation dataset; API нужен как внешний источник кандидатов, если локальный поиск недостаточен.

## Демо-Данные

При старте backend выполняется `bootstrap_database()`:

- Создается demo user `admin`.
- Создаются 5 тестовых профилей с разными целями, аллергиями, заболеваниями и типами питания.
- Собирается `knowledge_base.json` из файлов `backend/app/data/kb_sources`.
- Локальный каталог продуктов пополняется по мере анализа через USDA resolution/cache.

Тестовые рецепты для прогонов лежат в `backend/app/data/recipes/1.txt` ... `20.txt`.

## Полезные Скрипты

Из папки `backend`:

```powershell
.\.venv\Scripts\python.exe scripts\run_recipe_suite.py --indexes 8,13,17,19,20 --matrix --no-save-db --output reports\recipe_suite_complex_smoke.json
```

Прогоняет выбранные рецепты по тестовым профилям и сохраняет JSON-отчет с метриками качества, fallback и RAG.

```powershell
.\.venv\Scripts\python.exe scripts\run_recipe_suite.py --limit 20 --matrix --output reports\recipe_suite_latest.json
```

Полный прогон 20 рецептов по профилям. Используется для оценки качества анализа и персонализации.

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_local_ai.py
```

Проверяет скорость embeddings/Ollama и фактическое устройство (`cpu`/`cuda`).

```powershell
.\.venv\Scripts\python.exe scripts\generate_thesis_artifacts.py
```

Генерирует таблицы и графики для отчетности в `backend/reports/thesis`.

`scripts/cli_analyze.py` оставлен как CLI-сценарий для анализа рецепта без frontend.

## Проверки

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m py_compile app/services/qwen_prompts.py app/services/ollama_service.py app/modules/rag/service.py app/core/config.py
.\.venv\Scripts\python.exe -m pytest tests
```

Frontend:

```powershell
cd frontend
npm run build
```

Последний контрольный smoke-прогон: 5 сложных рецептов x 5 профилей = 25 анализов, `heuristic_fallback_ratio = 0.0`, `unresolved_ratio = 0.0`, `degraded_count = 0`.

## Структура

```text
recipe-analyzer/
  README.md
  setup-app.ps1
  run-app.ps1
  run-app.bat

  backend/
    requirements.txt
    pytest.ini
    .env.example

    app/
      main.py

      api/routes/
        auth.py
        profiles.py
        analyze.py
        history.py
        dashboard.py

      core/
        config.py
        db.py
        deps.py
        schemas.py
        security.py
        utils.py

      data/
        recipes/
          1.txt ... 20.txt
        fallback/
          ingredient_catalog.json
          nutrition_fallbacks.json
          parser_fallbacks.json
          personalization_aliases.json
        kb_sources/
        FoodData_Central_foundation_food_json_2025-12-18.json
        knowledge_base.json

      models/
        user.py
        profile.py
        recipe_analysis.py
        product.py
        external_lookup_cache.py

      modules/
        analysis/
          service.py
          nutrition.py
          nutrition_rules.py
          personalization.py
          portions.py

        rag/
          normalization.py
          ingredient_catalog.py
          ingredient_resolution.py
          retrieval.py
          service.py
          usda_client.py
          usda_resolution_utils.py

        structuring/
          input_cleaner.py
          fallback_parser.py
          schemas.py

      services/
        ollama_service.py
        qwen_prompts.py
        kb_catalog_service.py

    scripts/
      cli_analyze.py
      run_recipe_suite.py
      benchmark_local_ai.py
      generate_thesis_artifacts.py

    tests/
      integration/
      unit/

  frontend/
    package.json
    vite.config.ts
    src/
      api/
      auth/
      components/
      pages/
      types/
      utils/
      App.tsx
      main.tsx
      styles.css
```

## Что Не Коммитить

Обычно не нужно включать в VCS:

- `backend/.env`
- `backend/.venv/`
- `frontend/node_modules/`
- `backend/reports/`
- локальные SQLite базы (`*.db`, `*.sqlite`)
- сгенерированные embedding-артефакты `knowledge_base_embeddings.npy` и `knowledge_base_embeddings_meta.json`

