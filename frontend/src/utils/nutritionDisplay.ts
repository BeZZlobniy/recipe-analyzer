import type { AnalyzeResponse } from "../types/api";
import { formatNutrientKey, formatNutrientUnit } from "./labels";

const SODIUM_BY_TASTE = "по вкусу";

export function hasSaltByTaste(result: AnalyzeResponse | null) {
  return Boolean(
    result?.detailed_ingredients?.some((item) => {
      const ingredient = item.ingredient;
      return ingredient?.name_canonical === "соль" && ingredient?.amount_text === SODIUM_BY_TASTE;
    }),
  );
}

export function buildDisplayedNutrition(result: AnalyzeResponse | null, divisor: number, sodiumByTaste: boolean) {
  return Object.entries(result?.nutrition_total ?? {}).map(([key, value]) => ({
    key,
    value: key === "sodium" && sodiumByTaste ? SODIUM_BY_TASTE : Number((value.value / Math.max(divisor, 1)).toFixed(2)),
  }));
}

export function getInitialRecipeDivisor(result: AnalyzeResponse | null) {
  return Math.max(result?.portion_guidance?.recommended_recipe_servings ?? result?.servings ?? 1, 1);
}

export function getRecipeDivisorMax(result: AnalyzeResponse | null) {
  const recommended = getInitialRecipeDivisor(result);
  const estimated = result?.portion_guidance?.estimated_recipe_servings ?? 1;
  return Math.max(8, recommended + 4, estimated + 2);
}

export function clampDivisor(value: string, max: number) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 1) {
    return 1;
  }
  return Math.min(Math.round(numeric), max);
}

export function formatRecipeDivisor(value: number) {
  return `${value} ${pluralizePortions(value)}`;
}

export function formatDisplayLabel(key: string, value: number | string) {
  if (key === "sodium" && value === SODIUM_BY_TASTE) {
    return "Соль";
  }
  return formatNutrientKey(key);
}

export function formatDisplayUnit(key: string, value: number | string) {
  if (key === "sodium" && value === SODIUM_BY_TASTE) {
    return "";
  }
  return formatNutrientUnit(key);
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
