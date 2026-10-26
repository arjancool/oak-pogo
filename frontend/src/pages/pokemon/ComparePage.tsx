import { useQuery } from "@tanstack/react-query";
import { Trans, useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { z } from "zod";

import { CleanupBadge, IvPercent, PokemonSprite, StatusBadges, pokemonName } from "../../components/pokemon";
import { Alert, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { date, ivs, level, num, pct } from "../../lib/format";
import { label, leagueNames, readinessLabels } from "../../lib/i18n";
import { pokemonDetail } from "../../lib/schemas";

const compareSchema = z.array(
  pokemonDetail.extend({
    rankings: z.array(
      z.object({
        league: z.string(),
        target: z.string(),
        rank: z.number(),
        percent: z.number(),
        best_cp: z.number(),
        readiness: z.string(),
        stardust: z.number().nullable(),
        species_rank: z.number().nullable(),
      }),
    ),
  }),
);

export function ComparePage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const ids = (params.get("ids") ?? "").split(",").map(Number).filter((n) => Number.isFinite(n) && n > 0);
  const query = useQuery({
    queryKey: ["compare", ids],
    queryFn: async () => compareSchema.parse(await api.post("/api/v1/pokemon/compare", { ids })),
    enabled: ids.length >= 2,
  });
  if (ids.length < 2) {
    return (
      <>
        <PageHeader title={t("compare.title")} />
        <EmptyState title={t("compare.empty.title")}>
          {/* Not <link>: Trans parses that as an empty HTML element and drops the link text. */}
          <Trans i18nKey="compare.empty.text" components={{ boxLink: <Link to="/pokemon" className="text-oak-400 underline" /> }} />
        </EmptyState>
      </>
    );
  }
  if (query.isLoading) return <Spinner />;
  if (query.error) return <Alert tone="error">{errorMessage(query.error)}</Alert>;
  const items = query.data ?? [];
  const rows: [string, (p: (typeof items)[number]) => React.ReactNode][] = [
    ["CP", (p) => num(p.cp, "?")],
    [t("compare.rows.level"), (p) => level(p.level)],
    [t("compare.rows.ivs"), (p) => <span className="font-mono">{ivs(p.iv_attack, p.iv_defense, p.iv_stamina)}</span>],
    ["IV%", (p) => <IvPercent value={p.iv_percent} />],
    [t("compare.rows.fastMove"), (p) => p.fast_move?.name ?? "?"],
    [t("compare.rows.chargedMoves"), (p) => p.charged_moves.map((m) => m.name).join(" / ")],
    [t("compare.rows.caught"), (p) => (p.hatched_from_egg ? t("compare.hatched", { date: date(p.caught_at) }) : date(p.caught_at))],
    [t("compare.rows.cleanup"), (p) => <CleanupBadge status={p.cleanup?.status} />],
    [t("compare.rows.properties"), (p) => <StatusBadges pokemon={p} />],
  ];
  const leagues = ["great", "ultra", "master"];
  return (
    <>
      <PageHeader title={t("compare.title")} description={t("compare.description")} />
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th />
                {items.map((p) => (
                  <th key={p.id} className="px-3 pb-3 text-left align-bottom">
                    <Link to={`/pokemon/${p.id}`} className="flex items-center gap-2">
                      <PokemonSprite dex={p.species_id} shiny={p.shiny} types={p.types} size={44} />
                      <span className="font-medium">{pokemonName(p)}</span>
                    </Link>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(([title, render]) => (
                <tr key={title} className="border-t border-line">
                  <td className="py-2 pr-3 text-xs text-muted">{title}</td>
                  {items.map((p) => (
                    <td key={p.id} className="px-3 py-2">
                      {render(p)}
                    </td>
                  ))}
                </tr>
              ))}
              {leagues.map((league) => (
                <tr key={league} className="border-t border-line">
                  <td className="py-2 pr-3 text-xs text-muted">{leagueNames[league]}</td>
                  {items.map((p) => {
                    const best = p.rankings
                      .filter((r) => r.league === league && r.readiness !== "not_suitable")
                      .sort((a, b) => (a.species_rank ?? 9999) - (b.species_rank ?? 9999) || a.rank - b.rank)[0];
                    return (
                      <td key={p.id} className="px-3 py-2 text-xs">
                        {best ? (
                          <>
                            <p className="font-medium">{best.target}</p>
                            <p>
                              {t("compare.rank", { rank: best.rank, percent: pct(best.percent), readiness: label(readinessLabels, best.readiness) })}
                            </p>
                            {best.stardust ? <p className="text-muted">{t("compare.stardustNeeded", { stardust: num(best.stardust) })}</p> : null}
                          </>
                        ) : (
                          <span className="text-muted">{t("compare.notSuitable")}</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="border-t border-line">
                <td className="py-2 pr-3 text-xs text-muted">{t("compare.rows.advice")}</td>
                {items.map((p) => (
                  <td key={p.id} className="px-3 py-2 text-xs">
                    {p.recommendation?.reasons.slice(0, 3).map((r, i) => <p key={i}>{r.text}</p>)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
