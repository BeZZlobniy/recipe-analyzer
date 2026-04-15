export const compatibilityDimensionLabels: Record<string, string> = {
  diet: "Совместимость с типом питания",
  restriction: "Совместимость с ограничениями",
  goal: "Совместимость с целью",
};

export const compatibilityLevelLabels: Record<string, string> = {
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
};

export const nutrientLabels: Record<string, string> = {
  calories: "Калории",
  protein: "Белки",
  fat: "Жиры",
  carbs: "Углеводы",
  fiber: "Клетчатка",
  sodium: "Натрий",
};

export const nutrientUnits: Record<string, string> = {
  calories: "ккал",
  protein: "г",
  fat: "г",
  carbs: "г",
  fiber: "г",
  sodium: "мг",
};

export function formatCompatibilityDimension(key: string): string {
  return compatibilityDimensionLabels[key] ?? key;
}

export function formatCompatibilityLevel(key: string): string {
  return compatibilityLevelLabels[key] ?? key;
}

export function formatNutrientKey(key: string): string {
  return nutrientLabels[key] ?? key;
}

export function formatNutrientUnit(key: string): string {
  return nutrientUnits[key] ?? "";
}
