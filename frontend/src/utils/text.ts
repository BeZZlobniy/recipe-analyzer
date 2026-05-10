export function uniqueTextList(values: string[]) {
  return Array.from(new Set(values.map((item) => item.trim()).filter(Boolean)));
}

export function isUserFacingWarning(value: string) {
  return !/^Что учитывать:|^Тема:|^Рекомендации:/i.test(value);
}
