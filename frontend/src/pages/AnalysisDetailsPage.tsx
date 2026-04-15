import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { analysisApi, profilesApi } from "../api";
import type { AnalysisDetail, Profile } from "../types/api";
import { formatNutrientKey, formatNutrientUnit } from "../utils/labels";

export function AnalysisDetailsPage() {
  const { analysisId } = useParams();
  const [detail, setDetail] = useState<AnalysisDetail | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [portions, setPortions] = useState(1);
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
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить анализ"));
  }, [analysisId]);

  const result = detail?.analysis_result ?? null;
  const profile = profiles.find((item) => item.id === detail?.profile_id) ?? null;
  const visibleWarnings = useMemo(
    () => (result?.warnings ?? []).filter((item) => !/^Что учитывать:|^Тема:|^Рекомендации:/i.test(item)),
    [result],
  );
  const sodiumByTaste = useMemo(
    () =>
      Boolean(
        result?.detailed_ingredients?.some((item) => {
          const ingredient = item.ingredient as { name_canonical?: string; amount_text?: string } | undefined;
          return ingredient?.name_canonical === "соль" && ingredient?.amount_text === "по вкусу";
        }),
      ),
    [result],
  );
  const scaledNutrition = useMemo(
    () =>
      Object.entries(result?.nutrition_total ?? {}).map(([key, value]) => ({
        key,
        value: key === "sodium" && sodiumByTaste ? "по вкусу" : Number((value.value / portions).toFixed(2)),
      })),
    [result, portions, sodiumByTaste],
  );

  if (error) {
    return <div className="page">{error}</div>;
  }

  if (!detail || !result) {
    return <div className="page">Загрузка...</div>;
  }

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
          </div>
        </div>
      </div>

      <div className="grid twoCols">
        <div className="card">
          <h3>Структурированные ингредиенты</h3>
          <ul>{detail.structured_recipe.ingredients.map((item) => <li key={item.name_raw}>{item.name_raw} → {item.name_canonical}</li>)}</ul>
        </div>
        <div className="card">
          <div className="rowBetween">
            <h3>Пищевая ценность</h3>
            <strong>{portions} {pluralizePortions(portions)}</strong>
          </div>
          <label>
            Показать для количества порций
            <input type="range" min="1" max="10" value={portions} onChange={(event) => setPortions(Number(event.target.value))} />
          </label>
          <ul>{scaledNutrition.map((item) => <li key={item.key}>{formatDisplayLabel(item.key, item.value)}: {item.value} {formatDisplayUnit(item.key, item.value)}</li>)}</ul>
        </div>
      </div>

      <div className="grid twoCols">
        <div className="card">
          <h3>Проблемы и рекомендации</h3>
          {result.detected_issues.length > 0 ? <ul>{result.detected_issues.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">Явных проблем не выявлено.</p>}
          <ul>{result.recommendations.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
        <div className="card">
          <h3>Предупреждения</h3>
          {visibleWarnings.length > 0 ? <ul>{visibleWarnings.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">Предупреждений нет.</p>}
        </div>
      </div>
    </div>
  );
}

function pluralizePortions(value: number) {
  const mod10 = value % 10;
  const mod100 = value % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return "порция";
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return "порции";
  }
  return "порций";
}

function formatDisplayLabel(key: string, value: string | number) {
  if (key === "sodium" && value === "по вкусу") {
    return "Соль";
  }
  return formatNutrientKey(key);
}

function formatDisplayUnit(key: string, value: string | number) {
  if (key === "sodium" && value === "по вкусу") {
    return "";
  }
  return formatNutrientUnit(key);
}
