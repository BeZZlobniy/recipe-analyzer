import { useEffect, useMemo, useState } from "react";
import { analysisApi, profilesApi } from "../api";
import { ProfileAssessmentPanel } from "../components/ProfileAssessmentPanel";
import type { AnalyzeResponse, Profile } from "../types/api";
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

export function NewAnalysisPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState<number | null>(null);
  const [recipeText, setRecipeText] = useState("");
  const [targetRecipeCalories, setTargetRecipeCalories] = useState("");
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [portionDivisor, setPortionDivisor] = useState(1);

  useEffect(() => {
    void profilesApi
      .list()
      .then((items) => {
        setProfiles(items);
        if (items[0]) {
          setProfileId(items[0].id);
        }
      })
      .catch(() => setProfiles([]));
  }, []);

  const activeProfile = profiles.find((profile) => profile.id === profileId) ?? null;
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

  const analyze = async () => {
    if (!profileId) {
      setError("Сначала создайте или выберите профиль");
      return;
    }

    setPending(true);
    setError("");
    try {
      const payload = await analysisApi.analyze({
        profile_id: profileId,
        recipe_text: recipeText,
        target_recipe_calories: parsePositiveNumber(targetRecipeCalories),
      });
      setResult(payload);
      setPortionDivisor(getInitialRecipeDivisor(payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось выполнить анализ");
    } finally {
      setPending(false);
    }
  };

  const maxDivisor = getRecipeDivisorMax(result);
  const recommendedDivisor = getInitialRecipeDivisor(result);
  const recommendedCalories =
    result?.portion_guidance?.calories_per_recommended_serving ??
    result?.nutrition_per_serving?.calories?.value ??
    null;

  return (
    <div className="page analysisPage">
      <div className="pageHeader">
        <div>
          <h1>Новый анализ</h1>
          <p className="muted">Вставьте рецепт, выберите профиль и при необходимости задайте целевые калории на одну порцию рецепта.</p>
        </div>
      </div>

      <div className="grid analysisComposerGrid">
        <div className="card analysisInputCard">
          <div className="rowBetween">
            <h3>Текст рецепта</h3>
            <select value={profileId ?? ""} onChange={(event) => setProfileId(Number(event.target.value))}>
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name}
                </option>
              ))}
            </select>
          </div>
          <div className="muted">Активный профиль: {activeProfile?.name ?? "не выбран"}</div>
          <label>
            Целевые калории на рецепт
            <input
              type="number"
              min="1"
              step="1"
              value={targetRecipeCalories}
              onChange={(event) => setTargetRecipeCalories(event.target.value)}
              placeholder="Например, 700"
            />
          </label>
          <textarea
            className="recipeInput"
            value={recipeText}
            onChange={(event) => setRecipeText(event.target.value)}
            placeholder="Вставьте свободный текст рецепта..."
          />
          {error ? <div className="errorBox">{error}</div> : null}
          <button onClick={() => void analyze()} disabled={pending || !recipeText.trim()}>
            {pending ? "Анализ..." : "Проанализировать"}
          </button>
        </div>

        <aside className="card analysisProfileCard">
          <h3>Профиль анализа</h3>
          <div className="list compactList">
            <div className="listRow"><strong>Профиль</strong><span>{activeProfile?.name ?? "не выбран"}</span></div>
            <div className="listRow"><strong>Тип питания</strong><span>{activeProfile?.diet_type ?? "не задан"}</span></div>
            <div className="listRow"><strong>Цель</strong><span>{activeProfile?.goal ?? "не задана"}</span></div>
            <div className="listRow"><strong>Аллергии</strong><span>{activeProfile?.allergies_json?.length ? activeProfile.allergies_json.join(", ") : "нет"}</span></div>
            <div className="listRow"><strong>Заболевания</strong><span>{activeProfile?.diseases_json?.length ? activeProfile.diseases_json.join(", ") : "нет"}</span></div>
            <div className="listRow"><strong>Ограничения</strong><span>{activeProfile?.restrictions_text || "не заданы"}</span></div>
          </div>
        </aside>
      </div>

      {!result ? (
        <div className="card emptyResultCard">
          <h3>Результат появится здесь</h3>
          <p className="muted">После анализа здесь будет краткий вывод, рекомендуемое деление рецепта, профильная оценка, КБЖУ и список проблем без лишнего дублирования.</p>
        </div>
      ) : null}

      {result ? (
        <section className="analysisResultStack">
          <div className="card resultHero">
            <div>
              <span className="eyebrow">Результат анализа</span>
              <h2>{result.title}</h2>
              <p>{result.summary}</p>
            </div>
            <div className="resultMetricGrid">
              <div className="metricTile">
                <span>Рекомендовано</span>
                <strong>{formatRecipeDivisor(recommendedDivisor)}</strong>
              </div>
              <div className="metricTile">
                <span>Ккал / порцию</span>
                <strong>{formatMetricNumber(recommendedCalories)}</strong>
              </div>
              <div className="metricTile">
                <span>Качество</span>
                <strong>{formatMetricNumber(result.analysis_quality?.score as number | undefined)}</strong>
              </div>
            </div>
          </div>

          {result.profile_assessment ? <ProfileAssessmentPanel assessment={result.profile_assessment} /> : null}

          <div className="grid resultDetailGrid">
            <div className="card">
              <div className="rowBetween">
                <h3>Пищевая ценность</h3>
                <strong>{formatRecipeDivisor(portionDivisor)}</strong>
              </div>
              <label>
                Показать значения, если разделить весь рецепт на
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

            <div className="card">
              <h3>Проблемы и рекомендации</h3>
              <h4>Проблемы</h4>
              {keyIssues.length > 0 ? (
                <ul>{keyIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
              ) : (
                <div className="muted">Явных проблем не выявлено</div>
              )}

              <h4>Рекомендации</h4>
              {keyRecommendations.length > 0 ? (
                <ul>{keyRecommendations.map((item) => <li key={item}>{item}</li>)}</ul>
              ) : (
                <div className="muted">Дополнительных рекомендаций нет.</div>
              )}

              {visibleWarnings.length > 0 ? (
                <>
                  <h4>Технические предупреждения</h4>
                  <ul>{visibleWarnings.map((item) => <li key={item}>{item}</li>)}</ul>
                </>
              ) : null}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function parsePositiveNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  const numeric = Number(trimmed);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : undefined;
}

function formatMetricNumber(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(value % 1 === 0 ? 0 : 1) : "—";
}
