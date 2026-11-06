import i18n from "../i18n";

/** An item name per language, as the server sends it (issue #31). */
export interface ItemNames {
  nl: string;
  en: string;
}

/** The name in the chosen language, else the name the server gave. */
export function itemName(names: ItemNames | null | undefined, fallback: string | null): string {
  const language = i18n.resolvedLanguage ?? i18n.language;
  if (names && (language === "nl" || language === "en")) return names[language];
  return fallback ?? "";
}
