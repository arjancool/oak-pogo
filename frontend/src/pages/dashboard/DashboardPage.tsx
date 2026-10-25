import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { z } from "zod";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { CleanupBadge, IvPercent, PokemonSprite, pokemonName } from "../../components/pokemon";
import { Alert, Card, EmptyState, PageHeader, Spinner, Stat } from "../../components/ui";
import { useAccount } from "../../lib/account";
import { api } from "../../lib/api";
import { dateTime, num, relative } from "../../lib/format";
import { classificationLabels, label } from "../../lib/i18n";
import { pokemonSummary, type PokemonSummary } from "../../lib/schemas";
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
      warnings: z.array(z.object({ code: z.string(), message: z.string() })),
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
  if (data.error || !data.data) return <Alert tone="error">Het dashboard kon niet geladen worden.</Alert>;
  const d = data.data;
  const c = d.cards;
  const box = (query: string) => () => navigate(`/pokemon?${query}`);

  if (!c.total && !d.last_sync) {
    return (
      <>
        <PageHeader title={`Welkom bij OAK${account ? `, ${account.nickname}` : ""}`} />
        <EmptyState title="Nog geen Pokémon geïmporteerd">
          Koppel PGSharp onder <b>Beheer → PGSharp Sync</b> of upload daar een <code>PGSStats.json</code>. Na de eerste import
          verschijnt hier je collectie.
        </EmptyState>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Overzicht"
        description={account?.source_nickname ? `${account.source_nickname} · level ${account.trainer_level ?? "?"}` : undefined}
      />
      {!d.game_data && (
        <div className="mb-4">
          <Alert tone="warning" title="Geen Game Data">
            Zonder Game Data zijn soortnamen, levels, PvP-analyses en cleanup-adviezen niet beschikbaar. Werk de Game Data bij onder
            Beheer.
          </Alert>
        </div>
      )}
      {sync.data && (
        <Card
          className="mb-5"
          title="Synchronisatie"
          actions={<span className="text-xs text-muted">Laatste succesvolle sync: {dateTime(sync.data.last_successful_sync_at)}</span>}
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <Stat label="Status" value={sync.data.message} />
            <Stat label="Pokémon in export" value={num(d.last_sync?.total ?? null, "–")} />
            <Stat label="Nieuw" value={num(d.last_sync?.new ?? null, "–")} onClick={box("new=true")} />
            <Stat label="Gewijzigd" value={num(d.last_sync?.changed ?? null, "–")} onClick={() => navigate("/history?kind=changed")} />
            <Stat
              label="Niet meer in inventaris"
              value={num(d.last_sync?.missing ?? null, "–")}
              hint={d.last_sync?.missing_unconfirmed ? `${d.last_sync.missing_unconfirmed} niet bevestigd (gedeeltelijke import)` : undefined}
              onClick={() => navigate("/history?kind=missing")}
            />
          </div>
          {d.last_sync && (
            <p className="mt-3 text-xs text-muted">
              {label(classificationLabels, d.last_sync.classification)} · {relative(d.last_sync.applied_at)}
              {d.last_sync.warnings.map((w) => (
                <span key={w.code} className="ml-2 text-amber-300">
                  {w.message}
                </span>
              ))}
            </p>
          )}
        </Card>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-8">
        <Stat label="Totaal Pokémon" value={num(c.total ?? 0)} onClick={box("")} />
        <Stat label="Shiny" value={num(c.shiny ?? 0)} onClick={box("shiny=true")} accent="#f472b6" />
        <Stat label="Lucky" value={num(c.lucky ?? 0)} onClick={box("lucky=true")} accent="#eab308" />
        <Stat label="Shadow" value={num(c.shadow ?? 0)} onClick={box("shadow=true")} accent="#a855f7" />
        <Stat label="Hundo" value={num(c.hundo ?? 0)} onClick={box("hundo=true")} accent="#ef4444" />
        <Stat label="Shundo" value={num(c.shundo ?? 0)} onClick={box("shundo=true")} />
        <Stat label="Favorieten" value={num(c.favorite ?? 0)} onClick={box("favorite=true")} accent="#facc15" />
        <Stat label="Vintage 2016–2019" value={num(c.vintage ?? 0)} onClick={box("vintage=true")} accent="#d97706" />
        <Stat label="Legendary" value={num(c.legendary ?? 0)} onClick={box("legendary=true")} />
        <Stat label="Mythical" value={num(c.mythical ?? 0)} onClick={box("mythical=true")} />
        <Stat label="Dynamax" value={num(c.dynamax ?? 0)} onClick={box("dynamax=true")} />
        <Stat label="Gigantamax" value={num(c.gigantamax ?? 0)} onClick={box("gigantamax=true")} />
        <Stat label="Cleanup-kandidaten" value={num(c.cleanup_candidates ?? 0)} onClick={() => navigate("/cleanup")} accent="#f87171" />
        <Stat label="Te beoordelen" value={num(c.review ?? 0)} onClick={() => navigate("/cleanup?status=REVIEW")} accent="#fbbf24" />
        <Stat label="Stardust" value={num(c.stardust)} />
        <Stat
          label="Vrije opslag"
          value={c.storage_free === null || c.storage_free === undefined ? "onbekend" : num(c.storage_free)}
          hint={c.storage_max ? `van ${num(c.storage_max)}` : undefined}
        />
        <Stat label="Achtergronden" value={num(c.background ?? 0)} onClick={box("background=true")} />
        <Stat label="Op actielijst" value={num(c.action_list_open ?? 0)} onClick={() => navigate("/cleanup?tab=list")} />
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Card title="Laatst gevangen">
          <MiniList items={d.recent_catches} empty="Geen vangstdatum bekend." />
        </Card>
        <Card title="Nieuw sinds vorige sync">
          <MiniList items={d.new_since_last_sync} empty="Geen nieuwe Pokémon, of dit was de eerste synchronisatie." />
        </Card>
        <Card title="Niet meer in inventaris">
          <MiniList items={d.missing_since_last_sync} empty="Niets verdwenen bij de laatste volledige sync." />
        </Card>
        <Card title="Nieuwe waardevolle Pokémon">
          <MiniList items={d.valuable_new} empty="Geen nieuwe shiny, hundo, lucky of legendary." />
        </Card>
        <Card title="Beste investeringskandidaten">
          <MiniList items={d.investment_candidates} empty="Nog geen BUILD-adviezen." />
        </Card>
        <Card title="Aanbevolen cleanup" actions={<span className="text-xs text-muted">{d.favorite_changes} favorieten gewijzigd</span>}>
          <MiniList items={d.top_cleanup} empty="Geen transfer-kandidaten." />
        </Card>
      </div>
      {Object.keys(d.year_distribution).length > 0 && (
        <Card className="mt-5" title="Vangstjaar">
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
