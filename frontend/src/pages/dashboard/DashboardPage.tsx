import { useQuery } from "@tanstack/react-query";
import { Trans, useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { z } from "zod";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { CleanupBadge, IvPercent, PokemonSprite, pokemonName } from "../../components/pokemon";
import { Alert, Card, EmptyState, PageHeader, Spinner, Stat } from "../../components/ui";
import { useAccount } from "../../lib/account";
import { api } from "../../lib/api";
import { dateTime, level, num, relative } from "../../lib/format";
import { classificationLabels, label } from "../../lib/i18n";
import { pokemonSummary, type PokemonSummary } from "../../lib/schemas";
import { serverText } from "../../lib/serverText";
import { storedText } from "../../lib/storedText";
import type { SyncStatus } from "../../lib/types";

const dashboardSchema = z.object({
  cards: z.record(z.string(), z.number().nullable()),
  cleanup_statuses: z.record(z.string(), z.number()),
  recent_catches: z.array(pokemonSummary),
  new_since_last_sync: z.array(pokemonSummary),
  valuable_new: z.array(pokemonSummary),
  missing_since_last_sync: z.array(pokemonSummary),
  favorite_changes: z.number(),
  investment_candidates: z.array(pokemonSummary),
  top_cleanup: z.array(pokemonSummary),
  last_sync: z
    .object({
      id: z.number(),
      applied_at: z.string(),
      classification: z.string(),
      new: z.number(),
      changed: z.number(),
      missing: z.number(),
      missing_unconfirmed: z.number(),
      total: z.number(),
      warnings: z.array(z.object({ code: z.string(), message: z.string(), data: z.record(z.string(), z.unknown()).nullish() })),
    })
    .nullable(),
  game_data: z.boolean(),
  year_distribution: z.record(z.string(), z.number()),
});

function MiniList({ items, empty }: { items: PokemonSummary[]; empty: string }) {
  const navigate = useNavigate();
  if (!items.length) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="divide-y divide-line">
      {items.map((p) => (
        <li key={p.id}>
          <button className="flex w-full items-center gap-3 py-2 text-left hover:bg-surface-3/40" onClick={() => navigate(`/pokemon/${p.id}`)}>
            <PokemonSprite dex={p.species_id} shiny={p.shiny} types={p.types} size={36} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{pokemonName(p)}</p>
              <p className="text-xs text-muted">
                CP {num(p.cp)} · <IvPercent value={p.iv_percent} />
              </p>
            </div>
            <CleanupBadge status={p.cleanup?.status} />
          </button>
        </li>
      ))}
    </ul>
  );
}

