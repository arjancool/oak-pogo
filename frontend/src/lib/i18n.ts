/**
 * Labels for codes the API sends, such as types and cleanup statuses. The texts live in the
 * translation catalogs under "labels" (ADR-0025). Each map reads the active language when it is
 * used, so existing code keeps writing typeNames[type] or Object.entries(leagueNames).
 */
import i18n from "../i18n";
import nl from "../i18n/nl.json";

type LabelGroup = keyof typeof nl.labels;

function labelMap(group: LabelGroup): Record<string, string> {
  const source: Record<string, string> = nl.labels[group];
  const has = (key: string | symbol): key is string => typeof key === "string" && Object.hasOwn(source, key);
  const text = (key: string) => i18n.t(`labels.${group}.${key}` as "labels.types.normal");
  return new Proxy({} as Record<string, string>, {
    get: (_target, key) => (has(key) ? text(key) : undefined),
    has: (_target, key) => has(key),
    ownKeys: () => Object.keys(source),
    getOwnPropertyDescriptor: (_target, key) => (has(key) ? { value: text(key), enumerable: true, configurable: true } : undefined),
  });
}

export const typeNames: Record<string, string> = labelMap("types");

export const typeColors: Record<string, string> = {
  normal: "#9fa19f",
  fighting: "#ff8000",
  flying: "#81b9ef",
  poison: "#9141cb",
  ground: "#915121",
  rock: "#afa981",
  bug: "#91a119",
  ghost: "#704170",
  steel: "#60a1b8",
  fire: "#e62829",
  water: "#2980ef",
  grass: "#3fa129",
  electric: "#fac000",
  psychic: "#ef4179",
  ice: "#3dcef3",
  dragon: "#5060e1",
  dark: "#624d4e",
  fairy: "#ef70ef",
};

export const statusLabels: Record<string, string> = labelMap("statuses");

export const statusDescriptions: Record<string, string> = labelMap("statusDescriptions");

export const confirmationKindLabels: Record<string, string> = labelMap("confirmationKinds");

export const readinessLabels: Record<string, string> = labelMap("readiness");

export const leagueNames: Record<string, string> = labelMap("leagues");

export const confidenceLabels: Record<string, string> = labelMap("confidence");

export const importStatusLabels: Record<string, string> = labelMap("importStatuses");

export const classificationLabels: Record<string, string> = labelMap("classifications");

export const changeLabels: Record<string, string> = labelMap("changes");

export const eventLabels: Record<string, string> = labelMap("events");

export const eventKindLabels: Record<string, string> = labelMap("eventKinds");

export const moveActionLabels: Record<string, string> = labelMap("moveActions");

export const availabilityLabels: Record<string, string> = labelMap("availability");

export const conditionLabels: Record<string, string> = labelMap("conditions");

export const teamLabels: Record<number, string> = labelMap("teams");

export function label(map: Record<string, string>, key: string | null | undefined): string {
  if (!key) return "–";
  return map[key] ?? key;
}
