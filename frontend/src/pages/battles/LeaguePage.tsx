import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { PokemonSprite, ReadinessBadge } from "../../components/pokemon";
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Select, SortHeader, Spinner } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { ivs, level, num, pct } from "../../lib/format";
import { leagueNames } from "../../lib/i18n";
import { useUrlState } from "../../lib/useUrlState";
import { CupRules, type LeagueInfo } from "./shared";

interface LeagueItem {
  pokemon_id: number;
  species_id: number;
  shiny: boolean | null;
  types: string[];
  name: string | null;
  form_label: string | null;
  cp: number | null;
  level: number | null;
  shadow: boolean;
  ivs: [number | null, number | null, number | null];
  target: string;
  is_evolution: boolean;
  iv_rank: number;
  percent: number;
  best_cp: number;
  best_level: number;
  readiness: string;
  species_rank: number | null;
  species_score: number | null;
  cost: { stardust: number | null; candy: number | null; xl_candy: number | null };
  moveset_quality: string;
  recommended_moveset: string[];
  suitability: number;
}

const qualityLabels: Record<string, [string, string]> = {
  optimal: ["Optimaal", "#34d399"],
  partial: ["Deels", "#fbbf24"],
  poor: ["Andere aanvallen nodig", "#f87171"],
  after_evolution: ["Na evolutie bepalen", "#a78bfa"],
  unknown: ["Onbekend", "#94a3b8"],
};

const LIMIT = 200;
const DEFAULT_SORT = "-suitability";

function League({ accountId, league }: { accountId: number; league: string }) {
  const [state, update] = useUrlState();
  const readiness = state.readiness ?? "";
  const sort = state.sort ?? DEFAULT_SORT;
  const query = useQuery({
    queryKey: ["league", league, accountId, readiness, sort],
    queryFn: () =>
      api.get<{ max_cp: number | null; method: string; info: LeagueInfo; items: LeagueItem[]; total: number }>(`/api/v1/battles/league/${league}`, {
        account_id: accountId,
        readiness: readiness || undefined,
        sort,
        limit: LIMIT,
      }),
  });
  const header = (label: string, sortKey: string, ascendingFirst = false) => (
    <SortHeader label={label} sortKey={sortKey} sort={sort} onSort={(value) => update({ sort: value })} ascendingFirst={ascendingFirst} />
  );
  return (
    <>
      <PageHeader
        title={query.data?.info.name ?? leagueNames[league] ?? league}
        description={query.data ? `${query.data.max_cp ? `Maximaal ${num(query.data.max_cp)} CP. ` : "Geen CP-limiet. "}${query.data.method}` : undefined}
        actions={
          <div className="flex flex-wrap gap-2">
            {sort !== DEFAULT_SORT && (
              <Button variant="ghost" onClick={() => update({ sort: null })}>
                Meest geschikt eerst
              </Button>
            )}
            <Select value={readiness} onChange={(e) => update({ readiness: e.target.value })} aria-label="Inzetbaarheid">
              <option value="">Alle inzetbaarheid</option>
              <option value="direct">Direct inzetbaar</option>
              <option value="power_up">Na power-up</option>
              <option value="evolution">Na evolutie</option>
            </Select>
          </div>
        }
      />
      {query.data?.info.kind === "cup" && (
        <Card className="mb-5" title="Regels van deze cup">
          <CupRules info={query.data.info} />
          <p className="mt-2 text-xs text-muted">
            Zoals PvPoke ze beschrijft. Controleer in het spel of de cup nu loopt en of de regels gelijk zijn.{" "}
            <Link to="/battles/cups" className="underline">
              Alle cups
            </Link>
          </p>
        </Card>
      )}
      {query.isLoading ? (
        <Spinner />
      ) : query.error ? (
        <Alert tone="error">{errorMessage(query.error)}</Alert>
      ) : !query.data?.items.length ? (
        <EmptyState title="Geen geschikte Pokémon">Er zijn geen Pokémon die (na evolutie of power-up) in deze {query.data?.info.kind === "cup" ? "cup" : "league"} passen, of de analyse moet nog draaien.</EmptyState>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm [&_td]:pr-3 [&_th]:pr-3">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-2">{header("Pokémon", "name", true)}</th>
                  <th>{header("Doel", "target", true)}</th>
                  <th>{header("Soortrang", "species_rank", true)}</th>
                  <th>{header("IV-rang", "iv_rank", true)}</th>
                  <th>{header("%", "percent")}</th>
                  <th>
                    {header("CP nu", "cp")} → {header("beste", "best_cp")}
                  </th>
                  <th>{header("Inzetbaarheid", "readiness", true)}</th>
                  <th>{header("Investering", "stardust", true)}</th>
                  <th>{header("Aanvallen", "moveset", true)}</th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((item) => {
                  const [qualityText, qualityColor] = qualityLabels[item.moveset_quality] ?? ["?", undefined];
                  return (
                    <tr key={item.pokemon_id} className="border-t border-line align-top">
                      <td className="py-2 pr-3">
                        <Link to={`/pokemon/${item.pokemon_id}`} className="flex items-center gap-2">
                          <PokemonSprite dex={item.species_id} shiny={item.shiny} types={item.types} size={32} />
                          <span>
                            <span className="font-medium hover:text-oak-300">
                              {item.name}
                              {item.form_label ? ` (${item.form_label})` : ""}
                            </span>
                            {item.shadow && <Badge className="ml-1" color="#a855f7">Shadow</Badge>}
                            <span className="block font-mono text-xs text-muted">{ivs(...item.ivs)}</span>
                          </span>
                        </Link>
                      </td>
                      <td className="pr-3">
                        {item.target}
                        {item.is_evolution && <span className="block text-xs text-muted">na evolutie</span>}
                      </td>
                      <td className="pr-3 tabular-nums">{item.species_rank ?? "–"}</td>
                      <td className="pr-3 tabular-nums">{item.iv_rank}</td>
                      <td className="pr-3 tabular-nums">{pct(item.percent)}</td>
                      <td className="pr-3 tabular-nums">
                        {num(item.cp, "?")} → {num(item.best_cp)} <span className="text-xs text-muted">L{level(item.best_level)}</span>
                      </td>
                      <td className="pr-3">
                        <ReadinessBadge readiness={item.readiness} />
                      </td>
                      <td className="pr-3 text-xs tabular-nums">
                        {item.cost.stardust ? `${num(item.cost.stardust)} stardust` : "–"}
                        {item.cost.xl_candy ? <span className="block">{num(item.cost.xl_candy)} XL</span> : null}
                      </td>
                      <td className="text-xs">
                        <Badge color={qualityColor}>{qualityText}</Badge>
                        <span className="mt-1 block text-muted">{item.recommended_moveset.join(" · ")}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {query.data.total > query.data.items.length && (
            <p className="mt-3 text-xs text-muted">
              Je ziet de eerste {num(query.data.items.length)} van {num(query.data.total)} Pokémon in deze volgorde. Het sorteren gebeurt over alle {num(query.data.total)}.
            </p>
          )}
          <p className="mt-3 text-xs text-muted">
            Klik op een kolomkop om te sorteren. Soortrang zegt hoe sterk de soort is (PvPoke). IV-rang zegt hoe goed dit exemplaar binnen die soort is. Een sterke IV-rang bij een
            zwakke soort maakt nog geen goede battle-Pokémon.
          </p>
        </Card>
      )}
    </>
  );
}

export function LeaguePage() {
  const { league = "great" } = useParams();
  return <RequireAccount>{(id) => <League accountId={id} league={league} />}</RequireAccount>;
}