function Dashboard({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { account } = useAccount();
  const data = useQuery({
    queryKey: ["dashboard", accountId],
    queryFn: async () => dashboardSchema.parse(await api.get("/api/v1/dashboard", { account_id: accountId })),
  });
  const sync = useQuery({
    queryKey: ["sync-status", accountId],
    queryFn: () => api.get<SyncStatus>("/api/v1/sync/status", { account_id: accountId }),
  });
  if (data.isLoading) return <Spinner />;
  if (data.error || !data.data) return <Alert tone="error">{t("dashboard.loadError")}</Alert>;
  const d = data.data;
  const c = d.cards;
  const box = (query: string) => () => navigate(`/pokemon?${query}`);

  if (!c.total && !d.last_sync) {
    return (
      <>
        <PageHeader title={account ? t("dashboard.welcomeName", { name: account.nickname }) : t("dashboard.welcome")} />
        <EmptyState title={t("dashboard.empty.title")}>
          <Trans i18nKey="dashboard.empty.text" components={{ b: <b />, code: <code /> }} />
        </EmptyState>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={t("dashboard.title")}
        description={account?.source_nickname ? t("dashboard.description", { name: account.source_nickname, level: level(account.trainer_level) }) : undefined}
      />
      {!d.game_data && (
        <div className="mb-4">
          <Alert tone="warning" title={t("dashboard.noGameData.title")}>
            {t("dashboard.noGameData.text")}
          </Alert>
        </div>
      )}
      {sync.data && (
        <Card
          className="mb-5"
          title={t("dashboard.sync.title")}
          actions={<span className="text-xs text-muted">{t("dashboard.sync.lastSuccess", { time: dateTime(sync.data.last_successful_sync_at) })}</span>}
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <Stat label={t("dashboard.sync.status")} value={serverText("sync", sync.data.message)} />
            <Stat label={t("dashboard.sync.inExport")} value={num(d.last_sync?.total ?? null, "–")} />
            <Stat label={t("dashboard.sync.new")} value={num(d.last_sync?.new ?? null, "–")} onClick={box("new=true")} />
            <Stat label={t("dashboard.sync.changed")} value={num(d.last_sync?.changed ?? null, "–")} onClick={() => navigate("/history?kind=changed")} />
            <Stat
              label={t("dashboard.sync.missing")}
              value={num(d.last_sync?.missing ?? null, "–")}
              hint={d.last_sync?.missing_unconfirmed ? t("dashboard.sync.unconfirmed", { missing: num(d.last_sync.missing_unconfirmed) }) : undefined}
              onClick={() => navigate("/history?kind=missing")}
            />
          </div>
          {d.last_sync && (
            <p className="mt-3 text-xs text-muted">
              {label(classificationLabels, d.last_sync.classification)} · {relative(d.last_sync.applied_at)}
              {d.last_sync.warnings.map((w) => (
                <span key={w.code} className="ml-2 text-amber-300">
                  {storedText("imports", w.code, w.message, w.data)}
                </span>
              ))}
            </p>
          )}
        </Card>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-8">
        <Stat label={t("dashboard.cards.total")} value={num(c.total ?? 0)} onClick={box("")} />
        <Stat label={t("dashboard.cards.shiny")} value={num(c.shiny ?? 0)} onClick={box("shiny=true")} accent="#f472b6" />
        <Stat label={t("dashboard.cards.lucky")} value={num(c.lucky ?? 0)} onClick={box("lucky=true")} accent="#eab308" />
        <Stat label={t("dashboard.cards.shadow")} value={num(c.shadow ?? 0)} onClick={box("shadow=true")} accent="#a855f7" />
        <Stat label={t("dashboard.cards.hundo")} value={num(c.hundo ?? 0)} onClick={box("hundo=true")} accent="#ef4444" />
        <Stat label={t("dashboard.cards.shundo")} value={num(c.shundo ?? 0)} onClick={box("shundo=true")} />
        <Stat label={t("dashboard.cards.favorites")} value={num(c.favorite ?? 0)} onClick={box("favorite=true")} accent="#facc15" />
        <Stat label={t("dashboard.cards.vintage")} value={num(c.vintage ?? 0)} onClick={box("vintage=true")} accent="#d97706" />
        <Stat label={t("dashboard.cards.legendary")} value={num(c.legendary ?? 0)} onClick={box("legendary=true")} />
        <Stat label={t("dashboard.cards.mythical")} value={num(c.mythical ?? 0)} onClick={box("mythical=true")} />
        <Stat label={t("dashboard.cards.dynamax")} value={num(c.dynamax ?? 0)} onClick={box("dynamax=true")} />
        <Stat label={t("dashboard.cards.gigantamax")} value={num(c.gigantamax ?? 0)} onClick={box("gigantamax=true")} />
        <Stat label={t("dashboard.cards.cleanupCandidates")} value={num(c.cleanup_candidates ?? 0)} onClick={() => navigate("/cleanup")} accent="#f87171" />
        <Stat label={t("dashboard.cards.review")} value={num(c.review ?? 0)} onClick={() => navigate("/cleanup?status=REVIEW")} accent="#fbbf24" />
        <Stat label={t("dashboard.cards.stardust")} value={num(c.stardust)} />
        <Stat
          label={t("dashboard.cards.storageFree")}
          value={c.storage_free === null || c.storage_free === undefined ? t("common.unknown") : num(c.storage_free)}
          hint={c.storage_max ? t("dashboard.cards.storageMax", { max: num(c.storage_max) }) : undefined}
        />
        <Stat label={t("dashboard.cards.backgrounds")} value={num(c.background ?? 0)} onClick={box("background=true")} />
        <Stat label={t("dashboard.cards.actionList")} value={num(c.action_list_open ?? 0)} onClick={() => navigate("/cleanup?tab=list")} />
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Card title={t("dashboard.lists.recent")}>
          <MiniList items={d.recent_catches} empty={t("dashboard.lists.recentEmpty")} />
        </Card>
        <Card title={t("dashboard.lists.new")}>
          <MiniList items={d.new_since_last_sync} empty={t("dashboard.lists.newEmpty")} />
        </Card>
        <Card title={t("dashboard.lists.missing")}>
          <MiniList items={d.missing_since_last_sync} empty={t("dashboard.lists.missingEmpty")} />
        </Card>
        <Card title={t("dashboard.lists.valuable")}>
          <MiniList items={d.valuable_new} empty={t("dashboard.lists.valuableEmpty")} />
        </Card>
        <Card title={t("dashboard.lists.investment")}>
          <MiniList items={d.investment_candidates} empty={t("dashboard.lists.investmentEmpty")} />
        </Card>
        <Card
          title={t("dashboard.lists.cleanup")}
          actions={<span className="text-xs text-muted">{t("dashboard.lists.favoritesChanged", { count: d.favorite_changes })}</span>}
        >
          <MiniList items={d.top_cleanup} empty={t("dashboard.lists.cleanupEmpty")} />
        </Card>
      </div>
      {Object.keys(d.year_distribution).length > 0 && (
        <Card className="mt-5" title={t("dashboard.years")}>
          <div className="flex flex-wrap gap-2">
            {Object.entries(d.year_distribution)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([year, count]) => (
                <button
                  key={year}
                  onClick={box(`years=${year}`)}
                  className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-surface-3"
                >
                  <span className="font-medium">{year}</span> <span className="text-muted">{count}</span>
                </button>
              ))}
          </div>
        </Card>
      )}
    </>
  );
}

export function DashboardPage() {
  return <RequireAccount>{(id) => <Dashboard accountId={id} />}</RequireAccount>;
}
