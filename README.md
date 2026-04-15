# Recipe Analyzer MVP

Локальное MVP веб-приложения для персонализированного анализа рецептов с учетом пользовательского профиля.

## Что реализовано

Система принимает свободный текст рецепта, преобразует его в структурированную форму, сопоставляет ингредиенты с пищевыми данными, рассчитывает ориентировочную пищевую ценность и формирует аналитический отчет с учетом профиля пользователя.

## Актуальная архитектура backend

Backend работает по конвейеру:

1. `Normalization`
   - очистка текста рецепта;
   - извлечение названия блюда;
   - выделение ингредиентов, количеств и единиц измерения;
   - получение `name_en` для дальнейшего поиска по USDA.

2. `Ingredient Resolution`
   - построение поисковых запросов для каждого ингредиента;
   - поиск кандидатов сначала в локальном USDA Foundation JSON, затем через USDA API;
   - ранжирование кандидатов;
   - при необходимости LLM-разрешение неоднозначности.

3. `Deterministic Nutrition`
   - расчет массы ингредиентов;
   - расчет БЖУ и калорийности;
   - вычисление показателей на весь рецепт и на порцию;
   - оценка качества анализа.

4. `Final RAG Analysis`
   - извлечение релевантного контекста из базы знаний;
   - генерация краткого вывода, предупреждений и рекомендаций;
   - оценка совместимости рецепта с типом питания, ограничениями и целью.

## Технологический стек

- `backend/`: FastAPI, SQLAlchemy, SQLite
- `frontend/`: Vite, React, TypeScript
- `LLM`: Ollama, `qwen2.5:7b`
- `nutrition source`: USDA Foundation JSON + USDA API fallback
- `knowledge base`: локальные TXT-источники, агрегированные в JSON

## Структура проекта

```text
recipe-analyzer/
  backend/
    app/
      api/
      core/
      data/
      models/
      modules/
        analysis/
        rag/
        structuring/
      services/
      main.py
    app.db
    requirements.txt
  frontend/
    src/
```

## Запуск

Быстрый запуск:

```powershell
.\setup-app.ps1
.\run-app.ps1
```

Или вручную:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```powershell
cd frontend
npm install
npm run dev
```

## Demo user

- username: `admin`
- password: `admin`

## Демонстрационные рецепты

В истории анализов сохранены четыре показательных кейса:

1. полезный рецепт с высокой совместимостью;
2. калорийный и “вредный” рецепт с низкой совместимостью по ограничениям и цели;
3. рецепт со средней совместимостью по ограничениям и цели;
4. еще один рецепт со средней совместимостью по ограничениям и цели.

## Ключевые файлы реализации

- [backend/app/modules/analysis/service.py](backend/app/modules/analysis/service.py)
- [backend/app/modules/rag/normalization.py](backend/app/modules/rag/normalization.py)
- [backend/app/modules/rag/ingredient_resolution.py](backend/app/modules/rag/ingredient_resolution.py)
- [backend/app/modules/analysis/nutrition.py](backend/app/modules/analysis/nutrition.py)
- [backend/app/modules/rag/service.py](backend/app/modules/rag/service.py)
- [frontend/src/pages/NewAnalysisPage.tsx](frontend/src/pages/NewAnalysisPage.tsx)
- [frontend/src/pages/AnalysisDetailsPage.tsx](frontend/src/pages/AnalysisDetailsPage.tsx)
- [frontend/src/pages/DashboardPage.tsx](frontend/src/pages/DashboardPage.tsx)

## Что важно для ВКР

Для технологического раздела удобно опираться на следующие артефакты:

- backend pipeline и описание модулей;
- структура БД SQLite;
- описание интеграции USDA;
- описание использования LLM и RAG;
- демонстрационные рецепты и сохраненные результаты анализа;
- скриншоты страниц frontend;
- метрики качества анализа (`analysis_quality`, `matched_ratio`, `unresolved_ratio`);
- сравнение показательных рецептов по совместимости и пищевой ценности.
