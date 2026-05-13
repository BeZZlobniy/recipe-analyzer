# Recipe Analyzer

Локальное веб-приложение для персонализированного анализа рецептов. Система извлекает ингредиенты из свободного текста, сопоставляет их с USDA FoodData Central, рассчитывает КБЖУ и формирует RAG-отчет с учетом профиля пользователя.

## Возможности

- Разбор рецепта из свободного текста: название, ингредиенты, количества, единицы, шаги.
- Нормализация ингредиентов через Qwen/Ollama с эвристическим резервным парсером.
- Сопоставление ингредиентов с локальным USDA Foundation JSON и, при наличии ключа, USDA API.
- Расчет калорий, белков, жиров, углеводов, клетчатки и натрия.
- Персонализация по цели, типу питания, аллергиям, заболеваниям, предпочтениям и дополнительным ограничениям.
- Отдельный профильный блок анализа: цель, аллергии, заболевания, предпочтения, тип питания и ограничения.
- Рекомендация целого количества порций: `1 порция = весь рецепт`, `2 порции = рецепт / 2` и так далее.
- История анализов, детальный просмотр результата и dashboard.
- Локальная RAG-база знаний из `backend/app/data/kb_sources`.
- Поддержка GPU для embeddings через `EMBEDDING_DEVICE=auto|cuda|cpu`; скрипты установки ставят CUDA PyTorch при наличии NVIDIA GPU.

## Pipeline

1. `input_cleaner` очищает текст рецепта от шума.
2. `fallback_parser` строит устойчивый эвристический разбор рецепта.
3. Qwen через Ollama уточняет структуру рецепта и английские `name_en` для USDA.
4. `normalization.py` объединяет LLM-результат и эвристику, чтобы не терять количества.
5. `ingredient_resolution.py` ищет USDA-кандидатов, ранжирует их и при необходимости просит Qwen выбрать лучший продукт.
6. `nutrition.py` считает нутриенты и метрики качества сопоставления.
7. `portions.py` определяет рекомендуемое количество порций под целевые калории.
8. `retrieval.py` достает RAG-контекст из локальной базы знаний.
9. `rag/service.py` формирует итоговый персонализированный анализ и профильные блоки.

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

Скрипты создают Python venv, ставят backend/frontend зависимости, копируют `backend/.env.example` в `backend/.env`, при наличии NVIDIA GPU ставят CUDA-сборку PyTorch и запускают backend/frontend.

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

## Настройки

Основные переменные в `backend/.env`:

```env
SECRET_KEY=recipe-analyzer-dev-secret
DATABASE_URL=sqlite:///./app.db
CORS_ORIGINS=["http://localhost:5173"]

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_NORMALIZATION_MODEL=qwen2.5:7b
OLLAMA_TIMEOUT_SEC=0

EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DEVICE=auto
ENABLE_EMBEDDING_RETRIEVAL=true

USDA_REQUEST_TIMEOUT_SEC=0
USDA_API_KEY=your_usda_api_key
```

`EMBEDDING_DEVICE=auto` выбирает CUDA, если PyTorch видит GPU, иначе CPU. Для принудительного GPU укажите `EMBEDDING_DEVICE=cuda`; приложение упадет при старте, если CUDA недоступна.

`USDA_API_KEY` не обязателен: без него используется локальный Foundation dataset. API нужен только как внешний источник кандидатов, если локальный поиск слабый.

## Демо-Данные

При старте backend выполняется `bootstrap_database()`:

- Создается demo user `admin`.
- Создаются 5 тестовых профилей: вегетарианец без лактозы, набор массы, контроль сахара, низкая соль, веган без глютена.
- Собирается `knowledge_base.json` из `kb_sources`.
- Локальная база продуктов наполняется по мере анализа через USDA resolution/cache.

Тестовые рецепты для прогонов лежат в `backend/app/data/recipes/1.txt` ... `20.txt`.

## Полезные Скрипты

Из папки `backend`:

```powershell
.\.venv\Scripts\python.exe scripts\run_recipe_suite.py --limit 10
```

Прогоняет рецепты `app/data/recipes/1.txt..10.txt` по демо-профилям и сохраняет отчет в `backend/reports/recipe_suite_latest.json`.

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_recipe_suite.py --report reports\recipe_suite_latest.json
```

Оценивает сохраненный suite-прогон по служебной разметке рецептов и профилей.

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_local_ai.py
```

Проверяет скорость embeddings/Ollama и фактическое устройство (`cpu`/`cuda`).

```powershell
.\.venv\Scripts\python.exe scripts\generate_thesis_artifacts.py
```

Генерирует таблицы и графики для отчетности в `backend/reports/thesis`.

## Проверки

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall app
.\.venv\Scripts\python.exe -m pytest tests
```

Frontend:

```powershell
cd frontend
npm run build
npx tsc -p tsconfig.json --noEmit --noUnusedLocals --noUnusedParameters
```

## Структура

```text
recipe-analyzer/
  README.md
  setup-app.ps1
  run-app.ps1
  run-app.bat
  app.db

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
        FoodData_Central_foundation_food_json_2025-12-18.json
        eval/
          recipe_expectations.json
        fallback/
          ingredient_catalog.json
          nutrition_fallbacks.json
          parser_fallbacks.json
          personalization_aliases.json
        recipes/
          1.txt ... 20.txt
        kb_sources/
        knowledge_base.json
        knowledge_base_embeddings.npy
        knowledge_base_embeddings_meta.json

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
      run_recipe_suite.py
      evaluate_recipe_suite.py
      benchmark_local_ai.py
      generate_thesis_artifacts.py

    tests/
      integration/test_api.py
      unit/test_ingredient_catalog.py
      unit/test_nutrition.py
      unit/test_parsing.py
      unit/test_rag_personalization_guard.py
      unit/test_recipe_analysis_regressions.py
      unit/test_recipe_suite_evaluation.py
      unit/test_usda_resolution_utils.py

    demo/
    reports/

  frontend/
    package.json
    vite.config.ts
    tsconfig.json
    src/
      api/
      auth/
      components/
        Charts.tsx
        Layout.tsx
        ProfileAssessmentPanel.tsx
        ProtectedRoute.tsx
        StatCard.tsx
      pages/
        LoginPage.tsx
        DashboardPage.tsx
        ProfilesPage.tsx
        NewAnalysisPage.tsx
        HistoryPage.tsx
        AnalysisDetailsPage.tsx
      types/api.ts
      utils/
        labels.ts
        nutritionDisplay.ts
        text.ts
      App.tsx
      main.tsx
      styles.css
```

