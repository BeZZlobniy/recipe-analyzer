import { useEffect, useMemo, useState } from "react";
import { analysisApi, profilesApi } from "../api";
import type { AnalyzeResponse, Profile } from "../types/api";
import { formatNutrientKey, formatNutrientUnit } from "../utils/labels";

export function NewAnalysisPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState<number | null>(null);
  const [recipeText, setRecipeText] = useState("");
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [portions, setPortions] = useState(1);

  useEffect(() => {
    void profilesApi.list().then((items) => {
      setProfiles(items);
      if (items[0]) {
        setProfileId(items[0].id);
      }
    });
  }, []);

  const activeProfile = profiles.find((profile) => profile.id === profileId) ?? null;
  const visibleWarnings = useMemo(
    () => (result?.warnings ?? []).filter((item) => !/^Что учитывать:|^Тема:|^Рекомендации:/i.test(item)),
    [result],
  );

  const analyze = async () => {
    if (!profileId) {
      setError("Сначала создайте или выберите профиль");
      return;
    }
    setPending(true);
    setError("");
    try {
      const payload = await analysisApi.analyze({ profile_id: profileId, recipe_text: recipeText });
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось выполнить анализ");
    } finally {
      setPending(false);
    }
  };

  const sodiumByTaste = hasSaltByTaste(result);

  return (
    <div className="page">
      <h1>Новый анализ</h1>
      <div className="grid twoCols">
        <div className="card">
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
          <textarea className="recipeInput" value={recipeText} onChange={(event) => setRecipeText(event.target.value)} placeholder="Вставьте свободный текст рецепта..." />
          {error ? <div className="errorBox">{error}</div> : null}
          <button onClick={() => void analyze()} disabled={pending || !recipeText.trim()}>
            {pending ? "Анализ..." : "Проанализировать"}
          </button>
        </div>

        <div className="card">
          <h3>Последний результат</h3>
          {!result ? <div className="muted">Запустите анализ, чтобы увидеть результат</div> : null}
          {result ? (
            <div className="resultPreview">
              <strong>{result.title}</strong>
              <p>{result.summary}</p>
              <div className="list">
                <div className="listRow"><strong>Профиль:</strong><span>{activeProfile?.name ?? "не выбран"}</span></div>
                <div className="listRow"><strong>Тип питания:</strong><span>{activeProfile?.diet_type ?? "не задан"}</span></div>
                <div className="listRow"><strong>Цель:</strong><span>{activeProfile?.goal ?? "не задана"}</span></div>
                <div className="listRow"><strong>Аллергии:</strong><span>{activeProfile?.allergies_json?.length ? activeProfile.allergies_json.join(", ") : "нет"}</span></div>
                <div className="listRow"><strong>Ограничения:</strong><span>{activeProfile?.restrictions_text || "не заданы"}</span></div>
              </div>
              <div className="rowBetween">
                <h4>Пищевая ценность</h4>
                <strong>{portions} {pluralizePortions(portions)}</strong>
              </div>
              <input type="range" min="1" max="10" value={portions} onChange={(event) => setPortions(Number(event.target.value))} />
              <ul>
                {Object.entries(result.nutrition_total).map(([key, value]) => (
                  <li key={key}>
                    {formatDisplayLabel(key, sodiumByTaste)}: {formatNutritionValue(key, value.value / portions, sodiumByTaste)} {formatDisplayUnit(key, sodiumByTaste)}
                  </li>
                ))}
              </ul>
              <h4>Проблемы</h4>
              {result.detected_issues.length > 0 ? <ul>{result.detected_issues.map((issue) => <li key={issue}>{issue}</li>)}</ul> : <div className="muted">Явных проблем не выявлено</div>}
              <h4>Рекомендации</h4>
              <ul>{result.recommendations.map((item) => <li key={item}>{item}</li>)}</ul>
              {visibleWarnings.length > 0 ? (
                <>
                  <h4>Предупреждения</h4>
                  <ul>{visibleWarnings.map((item) => <li key={item}>{item}</li>)}</ul>
                </>
              ) : null}
            </div>
          ) : null}
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

function hasSaltByTaste(result: AnalyzeResponse | null) {
  return Boolean(
    result?.detailed_ingredients?.some((item) => {
      const ingredient = item.ingredient as { name_canonical?: string; amount_text?: string } | undefined;
      return ingredient?.name_canonical === "соль" && ingredient?.amount_text === "по вкусу";
    }),
  );
}

function formatNutritionValue(key: string, value: number, sodiumByTaste: boolean) {
  if (key === "sodium" && sodiumByTaste) {
    return "по вкусу";
  }
  return Number(value.toFixed(2));
}

function formatDisplayLabel(key: string, sodiumByTaste: boolean) {
  if (key === "sodium" && sodiumByTaste) {
    return "Соль";
  }
  return formatNutrientKey(key);
}

function formatDisplayUnit(key: string, sodiumByTaste: boolean) {
  if (key === "sodium" && sodiumByTaste) {
    return "";
  }
  return formatNutrientUnit(key);
}
