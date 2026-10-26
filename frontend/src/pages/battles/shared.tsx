import { useQuery } from "@tanstack/react-query";
import type { ParseKeys } from "i18next";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { TypeBadge } from "../../components/pokemon";
import { Input } from "../../components/ui";
import i18n from "../../i18n";
import { api } from "../../lib/api";
import { level, num } from "../../lib/format";
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

const tagNames: Record<string, ParseKeys> = {
  mega: "battles.shared.tags.mega",
  shadow: "battles.shared.tags.shadow",
  legendary: "battles.shared.tags.legendary",
  mythical: "battles.shared.tags.mythical",
  ultrabeast: "battles.shared.tags.ultrabeast",
  starter: "battles.shared.tags.starter",
  regional: "battles.shared.tags.regional",
};
const stageNames: Record<number, ParseKeys> = {
  0: "battles.shared.stages.none",
  1: "battles.shared.stages.first",
  2: "battles.shared.stages.middle",
  3: "battles.shared.stages.final",
};

function either(values: string[]): string {
  return values.length > 1 ? i18n.t("battles.shared.either", { rest: values.slice(0, -1).join(", "), last: values[values.length - 1] }) : (values[0] ?? "");
}

function stageName(value: string | number): string {
  const key = stageNames[Number(value)];
  return key ? i18n.t(key) : String(value);
}

/** A type name as it reads inside a rule: lowercase in Dutch, capitalized in English. */
function typeInRule(type: string): string {
  return type in typeNames ? i18n.t(`battles.shared.typeInRule.${type}` as ParseKeys) : type;
}

/** One rule of a cup in plain language. */
export function conditionText(c: CupCondition): string {
  const values = c.values.map(String);
  const t = i18n.t;
  switch (c.kind) {
    case "type": {
      const types = either(values.map(typeInRule));
      return c.include ? t("battles.shared.rules.typeOnly", { types }) : t("battles.shared.rules.typeNone", { types });
    }
    case "tag": {
      const tags = either(values.map((v) => (tagNames[v] ? t(tagNames[v]) : v)));
      return c.include ? t("battles.shared.rules.tagOnly", { tags }) : t("battles.shared.rules.tagNone", { tags });
    }
    case "id":
      if (!c.include) return t("battles.shared.rules.idNone", { count: c.count });
      return c.alone ? t("battles.shared.rules.idOnly", { number: c.count }) : t("battles.shared.rules.idAlso", { count: c.count });
    case "evolution": {
      const stages = either(c.values.map(stageName));
      return c.include ? t("battles.shared.rules.stageOnly", { stages }) : t("battles.shared.rules.stageNone", { stages });
    }
    case "dex": {
      const ranges = [];
      for (let i = 0; i + 1 < values.length; i += 2) ranges.push(t("battles.shared.range", { from: values[i], to: values[i + 1] }));
      return c.include ? t("battles.shared.rules.dexOnly", { ranges: either(ranges) }) : t("battles.shared.rules.dexNone", { ranges: either(ranges) });
    }
    case "move":
      return c.include ? t("battles.shared.rules.moveOnly", { count: c.count }) : t("battles.shared.rules.moveNone", { count: c.count });
    case "moveType": {
      const types = either(values.map(typeInRule));
      return c.include ? t("battles.shared.rules.moveTypeOnly", { types }) : t("battles.shared.rules.moveTypeNone", { types });
    }
    case "cost":
      return c.include ? t("battles.shared.rules.costOnly", { costs: either(values) }) : t("battles.shared.rules.costNone", { costs: either(values) });
    case "distance":
      return c.include ? t("battles.shared.rules.distanceOnly", { distances: either(values) }) : t("battles.shared.rules.distanceNone", { distances: either(values) });
    default:
      return t("battles.shared.rules.other", { kind: c.kind });
  }
}

/** A cup's limits and rules, as OAK applies them. */
export function CupRules({ info }: { info: LeagueInfo }) {
  const { t } = useTranslation();
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm">
      <li>{info.max_cp ? t("battles.shared.maxCp", { cp: num(info.max_cp) }) : t("battles.shared.noCpLimit")}</li>
      {info.level_cap !== null && <li>{t("battles.shared.levelCap", { level: level(info.level_cap) })}</li>}
      {info.conditions.map((c, index) => (
        <li key={index}>{conditionText(c)}</li>
      ))}
    </ul>
  );
}
