import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { TypeBadge } from "../../components/pokemon";
import { Input } from "../../components/ui";
import { api } from "../../lib/api";
import { typeNames } from "../../lib/i18n";

export interface SpeciesOption {
  key: string;
  name: string;
  dex: number;
  types: string[];
  class: string | null;
}

/** Search box for choosing a raid boss or an opponent from the Game Data. */
export function SpeciesPicker({ onPick, placeholder }: { onPick: (option: SpeciesOption) => void; placeholder: string }) {
  const [text, setText] = useState("");
  const query = useQuery({
    queryKey: ["species-search", text],
    queryFn: () => api.get<SpeciesOption[]>("/api/v1/battles/species", { q: text }),
    enabled: text.trim().length >= 2,
  });
  return (
    <div className="relative">
      <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
      {text.trim().length >= 2 && (query.data?.length ?? 0) > 0 && (
        <ul className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-line bg-surface shadow-lg">
          {query.data?.map((option) => (
            <li key={option.key}>
              <button
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-surface-3"
                onClick={() => {
                  onPick(option);
                  setText("");
                }}
              >
                <span>
                  #{option.dex} {option.name}
                </span>
                <span className="flex gap-1">
                  {option.types.map((t) => (
                    <TypeBadge key={t} type={t} />
                  ))}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export interface CupCondition {
  include: boolean;
  kind: string;
  values: (string | number)[];
  count: number;
  alone: boolean;
}

export interface LeagueInfo {
  id: string;
  kind: "league" | "cup";
  name: string;
  max_cp: number | null;
  level_cap: number | null;
  ranked_species: number | null;
  eligible_species: number | null;
  rules: string[];
  conditions: CupCondition[];
  party_size: number | null;
  link: string | null;
  source: string | null;
}

/** The three leagues and the cups PvPoke currently shows, from the active Game Data. */
export function useLeagues() {
  return useQuery({ queryKey: ["leagues"], queryFn: () => api.get<LeagueInfo[]>("/api/v1/battles/leagues"), staleTime: 5 * 60_000 });
}

const tagNames: Record<string, string> = {
  mega: "Mega-evoluties",
  shadow: "Shadow Pokémon",
  legendary: "Legendary Pokémon",
  mythical: "Mythical Pokémon",
  ultrabeast: "Ultra Beasts",
  starter: "starters",
  regional: "regionale Pokémon",
};
const stageNames: Record<number, string> = {
  0: "Pokémon zonder evolutie",
  1: "Pokémon die nog kunnen evolueren en zelf geen eerdere vorm hebben",
  2: "middelste vormen van een evolutielijn",
  3: "laatste vormen van een evolutielijn",
};

function either(values: string[]): string {
  return values.length > 1 ? `${values.slice(0, -1).join(", ")} of ${values[values.length - 1]}` : (values[0] ?? "");
}

/** One rule of a cup in plain Dutch. */
export function conditionText(c: CupCondition): string {
  const values = c.values.map(String);
  switch (c.kind) {
    case "type": {
      const types = either(values.map((v) => (typeNames[v] ?? v).toLowerCase()));
      return c.include ? `Alleen Pokémon met het type ${types}.` : `Geen Pokémon met het type ${types}.`;
    }
    case "tag": {
      const tags = either(values.map((v) => tagNames[v] ?? v));
      return c.include ? `Alleen ${tags}.` : `Geen ${tags}.`;
    }
    case "id":
      if (!c.include) return `${c.count} aangewezen soorten mogen niet mee.`;
      return c.alone ? `Alleen ${c.count} aangewezen soorten.` : `Daarnaast mogen ${c.count} aangewezen soorten mee.`;
    case "evolution":
      return `${c.include ? "Alleen" : "Geen"} ${either(c.values.map((v) => stageNames[Number(v)] ?? String(v)))}.`;
    case "dex": {
      const ranges = [];
      for (let i = 0; i + 1 < values.length; i += 2) ranges.push(`${values[i]} t/m ${values[i + 1]}`);
      return `${c.include ? "Alleen" : "Geen"} Pokédex-nummers ${either(ranges)}.`;
    }
    case "move":
      return c.include ? `Alleen Pokémon die een van ${c.count} aangewezen aanvallen kunnen leren.` : `Geen Pokémon die een van ${c.count} aangewezen aanvallen kunnen leren.`;
    case "moveType": {
      const types = either(values.map((v) => (typeNames[v] ?? v).toLowerCase()));
      return `${c.include ? "Alleen" : "Geen"} Pokémon met een aanval van het type ${types}.`;
    }
    case "cost":
      return `${c.include ? "Alleen" : "Geen"} Pokémon waarvan de tweede aanval ${either(values)} stardust kost.`;
    case "distance":
      return `${c.include ? "Alleen" : "Geen"} Pokémon met een buddy-afstand van ${either(values)} km.`;
    default:
      return `Regel van het soort "${c.kind}".`;
  }
}

/** A cup's limits and rules, as OAK applies them. */
export function CupRules({ info }: { info: LeagueInfo }) {
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm">
      <li>{info.max_cp ? `Maximaal ${info.max_cp.toLocaleString("nl-NL")} CP.` : "Geen CP-limiet."}</li>
      {info.level_cap !== null && <li>Maximaal level {info.level_cap}.</li>}
      {info.conditions.map((c, index) => (
        <li key={index}>{conditionText(c)}</li>
      ))}
    </ul>
  );
}
