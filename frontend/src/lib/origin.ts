import i18n from "../i18n";

const CHECKED = ["egg", "raid", "rocket", "max_battle"] as const;
type Origin = (typeof CHECKED)[number];

function isChecked(value: unknown): value is Origin {
  return typeof value === "string" && (CHECKED as readonly string[]).includes(value);
}

/** Where a Pokémon came from. Only origins checked against a real export have a name; any other
 * number stays "onbekend" with the number, and is never guessed (issue #32). */
export function originText(kind: unknown, code: unknown): string {
  if (isChecked(kind)) return i18n.t(`detail.values.origins.${kind}`);
  return typeof code === "number" ? i18n.t("detail.values.originCode", { code }) : i18n.t("detail.values.originMissing");
}
