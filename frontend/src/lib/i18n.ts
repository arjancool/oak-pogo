/**
 * Dutch interface labels. Kept in one place so a later translation only touches this module.
 */

export const typeNames: Record<string, string> = {
  normal: "Normaal",
  fighting: "Vechten",
  flying: "Vliegend",
  poison: "Gif",
  ground: "Grond",
  rock: "Gesteente",
  bug: "Insect",
  ghost: "Geest",
  steel: "Staal",
  fire: "Vuur",
  water: "Water",
  grass: "Gras",
  electric: "Elektrisch",
  psychic: "Psychisch",
  ice: "IJs",
  dragon: "Draak",
  dark: "Duister",
  fairy: "Fee",
};

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

export const statusLabels: Record<string, string> = {
  PROTECT: "Beschermd",
  KEEP: "Bewaren",
  BUILD: "Investeren",
  REVIEW: "Beoordelen",
  TRANSFER_CANDIDATE: "Transfer-kandidaat",
  UNKNOWN: "Onbekend",
};

export const statusDescriptions: Record<string, string> = {
  PROTECT: "Hard beschermd: vintage, handmatig of door een beschermingsregel",
  KEEP: "Beste exemplaar, nuttig in gevechten of een hoge bewaarscore",
  BUILD: "Goede kandidaat voor power-up of evolutie",
  REVIEW: "Beoordeel zelf, bijvoorbeeld een favoriet waarvan een beter exemplaar bestaat",
  TRANSFER_CANDIDATE: "Waarschijnlijk overbodig: er blijft een beter exemplaar. OAK zet nooit zelf iets over",
  UNKNOWN: "Onvoldoende betrouwbare gegevens",
};

export const confirmationKindLabels: Record<string, string> = {
  favorite: "Favoriet",
  vintage: "Vintage, bescherming opgeheven",
  unknown_date: "Vangstdatum onbekend",
  protected: "Beschermd door een regel",
};

export const readinessLabels: Record<string, string> = {
  direct: "Direct inzetbaar",
  power_up: "Na power-up",
  evolution: "Na evolutie",
  not_suitable: "Niet geschikt",
  unknown: "Onvoldoende gegevens",
  after_evolution: "Na evolutie",
};

export const leagueNames: Record<string, string> = {
  great: "Great League",
  ultra: "Ultra League",
  master: "Master League",
};

export const confidenceLabels: Record<string, string> = { high: "Hoog", medium: "Gemiddeld", low: "Laag" };

export const importStatusLabels: Record<string, string> = {
  received: "Ontvangen",
  queued: "In wachtrij",
  processing: "Wordt verwerkt",
  succeeded: "Volledig verwerkt",
  partial: "Gedeeltelijk verwerkt",
  failed: "Mislukt",
  rejected: "Geweigerd",
  duplicate: "Al eerder ontvangen",
};

export const classificationLabels: Record<string, string> = {
  full: "Volledige inventaris",
  partial: "Gedeeltelijke import",
  invalid: "Ongeldig",
  stale: "Verouderd",
  duplicate: "Dubbel",
};

export const changeLabels: Record<string, string> = {
  evolved: "Geëvolueerd",
  powered_up: "CP gewijzigd",
  moves_changed: "Aanvallen gewijzigd",
  favorite_changed: "Favoriet gewijzigd",
  tags_changed: "Tags gewijzigd",
  lucky_changed: "Lucky gewijzigd",
  alignment_changed: "Shadow/Purified gewijzigd",
  renamed: "Nieuwe bijnaam",
  mega_changed: "Mega gewijzigd",
  max_changed: "Max Moves gewijzigd",
  other: "Overige wijziging",
};

export const eventLabels: Record<string, string> = {
  APPEARED: "Voor het eerst gezien",
  CHANGED: "Gewijzigd",
  DISAPPEARED: "Niet meer in inventaris",
  REAPPEARED: "Weer in inventaris",
};

export const eventKindLabels: Record<string, string> = {
  "community-day": "Community Day",
  "pokemon-spotlight-hour": "Spotlight Hour",
  "raid-hour": "Raid Hour",
  "raid-day": "Raid Day",
  "raid-battles": "Raids",
  "max-mondays": "Max Monday",
  "max-battles": "Max Battles",
  "go-battle-league": "GO Battle League",
  "pokemon-go-tour": "Pokémon GO Tour",
  "wild-area": "Wild Area",
  "city-safari": "City Safari",
  "go-pass": "GO Pass",
  research: "Onderzoek",
  season: "Seizoen",
  event: "Event",
  manual: "Eigen event",
};

export const moveActionLabels: Record<string, string> = {
  none: "Heeft deze aanval al",
  fast_tm: "Fast TM",
  charged_tm: "Charged TM",
  elite_fast_tm: "Elite Fast TM",
  elite_charged_tm: "Elite Charged TM",
  unlock: "Tweede aanval vrijspelen",
  impossible: "Niet via TM beschikbaar",
};

export const availabilityLabels: Record<string, string> = {
  normal_tm: "Normale TM",
  elite_tm: "Alleen Elite TM",
  legacy: "Legacy/event",
  special: "Shadow/Purified-aanval",
  not_learnable: "Niet meer te leren",
};

export const conditionLabels: Record<string, string> = {
  must_be_buddy: "Moet buddy zijn",
  only_day: "Alleen overdag",
  only_night: "Alleen 's nachts",
  only_full_moon: "Alleen bij volle maan",
  only_dusk: "Alleen in de schemering",
  only_upside_down: "Telefoon ondersteboven",
  move_requirement: "Vereist een bepaalde aanval",
};

export const teamLabels: Record<number, string> = { 0: "Geen team", 1: "Mystic", 2: "Valor", 3: "Instinct" };

export function label(map: Record<string, string>, key: string | null | undefined): string {
  if (!key) return "–";
  return map[key] ?? key;
}
