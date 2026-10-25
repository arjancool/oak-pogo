import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Copy, Download, Printer, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { z } from "zod";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { ConfirmTransferDialog } from "../../components/cleanup/ConfirmTransferDialog";
import { CleanupBadge, IvPercent, PokemonSprite, ScoreMeter, StatusBadges, pokemonName } from "../../components/pokemon";
import { Alert, Badge, Button, Card, Checkbox, EmptyState, Input, PageHeader, Pagination, Select, Spinner, Switch, Tabs } from "../../components/ui";
import { api, buildUrl, errorMessage } from "../../lib/api";
import { dateTime, ivs, num, pct } from "../../lib/format";
import { confidenceLabels, label, statusDescriptions, statusLabels } from "../../lib/i18n";
import { actionList, actionListUpdate, cleanupPage, pokemonSummary, type CleanupItem, type ConfirmationItem } from "../../lib/schemas";
import type { Rules } from "../../lib/types";
import { useUrlState } from "../../lib/useUrlState";

type Tab = "recommendations" | "duplicates" | "list" | "rules";
const STATUS_ORDER = ["TRANSFER_CANDIDATE", "REVIEW", "BUILD", "KEEP", "PROTECT", "UNKNOWN"];

const PAGE_SIZE = 50;
const POLL_MS = 3_000;

