import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { z } from "zod";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { CleanupBadge, IvPercent, PokemonSprite, StatusBadges, pokemonName } from "../../components/pokemon";
import { Card, EmptyState, PageHeader, Select, Spinner, Tabs } from "../../components/ui";
import { api } from "../../lib/api";
import { dateTime, num } from "../../lib/format";
import { changeLabels, classificationLabels, label } from "../../lib/i18n";
import { pokemonSummary } from "../../lib/schemas";
import { useUrlState } from "../../lib/useUrlState";

const historySchema = z.object({
  kind: z.string(),
  sync_run: z.object({ id: z.number(), applied_at: z.string(), classification: z.string() }).nullable(),
  items: z.array(z.object({ pokemon: pokemonSummary, labels: z.array(z.string()), changes: z.record(z.string(), z.unknown()) })),
  runs: z.array(z.object({ id: z.number(), applied_at: z.string(), classification: z.string(), new: z.number(), changed: z.number(), missing: z.number() })),
  note: z.string().optional(),
});
type Kind = "new" | "changed" | "missing" | "reappeared";

function History({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const [state, update] = useUrlState();
  const kind = (state.kind as Kind) ?? "new";
  const run = state.run;
  const query = useQuery({
    queryKey: ["history", accountId, kind, run],
    queryFn: async () => historySchema.parse(await api.get("/api/v1/history/changes", { account_id: accountId, kind, sync_run_id: run })),
  });
  const inventory = useQuery({
    queryKey: ["inventory-history", accountId],
    queryFn: () => api.get<{ at: string; stardust: number | null; level: number | null; items_total: number }[]>("/api/v1/history/inventory", { account_id: accountId }),
  });
  const data = query.data;
  return (
    <>
      <PageHeader title={t("account.history.title")} description={t("account.history.description")} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs
          value={kind}
          onChange={(value) => update({ kind: value })}
          tabs={[
            { value: "new", label: t("account.history.tabs.new") },
            { value: "changed", label: t("account.history.tabs.changed") },
            { value: "missing", label: t("account.history.tabs.missing") },
            { value: "reappeared", label: t("account.history.tabs.reappeared") },
          ]}
        />
        {data && data.runs.length > 0 && (
          <Select value={run ?? ""} onChange={(e) => update({ run: e.target.value || null })} aria-label={t("account.history.syncSelect")}>
            <option value="">{t("account.history.latestSync")}</option>
            {data.runs.map((r) => (
              <option key={r.id} value={r.id}>
                {dateTime(r.applied_at)} · {label(classificationLabels, r.classification)} · +{r.new} / ~{r.changed} / -{r.missing}
              </option>
            ))}
          </Select>
        )}
      </div>
      {query.isLoading ? (
        <Spinner />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title={t("account.history.empty")}>{data?.note}</EmptyState>
      ) : (
        <Card title={data.sync_run ? t("account.history.syncOf", { time: dateTime(data.sync_run.applied_at) }) : undefined}>
          <ul className="divide-y divide-line">
            {data.items.map(({ pokemon, labels }) => (
              <li key={pokemon.id} className="flex flex-wrap items-center gap-3 py-2">
                <PokemonSprite dex={pokemon.species_id} shiny={pokemon.shiny} types={pokemon.types} size={36} />
                <div className="min-w-0 flex-1">
                  <Link to={`/pokemon/${pokemon.id}`} className="font-medium hover:text-oak-300">
                    {pokemonName(pokemon)}
                  </Link>
                  <p className="text-xs text-muted">
                    CP {num(pokemon.cp, "?")} · <IvPercent value={pokemon.iv_percent} />
                    {labels.length > 0 && <> · {labels.map((l) => label(changeLabels, l)).join(", ")}</>}
                  </p>
                </div>
                <StatusBadges pokemon={pokemon} compact />
                <CleanupBadge status={pokemon.cleanup?.status} />
              </li>
            ))}
          </ul>
        </Card>
      )}
      {inventory.data && inventory.data.length > 1 && (
        <Card className="mt-5" title={t("account.history.inventory")}>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-1">{t("account.history.columns.moment")}</th>
                <th>{t("account.history.columns.level")}</th>
                <th>{t("account.history.columns.stardust")}</th>
                <th>{t("account.history.columns.items")}</th>
              </tr>
            </thead>
            <tbody>
              {inventory.data
                .slice()
                .reverse()
                .slice(0, 30)
                .map((row) => (
                  <tr key={row.at} className="border-t border-line tabular-nums">
                    <td className="py-1">{dateTime(row.at)}</td>
                    <td>{row.level ?? "–"}</td>
                    <td>{num(row.stardust)}</td>
                    <td>{num(row.items_total)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}

export function HistoryPage() {
  return <RequireAccount>{(id) => <History accountId={id} />}</RequireAccount>;
}
