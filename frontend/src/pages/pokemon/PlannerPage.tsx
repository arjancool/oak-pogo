import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { PokemonSprite, ReadinessBadge } from "../../components/pokemon";
import { Alert, Card, Checkbox, Field, Input, PageHeader, Select, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { num } from "../../lib/format";
import { leagueNames } from "../../lib/i18n";

interface Candidate {
  pokemon_id: number;
  species_id: number;
  shiny: boolean | null;
  types: string[];
  name: string | null;
  form_label: string | null;
  cp: number | null;
  target: string;
  is_evolution: boolean;
  iv_rank: number;
  percent: number;
  best_cp: number;
  readiness: string;
  species_rank: number | null;
  cost: { stardust: number | null; candy: number | null; xl_candy: number | null };
  moveset_quality: string;
  recommended_moveset: string[];
  suitability: number;
}

function Planner({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const [league, setLeague] = useState("great");
  const [budget, setBudget] = useState(100_000);
  const [maxPokemon, setMaxPokemon] = useState(3);
  const [allowXl, setAllowXl] = useState(false);
  const [allowEvolution, setAllowEvolution] = useState(true);
  const [maxIvRank, setMaxIvRank] = useState(500);
  const readiness = allowEvolution ? "power_up,evolution" : "power_up";
  const query = useQuery({
    queryKey: ["league", league, accountId, "planner", readiness],
    queryFn: () => api.get<{ items: Candidate[] }>(`/api/v1/battles/league/${league}`, { account_id: accountId, readiness, limit: 500 }),
  });

  const plan = useMemo(() => {
    // Filter here as well: a cached or still loading result must never bring back an evolution
    // after the user turned evolutions off.
    const items = (query.data?.items ?? [])
      .filter((c) => allowEvolution || !c.is_evolution)
      .filter((c) => c.iv_rank <= maxIvRank)
      .filter((c) => allowXl || !c.cost.xl_candy)
      .sort((a, b) => b.suitability - a.suitability);
    const chosen: Candidate[] = [];
    const seen = new Set<string>();
    let spent = 0;
    for (const candidate of items) {
      if (chosen.length >= maxPokemon) break;
      if (seen.has(candidate.target)) continue;
      const cost = candidate.cost.stardust ?? 0;
      if (spent + cost > budget) continue;
      chosen.push(candidate);
      seen.add(candidate.target);
      spent += cost;
    }
    return { chosen, spent };
  }, [query.data, allowEvolution, maxIvRank, allowXl, maxPokemon, budget]);

  return (
    <>
      <PageHeader
        title={t("planner.title")}
        description={t("planner.description")}
      />
      <Card className="mb-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Field label={t("planner.goal")}>
            <Select className="w-full" value={league} onChange={(e) => setLeague(e.target.value)}>
              {Object.entries(leagueNames).map(([key, name]) => (
                <option key={key} value={key}>
                  {name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("planner.maxStardust")}>
            <Input type="number" min={0} step={10000} value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
          </Field>
          <Field label={t("planner.maxPokemon")}>
            <Input type="number" min={1} max={20} value={maxPokemon} onChange={(e) => setMaxPokemon(Number(e.target.value))} />
          </Field>
          <Field label={t("planner.maxIvRank")}>
            <Input type="number" min={1} max={4096} value={maxIvRank} onChange={(e) => setMaxIvRank(Number(e.target.value))} />
          </Field>
          <div className="space-y-2 pt-5">
            <Checkbox checked={allowXl} onChange={setAllowXl} label={t("planner.allowXl")} />
            <Checkbox checked={allowEvolution} onChange={setAllowEvolution} label={t("planner.allowEvolution")} />
          </div>
        </div>
      </Card>
      {query.isLoading ? (
        <Spinner />
      ) : plan.chosen.length === 0 ? (
        <Alert tone="info">{t("planner.none")}</Alert>
      ) : (
        <Card title={t("planner.proposal", { count: plan.chosen.length, stardust: num(plan.spent) })}>
          <ul className="divide-y divide-line">
            {plan.chosen.map((c) => (
              <li key={c.pokemon_id} className="flex flex-wrap items-center gap-3 py-3">
                <PokemonSprite dex={c.species_id} shiny={c.shiny} types={c.types} size={36} />
                <div className="min-w-0 flex-1">
                  <Link to={`/pokemon/${c.pokemon_id}`} className="font-medium hover:text-oak-300">
                    {c.name}
                    {c.form_label ? ` (${c.form_label})` : ""} → {c.target}
                  </Link>
                  <p className="text-xs text-muted">
                    {t("planner.ranks", { ivRank: c.iv_rank, speciesRank: c.species_rank ?? "–", cp: num(c.cp, "?"), bestCp: num(c.best_cp) })}
                    {c.recommended_moveset.length ? ` · ${t("planner.moves", { moves: c.recommended_moveset.join(", ") })}` : ""}
                  </p>
                </div>
                <ReadinessBadge readiness={c.readiness} />
                <span className="text-sm tabular-nums">
                  {t("planner.cost", { stardust: num(c.cost.stardust ?? 0), candy: num(c.cost.candy ?? 0) })}
                  {c.cost.xl_candy ? ` · ${num(c.cost.xl_candy)} XL` : ""}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted">{t("planner.footer")}</p>
        </Card>
      )}
    </>
  );
}

export function PlannerPage() {
  return <RequireAccount>{(id) => <Planner accountId={id} />}</RequireAccount>;
}
