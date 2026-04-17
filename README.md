# Recipe Analyzer MVP

Локальное веб-приложение для персонализированного анализа рецептов с учетом профиля пользователя.

## Что умеет система

- принимает рецепт в свободной текстовой форме;
- извлекает ингредиенты, количества и единицы измерения;
- сопоставляет ингредиенты с USDA FoodData Central;
- детерминированно рассчитывает калорийность и БЖУ;
- формирует персонализированный аналитический отчет через RAG;
- сохраняет историю анализов и показывает сводную статистику на dashboard.

## Backend pipeline

1. `Normalization`
   - очистка текста рецепта;
   - извлечение ингредиентов;
   - получение `name_ru`, `name_en`, количества и единиц.
2. `Ingredient Resolution`
   - поиск кандидатов сначала в локальном USDA Foundation JSON;
   - fallback в USDA API;
   - ранжирование и выбор наиболее подходящего продукта.
3. `Deterministic Nutrition`
   - перевод количества ингредиента в массу;
   - расчет калорий, белков, жиров, углеводов, клетчатки и натрия;
   - оценка качества анализа.
4. `Final RAG Analysis`
   - извлечение релевантного контекста из локальной базы знаний;
   - генерация summary, warnings, recommendations и compatibility.

## Технологический стек

- `backend`: FastAPI, SQLAlchemy, SQLite
- `frontend`: React, TypeScript, Vite
- `LLM`: Ollama, `qwen2.5:7b`
- `nutrition source`: USDA Foundation JSON + USDA API fallback
- `RAG knowledge base`: локальные `.txt` источники, агрегированные в JSON

## Актуальная структура проекта

```text
recipe-analyzer/
  backend/
    app/
      api/routes/           # REST endpoints
      core/                 # config, db, schemas, utils
      data/                 # USDA dataset, KB, active data
      models/               # SQLAlchemy models
      modules/
        analysis/           # orchestration, nutrition, portions
        rag/                # normalization, resolution, retrieval, final analysis
        structuring/        # fallback parsing and schemas
      services/             # Ollama and KB support services
      main.py
    demo/
      recipes/              # demo recipe texts
      results/              # saved demo analysis JSON
    scripts/                # service scripts and CLI helpers
    user_profiles/          # sample JSON profiles for CLI
    requirements.txt
  frontend/
    src/
      api/                  # API client and request wrappers
      auth/                 # auth context
      components/           # shared visual and layout components
      pages/                # route pages
      types/                # API-facing TS types
      utils/                # labels and formatting helpers
      App.tsx
      main.tsx
      styles.css
    package.json
    tsconfig.json
    vite.config.ts
  run-app.ps1
  setup-app.ps1
```

## Ключевые файлы реализации

### Backend

- `backend/app/modules/analysis/service.py`
- `backend/app/modules/rag/normalization.py`
- `backend/app/modules/rag/ingredient_resolution.py`
- `backend/app/modules/analysis/nutrition.py`
- `backend/app/modules/rag/service.py`

### Frontend

- `frontend/src/App.tsx`
- `frontend/src/auth/AuthContext.tsx`
- `frontend/src/pages/NewAnalysisPage.tsx`
- `frontend/src/pages/AnalysisDetailsPage.tsx`
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/pages/ProfilesPage.tsx`

## Запуск

Быстрый запуск:

```powershell
.\setup-app.ps1
.\run-app.ps1
```

Ручной запуск backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Ручной запуск frontend:

```powershell
cd frontend
npm install
npm run dev
```

## Demo user

- username: `admin`
- password: `admin`

## Demo recipes

В истории анализов сохранены показательные кейсы, а их исходные тексты и JSON-результаты лежат в `backend/demo/`:

1. полезный рецепт с высокой совместимостью;
2. калорийный рецепт с низкой совместимостью по ограничениям и цели;
3. два промежуточных рецепта со средней совместимостью.

## Что использовать в ВКР

Для технологического раздела удобно опираться на:

- backend pipeline и описание модулей;
- структуру БД SQLite;
- интеграцию USDA и локального USDA Foundation JSON;
- использование Ollama и RAG;
- demo-рецепты и сохраненные результаты анализа;
- страницы frontend: профили, новый анализ, детали, история, dashboard;
- метрики качества анализа: `analysis_quality`, `matched_ratio`, `unresolved_ratio`.

Файлы локальных отчетов, временных баз данных и сгенерированных embedding-артефактов в репозиторий не включаются.
