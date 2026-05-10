import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { analysisApi, profilesApi } from "../api";
import { ProfileAssessmentPanel } from "../components/ProfileAssessmentPanel";
import type { AnalysisDetail, DetailedIngredient, Profile } from "../types/api";
import {
  buildDisplayedNutrition,
  clampDivisor,
  formatDisplayLabel,
  formatDisplayUnit,
  formatRecipeDivisor,
  getInitialRecipeDivisor,
  getRecipeDivisorMax,
  hasSaltByTaste,
} from "../utils/nutritionDisplay";
import { isUserFacingWarning, uniqueTextList } from "../utils/text";

export function AnalysisDetailsPage() {
  const { analysisId } = useParams();
  const [detail, setDetail] = useState<AnalysisDetail | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [portionDivisor, setPortionDivisor] = useState(1);
  const [error, setError] = useState("");

  useEffect(() => {
    void profilesApi.list().then(setProfiles).catch(() => setProfiles([]));
  }, []);

  useEffect(() => {
    if (!analysisId) {
      return;
    }
    void analysisApi
      .historyItem(Number(analysisId))
      .then((payload) => {
        setDetail(payload);
        setPortionDivisor(getInitialRecipeDivisor(payload.analysis_result));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить анализ"));
  }, [analysisId]);

  const result = detail?.analysis_result ?? null;
  const profile = profiles.find((item) => item.id === detail?.profile_id) ?? null;
  const visibleWarnings = useMemo(
    () => (result?.warnings ?? []).filter(isUserFacingWarning),
    [result],
  );
  const sodiumByTaste = useMemo(() => hasSaltByTaste(result), [result]);
  const displayedNutrition = useMemo(
    () => buildDisplayedNutrition(result, portionDivisor, sodiumByTaste),
    [result, portionDivisor, sodiumByTaste],
  );
  const keyIssues = useMemo(
    () => uniqueTextList(result?.detected_issues ?? []).filter((item) => !/^Явных конфликтов/i.test(item)),
    [result],
  );
  const keyRecommendations = useMemo(() => {
    const portionSummary = result?.portion_guidance?.summary ?? "";
    return uniqueTextList(result?.recommendations ?? []).filter((item) => item !== portionSummary);
  }, [result]);

  if (error) {
    return <div className="page">{error}</div>;
  }

  if (!detail || !result) {
    return <div className="page">Загрузка...</div>;
  }

  const maxDivisor = getRecipeDivisorMax(result);
  const portionSummary = result.portion_guidance?.summary;
  const showPortionSummary = Boolean(portionSummary && !result.summary.includes(portionSummary));

  return (
    <div className="page">
      <h1>{detail.title}</h1>
      <div className="grid twoCols">
        <div className="card">
          <h3>Исходный рецепт</h3>
          <pre className="preBlock">{detail.recipe_text}</pre>
        </div>
        <div className="card">
          <h3>Краткий вывод</h3>
          <p>{result.summary}</p>
          <div className="list">
            <div className="listRow"><strong>Профиль:</strong><span>{profile?.name ?? "не найден"}</span></div>
            <div className="listRow"><strong>Тип питания:</strong><span>{profile?.diet_type ?? "не задан"}</span></div>
            <div className="listRow"><strong>Цель:</strong><span>{profile?.goal ?? "не задана"}</span></div>
            <div className="listRow"><strong>Аллергии:</strong><span>{profile?.allergies_json?.length ? profile.allergies_json.join(", ") : "нет"}</span></div>
            <div className="listRow"><strong>Заболевания:</strong><span>{profile?.diseases_json?.length ? profile.diseases_json.join(", ") : "нет"}</span></div>
            <div className="listRow"><strong>Ограничения:</strong><span>{profile?.restrictions_text || "не заданы"}</span></div>
            <div className="listRow"><strong>Базовое деление рецепта:</strong><span>{formatRecipeDivisor(result.portion_guidance?.estimated_recipe_servings ?? 1)}</span></div>
            <div className="listRow"><strong>Рекомендуемое деление:</strong><span>{formatRecipeDivisor(getInitialRecipeDivisor(result))}</span></div>
            {result.target_recipe_calories ? (
              <div className="listRow"><strong>Целевые калории:</strong><span>{result.target_recipe_calories} ккал</span></div>
            ) : null}
          </div>
          {showPortionSummary ? <div className="muted">{portionSummary}</div> : null}
        </div>
      </div>

      {result.profile_assessment ? <ProfileAssessmentPanel assessment={result.profile_assessment} /> : null}

      <div className="grid twoCols">
        <div className="card">
          <h3>Структурированные ингредиенты</h3>
          {result.detailed_ingredients.length > 0 ? (
            <div className="ingredientList">
              {result.detailed_ingredients.map((item, index) => (
                <div className="ingredientCard" key={`${item.ingredient.name_canonical}-${index}`}>
                  <div className="ingredientHeader">
                    <strong>{item.ingredient.name_raw} → {item.ingredient.name_canonical}</strong>
                    <span className={`pill ${item.match_confidence ?? "medium"}`}>{item.match_confidence ?? "medium"}</span>
                  </div>
                  <div className="muted">
                    Использовано в анализе: {item.matched_name || "не сопоставлено"}{typeof item.estimated_grams === "number" ? `, ${item.estimated_grams.toFixed(2)} г` : ""}
                  </div>
                  <div className="ingredientNutritionGrid">
                    <div><span>Ккал</span><strong>{formatIngredientNutrient(item, "calories")}</strong></div>
                    <div><span>Белки</span><strong>{formatIngredientNutrient(item, "protein")} г</strong></div>
                    <div><span>Жиры</span><strong>{formatIngredientNutrient(item, "fat")} г</strong></div>
                    <div><span>Углеводы</span><strong>{formatIngredientNutrient(item, "carbs")} г</strong></div>
                    <div><span>Клетчатка</span><strong>{formatIngredientNutrient(item, "fiber")} г</strong></div>
                    <div><span>Натрий</span><strong>{formatIngredientNutrient(item, "sodium")} мг</strong></div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">Детализация ингредиентов недоступна.</p>
          )}
        </div>
        <div className="card">
          <div className="rowBetween">
            <h3>Пищевая ценность</h3>
            <strong>{formatRecipeDivisor(portionDivisor)}</strong>
          </div>
          <label>
            Показать значения, если разделить рецепт на
            <input
              type="range"
              min="1"
              max={String(maxDivisor)}
              step="1"
              value={portionDivisor}
              onChange={(event) => setPortionDivisor(Number(event.target.value))}
            />
          </label>
          <div className="portionInputRow">
            <input
              type="number"
              min="1"
              max={String(maxDivisor)}
              step="1"
              value={portionDivisor}
              onChange={(event) => setPortionDivisor(clampDivisor(event.target.value, maxDivisor))}
            />
            <span className="muted">1 порция = 1/{portionDivisor} рецепта</span>
          </div>
          <div className="nutritionGrid">
            {displayedNutrition.map((item) => (
              <div className="nutritionTile" key={item.key}>
                <span>{formatDisplayLabel(item.key, item.value)}</span>
                <strong>{item.value} {formatDisplayUnit(item.key, item.value)}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid twoCols">
        <div className="card">
          <h3>Проблемы и рекомендации</h3>
          <h4>Проблемы</h4>
          {keyIssues.length > 0 ? (
            <ul>{keyIssues.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : (
            <p className="muted">Явных проблем не выявлено.</p>
          )}
          <h4>Рекомендации</h4>
          {keyRecommendations.length > 0 ? (
            <ul>{keyRecommendations.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : (
            <p className="muted">Дополнительных рекомендаций нет.</p>
          )}
        </div>
        <div className="card">
          <h3>Предупреждения</h3>
          {visibleWarnings.length > 0 ? (
            <ul>{visibleWarnings.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : (
            <p className="muted">Предупреждений нет.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function formatIngredientNutrient(item: DetailedIngredient, key: "calories" | "protein" | "fat" | "carbs" | "fiber" | "sodium") {
  const value = item.nutrients?.[key];
  return typeof value === "number" ? value.toFixed(2) : "—";
}
