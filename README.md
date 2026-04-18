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
Листинг Б — Актуальная структура приложения

recipe-analyzer/
  README.md                              # общее описание проекта, стек, запуск
  .gitignore                             # исключения Git
  app.db                                 # локальная SQLite БД, создается/обновляется при работе
  setup-app.ps1                          # первичная настройка окружения
  run-app.ps1                            # запуск backend и frontend
  run-app.bat                            # альтернативный запуск в Windows

  backend/
    README.md                            # описание backend-части
    requirements.txt                     # Python-зависимости
    pytest.ini                           # конфигурация pytest

    app/
      main.py                            # create_app(), startup, подключение роутов

      api/
        routes/
          auth.py                        # авторизация: login/logout/me
          profiles.py                    # CRUD профилей пользователя
          analyze.py                     # запуск анализа рецепта
          history.py                     # история и детали анализов
          dashboard.py                   # агрегаты и статистика dashboard

      core/
        config.py                        # настройки приложения, .env, пути, модели, флаги
        db.py                            # engine, SessionLocal, bootstrap_database()
        deps.py                          # зависимости FastAPI, доступ к БД/пользователю
        schemas.py                       # Pydantic-схемы API
        security.py                      # хеширование паролей, работа с auth
        utils.py                         # нормализация текста, вспомогательные функции

      data/
        FoodData_Central_foundation_food_json_2025-12-18.json
                                          # локальный USDA Foundation dataset
        knowledge_base.json              # собранная локальная база знаний для retrieval
        kb_sources/                      # исходные текстовые документы базы знаний
          kb_common_allergens.txt        # распространенные аллергены
          kb_hidden_allergen_sources.txt # скрытые источники аллергенов
          kb_lactose_intolerance.txt     # непереносимость лактозы
          kb_gluten_free.txt             # безглютеновое питание
          kb_diabetes.txt                # диабет и ограничения
          kb_hypertension.txt            # гипертония и натрий
          kb_hyperlipidemia.txt          # липидный профиль и жиры
          kb_low_sodium.txt              # низкосолевая диета
          kb_low_carb.txt                # низкоуглеводное питание
          kb_high_protein.txt            # высокобелковое питание
          kb_mediterranean_diet.txt      # средиземноморская диета
          kb_vegetarian.txt              # вегетарианство
          kb_vegan.txt                   # веганство
          kb_weight_loss.txt             # снижение веса
          kb_nutrition_thresholds.txt    # пороги и ориентиры по нутриентам
          kb_portion_size_rules.txt      # правила интерпретации порций
          kb_recipe_substitutions.txt    # возможные замены ингредиентов
          kb_sat_fat_and_sodium_rules.txt
                                          # насыщенные жиры и натрий
          kb_cooking_method_health_impact.txt
                                          # влияние способа приготовления

      models/
        user.py                          # модель пользователя
        profile.py                       # модель профиля пользователя
        recipe_analysis.py               # модель результата анализа рецепта
        product.py                       # каноническая карточка продукта
        product_alias.py                 # альтернативные названия продукта
        product_search_entry.py          # поисковые ключи продукта
        external_lookup_cache.py         # кэш внешних USDA-запросов

      modules/
        analysis/
          service.py                     # оркестрация backend-пайплайна анализа
          nutrition.py                   # расчет нутриентов и метрик качества
          nutrition_rules.py             # правила перевода единиц, оценка массы, fallback
          portions.py                    # оценка числа порций

        rag/
          normalization.py               # объединение эвристик и LLM-нормализации
          ingredient_catalog.py          # нормализация и англоязычные варианты ингредиентов
          ingredient_resolution.py       # сопоставление ингредиентов с USDA
          usda_client.py                 # работа с USDA API
          usda_resolution_utils.py       # вспомогательная логика ранжирования кандидатов
          retrieval.py                   # lexical/embedding retrieval по knowledge base
          service.py                     # формирование контекста и итогового анализа

        structuring/
          input_cleaner.py               # очистка входного текста рецепта
          fallback_parser.py             # эвристический разбор рецепта
          schemas.py                     # внутренние структуры SimpleRecipe/StructuredRecipe

      services/
        ollama_service.py                # взаимодействие с Ollama / Qwen
        kb_catalog_service.py            # сборка knowledge_base.json из kb_sources

    scripts/
      cli_analyze.py                     # CLI-запуск анализа рецепта
      generate_thesis_artifacts.py       # генерация артефактов для ВКР

    tests/
      conftest.py                        # тестовые фикстуры
      integration/
        test_api.py                      # интеграционные тесты API-сценариев
      unit/
        test_parsing.py                  # unit-тесты парсинга рецепта
        test_nutrition.py                # unit-тесты расчета нутриентов

    user_profiles/
      sample_user.json                   # пример профиля для CLI/демо

    reports/                             # локально генерируемые отчеты (обычно не versioned)

  frontend/
    index.html                           # HTML-шаблон Vite
    package.json                         # зависимости и npm-скрипты
    package-lock.json                    # lockfile npm
    tsconfig.json                        # базовая TS-конфигурация
    tsconfig.app.json                    # TS-конфигурация приложения
    vite.config.ts                       # конфигурация Vite

    src/
      main.tsx                           # точка входа frontend
      App.tsx                            # маршрутизация приложения
      styles.css                         # глобальные стили

      api/
        client.ts                        # базовый HTTP-клиент
        index.ts                         # функции работы с backend API

      auth/
        AuthContext.tsx                  # контекст аутентификации и сессии

      components/
        Layout.tsx                       # общий layout приложения
        ProtectedRoute.tsx               # защита приватных маршрутов
        StatCard.tsx                     # карточки статистики
        Charts.tsx                       # визуализация агрегированных данных

      pages/
        LoginPage.tsx                    # страница входа
        DashboardPage.tsx                # dashboard и сводная аналитика
        ProfilesPage.tsx                 # управление профилями
        NewAnalysisPage.tsx              # запуск нового анализа
        HistoryPage.tsx                  # история анализов
        AnalysisDetailsPage.tsx          # детальный просмотр результата

      types/
        api.ts                           # TypeScript-типы API

      utils/
        labels.ts                        # подписи, отображение служебных значений

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


Файлы локальных отчетов, временных баз данных и сгенерированных embedding-артефактов в репозиторий не включаются.