function ScoreBreakdown({ item }: { item: CleanupItem }) {
  const battle = item.scores.battle;
  const keep = item.scores.keep;
  return (
    <details className="mt-1 text-xs">
      <summary className="cursor-pointer text-muted">Hoe zijn de scores opgebouwd?</summary>
      <div className="mt-2 grid gap-3 md:grid-cols-2">
        <div>
          <p className="font-medium">Bruikbaarheid {item.battle_score ?? "onbekend"}</p>
          <p className="text-muted">De hoogste waarde telt, niet de som, zodat dezelfde IV&apos;s niet dubbel meetellen.</p>
          <ul className="mt-1 space-y-0.5">
            {battle?.parts.map((part, index) => (
              <li key={index} className={clsx("flex justify-between gap-3", part.code === battle.basis && "font-semibold")}>
                <span>{part.text}</span>
                <span className="tabular-nums">{Math.round(part.value)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="font-medium">Bewaarscore {item.keep_score ?? "onbekend"}</p>
          <p className="text-muted">
            Punten opgeteld, maximaal 100. Bewaren vanaf {keep?.keep_threshold}, beoordelen vanaf {keep?.review_threshold}.
          </p>
          <ul className="mt-1 space-y-0.5">
            {keep?.parts.map((part, index) => (
              <li key={index} className="flex justify-between gap-3">
                <span>{part.text}</span>
                <span className="tabular-nums">+{Math.round(part.value)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </details>
  );
}

function SimilarList({ item }: { item: CleanupItem }) {
  if (!item.alternatives.length) return <p className="text-xs text-muted">Geen andere exemplaren van deze soort en vorm.</p>;
  return (
    <div className="mt-1 text-xs">
      <span className="text-muted">Vergelijkbaar: </span>
      {item.alternatives.map((alt, index) => (
        <span key={alt.pokemon_id}>
          {index > 0 && <span className="text-muted"> · </span>}
          <Link to={`/pokemon/${alt.pokemon_id}`} className="hover:text-oak-300">
            CP {num(alt.cp, "?")}
          </Link>{" "}
          <span className="text-muted">
            {pct(alt.iv_percent, 0)} · bruikbaarheid {alt.battle_score ?? "?"} · bewaar {alt.keep_score ?? "?"}
            {alt.caught_year ? ` · ${alt.caught_year}` : ""}
          </span>{" "}
          <CleanupBadge status={alt.status} />
          {alt.better && <span className="ml-1 text-emerald-300">beter</span>}
        </span>
      ))}
    </div>
  );
}

function RecommendationRow({ item, selected, onSelect }: { item: CleanupItem; selected: boolean; onSelect?: (value: boolean) => void }) {
  return (
    <div className="flex flex-wrap items-start gap-3 rounded-xl border border-line bg-surface p-3">
      {onSelect && <Checkbox checked={selected} disabled={item.in_action_list} onChange={onSelect} />}
      <PokemonSprite dex={item.pokemon.species_id} shiny={item.pokemon.shiny} types={item.pokemon.types} size={44} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Link to={`/pokemon/${item.pokemon.id}`} className="font-medium hover:text-oak-300">
            {pokemonName(item.pokemon)}
          </Link>
          <span className="text-sm tabular-nums">CP {num(item.pokemon.cp, "?")}</span>
          <span className="font-mono text-xs text-muted">{ivs(item.pokemon.iv_attack, item.pokemon.iv_defense, item.pokemon.iv_stamina)}</span>
          <IvPercent value={item.pokemon.iv_percent} />
          <CleanupBadge status={item.status} />
          <Badge>Betrouwbaarheid {label(confidenceLabels, item.confidence)}</Badge>
          {item.in_action_list && <Badge color="#38bdf8">Op actielijst</Badge>}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
          <ScoreMeter label="Bruikbaarheid" value={item.battle_score} title="Feitelijke waarde in gevechten, 0–100" />
          <ScoreMeter label="Bewaarscore" value={item.keep_score} title="Reden om te bewaren, 0–100" />
          <StatusBadges pokemon={item.pokemon} compact />
        </div>
        {item.protection_reasons.length > 0 && (
          <p className="mt-1 text-xs text-sky-300">Bescherming: {item.protection_reasons.map((r) => r.text).join(" · ")}</p>
        )}
        {item.warnings.length > 0 && <p className="mt-1 text-xs text-amber-300">{item.warnings.map((w) => w.text).join(" · ")}</p>}
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-muted">
          {item.reasons.map((r, i) => (
            <li key={i}>{r.text}</li>
          ))}
        </ul>
        <SimilarList item={item} />
        <ScoreBreakdown item={item} />
      </div>
    </div>
  );
}

const SELECTABLE = new Set(["TRANSFER_CANDIDATE", "REVIEW"]);
const TRISTATE = [
  { value: "", text: "alle" },
  { value: "true", text: "alleen" },
  { value: "false", text: "zonder" },
];
const GYM_FILTERS = [
  { value: "", text: "Gyms: alle" },
  { value: "best", text: "Gyms: beste verdediger per soort" },
  { value: "in_gym", text: "Gyms: staat nu in een gym" },
];

function Recommendations({ accountId }: { accountId: number }) {
  const [state, update] = useUrlState();
  const client = useQueryClient();
  const status = state.status ?? "TRANSFER_CANDIDATE";
  const sort = state.sort ?? "priority";
  const page = Number(state.page ?? 1);
  const favorite = state.favorite ?? "";
  const vintage = state.vintage ?? "";
  const gym = state.gym ?? "";
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState<ConfirmationItem[]>([]);
  const query = useQuery({
    queryKey: ["cleanup", accountId, status, sort, page, favorite, vintage, gym],
    queryFn: async () =>
      cleanupPage.parse(
        await api.get("/api/v1/cleanup/recommendations", {
          account_id: accountId,
          status: status === "ALL" ? null : status,
          favorite: favorite || null,
          vintage: vintage || null,
          gym: gym || null,
          sort,
          page,
          page_size: PAGE_SIZE,
        }),
      ),
    refetchInterval: (q) => (q.state.data?.analysis.pending ? POLL_MS : false),
  });
  const analyze = useMutation({
    mutationFn: () => api.post("/api/v1/cleanup/analyze", undefined, { account_id: accountId }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["cleanup"] }),
  });
  const addToList = useMutation({
    mutationFn: async (body: { ids: number[]; confirmed_ids?: number[] }) =>
      actionListUpdate.parse(await api.post("/api/v1/cleanup/action-list", { account_id: accountId, mode: "add", ...body })),
    onSuccess: (result) => {
      const parts = [`Actielijst bevat nu ${result.count} Pokémon.`];
      if (result.skipped.length) parts.push(`${result.skipped.length} overgeslagen: ${[...new Set(result.skipped.map((s) => s.reason))].join("; ")}.`);
      if (result.needs_confirmation.length) parts.push(`${result.needs_confirmation.length} wachten op je bevestiging.`);
      setMessage(parts.join(" "));
      setPending(result.needs_confirmation);
      setSelected(new Set());
      void client.invalidateQueries({ queryKey: ["cleanup"] });
      void client.invalidateQueries({ queryKey: ["action-list"] });
    },
    onError: (error) => setMessage(errorMessage(error)),
  });
  const data = query.data;
  const counts = data?.analysis.counts ?? {};
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  const select = (id: number) => (checked: boolean) =>
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  return (
    <div className="space-y-4">
      {data && (
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
          <span>
            Analyse {data.analysis.computed_at ? dateTime(data.analysis.computed_at) : "nog niet uitgevoerd"} · engine {data.analysis.engine_version} · Game Data v
            {data.analysis.game_data_version ?? "–"}
            {data.analysis.stale && <span className="ml-2 text-amber-300">Verouderd: gegevens of regels zijn gewijzigd</span>}
            {data.analysis.pending && <span className="ml-2 text-sky-300">Wordt opnieuw berekend…</span>}
          </span>
          <Button size="sm" variant="outline" icon={<RefreshCw className="h-3.5 w-3.5" />} loading={analyze.isPending} onClick={() => analyze.mutate()}>
            Opnieuw analyseren
          </Button>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {["ALL", ...STATUS_ORDER].map((s) => (
          <button
            key={s}
            onClick={() => update({ status: s })}
            title={s === "ALL" ? "Alle Pokémon" : statusDescriptions[s]}
            className={clsx(
              "rounded-lg border px-3 py-2 text-left text-sm",
              s === status ? "border-oak-500 bg-oak-500/10" : "border-line hover:bg-surface-3",
            )}
          >
            <span className="block text-xs text-muted">{s === "ALL" ? "Alle" : statusLabels[s]}</span>
            <span className="font-semibold tabular-nums">{num(s === "ALL" ? total : (counts[s] ?? 0))}</span>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={sort} onChange={(e) => update({ sort: e.target.value })} aria-label="Sorteren">
          <option value="priority">Prioriteit</option>
          <option value="keep">Bewaarscore laag–hoog</option>
          <option value="-keep">Bewaarscore hoog–laag</option>
          <option value="-battle">Bruikbaarheid hoog–laag</option>
          <option value="battle">Bruikbaarheid laag–hoog</option>
          <option value="cp">CP laag–hoog</option>
          <option value="-cp">CP hoog–laag</option>
          <option value="name">Naam</option>
          <option value="iv">IV laag–hoog</option>
        </Select>
        <Select value={favorite} onChange={(e) => update({ favorite: e.target.value || null })} aria-label="Favorieten">
          {TRISTATE.map((o) => (
            <option key={o.value} value={o.value}>
              Favorieten: {o.text}
            </option>
          ))}
        </Select>
        <Select value={vintage} onChange={(e) => update({ vintage: e.target.value || null })} aria-label="Vintage">
          {TRISTATE.map((o) => (
            <option key={o.value} value={o.value}>
              Vintage (2016–2019): {o.text}
            </option>
          ))}
        </Select>
        <Select
          value={gym}
          // A best defender is usually kept, so a gym filter looks at every status.
          onChange={(e) => update(e.target.value ? { gym: e.target.value, status: "ALL" } : { gym: null })}
          aria-label="Gyms"
        >
          {GYM_FILTERS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.text}
            </option>
          ))}
        </Select>
        {selected.size > 0 && (
          <Button variant="primary" onClick={() => addToList.mutate({ ids: [...selected] })} loading={addToList.isPending}>
            {selected.size} op actielijst zetten
          </Button>
        )}
        {SELECTABLE.has(status) && data && data.items.length > 0 && (
          <Button variant="outline" onClick={() => setSelected(new Set(data.items.filter((i) => !i.in_action_list && i.pokemon.vintage_year === null).map((i) => i.pokemon.id)))}>
            Hele pagina selecteren
          </Button>
        )}
      </div>
      {message && <Alert tone="info">{message}</Alert>}
      {query.isLoading ? (
        <Spinner />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="Geen Pokémon met deze filters">{status !== "ALL" ? statusDescriptions[status] : undefined}</EmptyState>
      ) : (
        <div className="space-y-2">
          {data.items.map((item: CleanupItem) => (
            <RecommendationRow
              key={item.pokemon.id}
              item={item}
              selected={selected.has(item.pokemon.id)}
              onSelect={SELECTABLE.has(item.status) && item.pokemon.vintage_year === null ? select(item.pokemon.id) : undefined}
            />
          ))}
          <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPage={(p) => update({ page: String(p) }, false)} />
        </div>
      )}
      <ConfirmTransferDialog
        key={pending.map((p) => p.pokemon_id).join(",")}
        items={pending}
        busy={addToList.isPending}
        onCancel={() => setPending([])}
        onConfirm={(ids) => addToList.mutate({ ids, confirmed_ids: ids })}
      />
    </div>
  );
}

const duplicatesSchema = z.object({
  total_groups: z.number(),
  groups: z.array(
    z.object({
      group_key: z.string(),
      name: z.string(),
      shadow: z.boolean(),
      count: z.number(),
      statuses: z.record(z.string(), z.number()),
      members: z.array(
        pokemonSummary.extend({
          recommendation: z
            .object({
              status: z.string(),
              reasons: z.array(z.object({ code: z.string(), text: z.string() })),
              roles: z.array(z.record(z.string(), z.unknown())),
              battle_score: z.number().nullable(),
              keep_score: z.number().nullable(),
            })
            .nullable(),
        }),
      ),
    }),
  ),
});

function Duplicates({ accountId }: { accountId: number }) {
  const [filter, setFilter] = useState("");
  const query = useQuery({
    queryKey: ["duplicates", accountId],
    queryFn: async () => duplicatesSchema.parse(await api.get("/api/v1/cleanup/duplicates", { account_id: accountId })),
  });
  if (query.isLoading) return <Spinner />;
  const groups = (query.data?.groups ?? []).filter((g) => g.name.toLowerCase().includes(filter.toLowerCase()));
  return (
    <div className="space-y-3">
      <Input placeholder="Soort zoeken…" value={filter} onChange={(e) => setFilter(e.target.value)} className="max-w-xs" />
      <p className="text-xs text-muted">
        Pokémon van dezelfde soort, vorm en Shadow-status naast elkaar, hoogste bruikbaarheid eerst. Favorieten en vintage Pokémon doen gewoon
        mee in de vergelijking.
      </p>
      {groups.map((group) => (
        <Card
          key={group.group_key}
          title={`${group.name}${group.shadow ? " (Shadow)" : ""} · ${group.count}×`}
          actions={STATUS_ORDER.filter((s) => group.statuses[s]).map((s) => (
            <Badge key={s}>
              {statusLabels[s]} {group.statuses[s]}
            </Badge>
          ))}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm [&_td]:pr-3 [&_th]:pr-3">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-1">CP</th>
                  <th>IV's</th>
                  <th>IV%</th>
                  <th>Level</th>
                  <th>Aanvallen</th>
                  <th>GL / UL</th>
                  <th title="Bruikbaarheid in gevechten, 0–100">Bruikb.</th>
                  <th title="Bewaarscore, 0–100">Bewaar</th>
                  <th>Advies</th>
                  <th>Waarom</th>
                </tr>
              </thead>
              <tbody>
                {group.members.map((m) => (
                  <tr key={m.id} className="border-t border-line">
                    <td className="py-1.5">
                      <Link to={`/pokemon/${m.id}`} className="font-medium hover:text-oak-300">
                        {num(m.cp, "?")}
                      </Link>
                    </td>
                    <td className="font-mono text-xs">{ivs(m.iv_attack, m.iv_defense, m.iv_stamina)}</td>
                    <td>
                      <IvPercent value={m.iv_percent} />
                    </td>
                    <td>{m.level ?? "?"}</td>
                    <td className="text-xs">{[m.fast_move?.name, ...m.charged_moves.map((c) => c.name)].filter(Boolean).join(" · ")}</td>
                    <td className="tabular-nums">
                      {m.pvp.great.rank ?? "–"} / {m.pvp.ultra.rank ?? "–"}
                    </td>
                    <td className="tabular-nums">{m.recommendation?.battle_score ?? "–"}</td>
                    <td className="tabular-nums">{m.recommendation?.keep_score ?? "–"}</td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        <CleanupBadge status={m.recommendation?.status} />
                        {m.vintage_year !== null && <Badge color="#d97706">Vintage {m.vintage_year}</Badge>}
                        {m.favorite && <Badge color="#facc15">Favoriet</Badge>}
                      </div>
                    </td>
                    <td className="max-w-md text-xs text-muted">{m.recommendation?.reasons[0]?.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
    </div>
  );
}

function ActionListTab({ accountId }: { accountId: number }) {
  const client = useQueryClient();
  const [sort, setSort] = useState<"cp" | "-cp">("cp");
  const [copied, setCopied] = useState<string | null>(null);
  const [pending, setPending] = useState<ConfirmationItem[]>([]);
  const query = useQuery({
    queryKey: ["action-list", accountId, sort],
    queryFn: async () => actionList.parse(await api.get("/api/v1/cleanup/action-list", { account_id: accountId, sort })),
  });
  const change = useMutation({
    mutationFn: (body: { ids: number[]; mode: string; confirmed_ids?: number[] }) =>
      api.post("/api/v1/cleanup/action-list", { account_id: accountId, ...body }),
    onSuccess: () => {
      setPending([]);
      void client.invalidateQueries({ queryKey: ["action-list"] });
      void client.invalidateQueries({ queryKey: ["cleanup"] });
    },
  });
  if (query.isLoading) return <Spinner />;
  const data = query.data;
  if (!data || data.count === 0) {
    return (
      <EmptyState title="De actielijst is leeg">
        Zet transfer-kandidaten op de lijst vanuit het tabblad Aanbevelingen of de Pokémon Box. Je werkt de lijst daarna zelf in het spel af.
      </EmptyState>
    );
  }
  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text);
    setCopied(text);
  };
  const heldBack = data.items.filter((item) => item.status === "open" && !item.executable).length;
  return (
    <div className="space-y-4">
      <Alert tone="info" title="OAK zet niets over">
        Deze lijst is een hulpmiddel. Zoek iedere Pokémon in het spel op, controleer hem en zet hem zelf over. Daarna markeer je hem hier als
        afgerond, of de volgende volledige synchronisatie ziet dat hij weg is.
      </Alert>
      <div className="no-print flex flex-wrap gap-2">
        <Select value={sort} onChange={(e) => setSort(e.target.value as "cp" | "-cp")}>
          <option value="cp">CP laag–hoog</option>
          <option value="-cp">CP hoog–laag</option>
        </Select>
        <a href={buildUrl("/api/v1/cleanup/export", { account_id: accountId, sort })}>
          <Button variant="outline" icon={<Download className="h-4 w-4" />}>
            CSV
          </Button>
        </a>
        <a href={buildUrl("/api/v1/cleanup/export", { account_id: accountId, sort, format: "html" })} target="_blank" rel="noreferrer">
          <Button variant="outline" icon={<Printer className="h-4 w-4" />}>
            Printbare checklist
          </Button>
        </a>
        <Button variant="ghost" onClick={() => change.mutate({ ids: [], mode: "clear" })}>
          Lijst leegmaken
        </Button>
      </div>
      {heldBack > 0 && (
        <Alert tone="warning" title={`${heldBack} Pokémon tegengehouden`}>
          Hun bescherming is veranderd sinds ze op de lijst kwamen, of ze staan niet meer in je inventaris. Ze staan niet in de zoekopdrachten en
          niet op de checklist.
        </Alert>
      )}
      <Card title="Zoekopdrachten voor Pokémon GO">
        <p className="mb-2 text-xs text-muted">{data.search_hint.note}</p>
        <div className="space-y-1">
          {data.search_hint.queries.map((q) => (
            <div key={q.query} className="flex items-center gap-2">
              <code className="flex-1 truncate rounded bg-surface-3 px-2 py-1 text-xs">{q.query + data.search_hint.safety_suffix}</code>
              <Button size="sm" variant="ghost" icon={<Copy className="h-3.5 w-3.5" />} onClick={() => copy(q.query + data.search_hint.safety_suffix)}>
                {copied === q.query + data.search_hint.safety_suffix ? "Gekopieerd" : "Kopiëren"}
              </Button>
            </div>
          ))}
        </div>
      </Card>
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-left text-xs text-muted">
            <tr>
              <th className="px-3 py-2">Pokémon</th>
              <th>CP</th>
              <th>IV</th>
              <th>Reden</th>
              <th>Bescherming</th>
              <th>Bron-ID</th>
              <th className="no-print" />
            </tr>
          </thead>
          <tbody>
            {data.items.map((item) => (
              <tr key={item.pokemon.id} className={clsx("border-t border-line", item.status !== "open" && "opacity-50")}>
                <td className="px-3 py-2">
                  <Link to={`/pokemon/${item.pokemon.id}`} className="font-medium hover:text-oak-300">
                    {pokemonName(item.pokemon)}
                  </Link>
                  {!item.still_in_inventory && <Badge className="ml-2">Niet meer in inventaris</Badge>}
                  {item.blocked && (
                    <Badge className="ml-2" color="#f87171">
                      Tegengehouden: {item.blocked}
                    </Badge>
                  )}
                  {item.needs_confirmation && (
                    <Badge className="ml-2" color="#fbbf24">
                      Opnieuw bevestigen:{" "}
                      {item.needs_confirmation.new_reasons.length ? `nieuw ${item.needs_confirmation.new_reasons.join(", ")}` : item.needs_confirmation.message}
                    </Badge>
                  )}
                </td>
                <td className="tabular-nums">{num(item.pokemon.cp, "?")}</td>
                <td className="font-mono text-xs">{ivs(item.pokemon.iv_attack, item.pokemon.iv_defense, item.pokemon.iv_stamina)}</td>
                <td className="max-w-xs text-xs text-muted">{item.reason}</td>
                <td className="text-xs">{item.protection.length ? <span className="text-amber-300">{item.protection.join(", ")}</span> : "–"}</td>
                <td className="font-mono text-[10px] text-muted">{item.pokemon.source_pokemon_id}</td>
                <td className="no-print whitespace-nowrap pr-3 text-right">
                  {item.needs_confirmation && (
                    <Button size="sm" variant="ghost" onClick={() => setPending(item.needs_confirmation ? [item.needs_confirmation] : [])}>
                      Bevestigen
                    </Button>
                  )}
                  {item.status === "open" && item.executable && (
                    <Button size="sm" variant="ghost" onClick={() => change.mutate({ ids: [item.pokemon.id], mode: "done" })}>
                      Afgerond
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => change.mutate({ ids: [item.pokemon.id], mode: "remove" })}>
                    Verwijderen
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ConfirmTransferDialog
        key={pending.map((p) => p.pokemon_id).join(",")}
        items={pending}
        busy={change.isPending}
        onCancel={() => setPending([])}
        onConfirm={(ids) => change.mutate({ ids, mode: "add", confirmed_ids: ids })}
      />
    </div>
  );
}

const PROTECTION_RULES: Record<string, [string, string?]> = {
  protect_shiny: ["Shiny's"],
  protect_lucky: ["Lucky Pokémon"],
  protect_hundo: ["Hundo's en shundo's"],
  protect_location_card: ["Speciale achtergronden"],
  protect_costume: ["Kostuums"],
  protect_mythical: ["Mythical"],
  protect_legendary: ["Legendary"],
  protect_ultra_beast: ["Ultra Beasts"],
  protect_shadow: ["Shadow Pokémon"],
  protect_purified: ["Purified Pokémon"],
  protect_dynamax: ["Dynamax"],
  protect_gigantamax: ["Gigantamax"],
  protect_event: ["Event-Pokémon", "Met event-herkomst of beperkte uitgave"],
  protect_nicknamed: ["Pokémon met bijnaam"],
  protect_mega_progress: ["Pokémon met mega-voortgang"],
};
const ROLE_RULES: Record<string, [string, string?]> = {
  keep_best_great: ["Bewaar altijd de beste Great League-kandidaat"],
  keep_best_ultra: ["Bewaar altijd de beste Ultra League-kandidaat"],
  keep_best_master: ["Bewaar het beste Master League-exemplaar"],
  keep_best_raid: ["Bewaar de beste raid-aanvaller", "Hoogste Attack-IV binnen relevante soorten"],
  keep_best_gym: ["Bewaar de beste gymverdediger", "Meeste Defense en HP binnen de beste verdedigerssoorten"],
  elite_tm_available: ["Ik heb Elite TM's", "Movesetadvies en raidwaarde mogen Elite TM-aanvallen gebruiken"],
  include_best_buddy: ["Rekenen met Best Buddy (+1 level)"],
  consider_costs: ["Houd rekening met resourcekosten"],
  allow_transfer_on_partial_import: ["Transferadvies ook na een gedeeltelijke import", "Standaard uit: dan krijgt alles hooguit 'Beoordelen'"],
  use_events: ["Houd rekening met komende events", "Bewaar een transfer-kandidaat tot na de Community Day van zijn evolutielijn"],
};
const KEEP_RULES: Record<string, [string, string]> = {
  keep_weight_battle: ["Aandeel bruikbaarheid", "Procent van de bruikbaarheidsscore dat meetelt"],
  keep_points_best_copy: ["Beste of enige exemplaar", "Punten"],
  keep_points_favorite: ["Favoriet", "Punten. Telt nooit mee in de bruikbaarheid"],
  keep_points_shiny: ["Shiny", "Punten"],
  keep_points_lucky: ["Lucky", "Punten"],
  keep_points_rarity: ["Legendary, Mythical, Ultra Beast", "Punten"],
  keep_points_costume: ["Kostuum", "Punten"],
  keep_points_location_card: ["Speciale achtergrond", "Punten"],
  keep_points_event: ["Event-Pokémon", "Punten"],
  keep_points_max: ["Dynamax of Gigantamax", "Punten"],
  keep_points_mega: ["Mega-voortgang", "Punten"],
  keep_traits_cap: ["Maximum voor bijzondere kenmerken samen", "Punten"],
  keep_points_nickname: ["Bijnaam", "Punten"],
  keep_points_planned: ["Eigen plan in OAK", "Punten, niet bij plan 'overzetten'"],
  keep_threshold: ["Bewaren vanaf bewaarscore", "0–100"],
  review_threshold: ["Beoordelen vanaf bewaarscore", "0–100, daaronder transfer-kandidaat"],
};
const ANALYSIS_RULES: Record<string, [string, string]> = {
  keep_min_per_species: ["Minimaal aantal exemplaren per soort", "0–10. Het beste exemplaar blijft altijd"],
  meta_rank_threshold: ["Soort telt mee tot PvPoke-rang", "Hoe lager, hoe strenger"],
  species_rank_full: ["Soort telt volledig tot PvPoke-rang", "Daaronder loopt het gewicht af"],
  raid_top_n: ["Raidwaarde tot plaats", "Plaats tussen alle aanvallers van een type"],
  gym_top_n: ["Gymwaarde tot plaats", "Plaats tussen alle soorten die in een gym mogen"],
  good_iv_rank_threshold: ["IV-rang die altijd tot review leidt", "Van 4096"],
  build_iv_rank_threshold: ["Maximale IV-rang voor investeringsadvies", "Van 4096"],
  ready_cp_fraction: ["Direct inzetbaar vanaf fractie van de beste CP", "0,5–1"],
  max_level: ["Maximaal level", "Volgens Game Data meestal 50"],
  event_hold_days: ["Events tellen mee vanaf dagen ervoor", "0–60"],
};
const STEPS: Record<string, number> = { ready_cp_fraction: 0.01, max_level: 0.5 };

function NumberRules({ rules, entries, set }: { rules: Rules; entries: Record<string, [string, string]>; set: (key: string, value: number | null) => void }) {
  return (
    <div className="space-y-3">
      {Object.entries(entries).map(([key, [text, hint]]) => (
        <label key={key} className="grid grid-cols-[minmax(0,1fr)_6rem] items-center gap-3">
          <span>
            <span className="block text-sm">{text}</span>
            <span className="block text-xs text-muted">{hint}</span>
          </span>
          <Input
            type="number"
            step={STEPS[key] ?? 1}
            value={rules[key] === null || rules[key] === undefined ? "" : String(rules[key])}
            onChange={(e) => set(key, e.target.value === "" ? null : Number(e.target.value))}
          />
        </label>
      ))}
    </div>
  );
}

function RulesTab({ accountId }: { accountId: number }) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["rules", accountId],
    queryFn: () =>
      api.get<{ rules: Rules; defaults: Rules; engine_version: string; fixed: { code: string; text: string }[] }>("/api/v1/cleanup/rules", {
        account_id: accountId,
      }),
  });
  const [draft, setDraft] = useState<Rules | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const save = useMutation({
    mutationFn: (rules: Rules) => api.put("/api/v1/cleanup/rules", { rules }, { account_id: accountId }),
    onSuccess: () => {
      setMessage({ tone: "success", text: "Regels opgeslagen. De analyse wordt opnieuw berekend." });
      setDraft(null);
      void client.invalidateQueries({ queryKey: ["rules"] });
      void client.invalidateQueries({ queryKey: ["cleanup"] });
    },
    onError: (error) => setMessage({ tone: "error", text: errorMessage(error) }),
  });
  if (query.isLoading || !query.data) return <Spinner />;
  const rules = draft ?? query.data.rules;
  const set = (key: string, value: boolean | number | null) => setDraft({ ...rules, [key]: value });
  return (
    <div className="space-y-5">
      <Card title="Vaste regels">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {query.data.fixed.map((rule) => (
            <li key={rule.code}>{rule.text}</li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted">
          Deze regels staan vast. Wil je één vintage Pokémon toch kwijt, hef de bescherming dan op bij die Pokémon. OAK vraagt daar een
          bevestiging voor.
        </p>
      </Card>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Harde bescherming">
          <p className="mb-2 text-xs text-muted">
            Wat hier aan staat, krijgt altijd 'Beschermd', hoe laag de scores ook zijn. Zet je een regel uit, dan telt het kenmerk alleen nog
            als punten in de bewaarscore.
          </p>
          {Object.entries(PROTECTION_RULES).map(([key, [text, description]]) => (
            <Switch key={key} checked={Boolean(rules[key])} onChange={(v) => set(key, v)} label={text} description={description} />
          ))}
        </Card>
        <Card title="Bewaarscore (0–100)">
          <p className="mb-3 text-xs text-muted">
            Iedere eigenschap telt één keer. IV&apos;s tellen alleen via de bruikbaarheid. Favorieten krijgen extra punten maar geen harde
            bescherming.
          </p>
          <NumberRules rules={rules} entries={KEEP_RULES} set={set} />
        </Card>
        <Card title="Rollen en spelinstellingen">
          {Object.entries(ROLE_RULES).map(([key, [text, description]]) => (
            <Switch key={key} checked={Boolean(rules[key])} onChange={(v) => set(key, v)} label={text} description={description} />
          ))}
        </Card>
        <Card title="Analyse en drempels">
          <NumberRules rules={rules} entries={ANALYSIS_RULES} set={set} />
        </Card>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={!draft} loading={save.isPending} onClick={() => draft && save.mutate(draft)}>
          Opslaan
        </Button>
        <Button variant="outline" onClick={() => setDraft(query.data.defaults)}>
          Standaardwaarden
        </Button>
        <span className="text-xs text-muted">Engine {query.data.engine_version}</span>
      </div>
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
    </div>
  );
}

function Cleanup({ accountId }: { accountId: number }) {
  const [state, update] = useUrlState();
  const tab = (state.tab as Tab) ?? "recommendations";
  return (
    <>
      <PageHeader
        title="Cleanup Manager"
        description="Uitlegbaar advies over welke Pokémon je bewaart, opbouwt of kunt overzetten. OAK voert zelf nooit een transfer uit."
      />
      <Tabs
        value={tab}
        onChange={(value) => update({ tab: value === "recommendations" ? null : value, status: null, sort: null })}
        tabs={[
          { value: "recommendations", label: "Aanbevelingen" },
          { value: "duplicates", label: "Dubbelen" },
          { value: "list", label: "Actielijst" },
          { value: "rules", label: "Regels" },
        ]}
      />
      <div className="mt-4">
        {tab === "recommendations" && <Recommendations accountId={accountId} />}
        {tab === "duplicates" && <Duplicates accountId={accountId} />}
        {tab === "list" && <ActionListTab accountId={accountId} />}
        {tab === "rules" && <RulesTab accountId={accountId} />}
      </div>
    </>
  );
}

export function CleanupPage() {
  return <RequireAccount>{(id) => <Cleanup accountId={id} />}</RequireAccount>;
}
