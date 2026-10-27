import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import type { ParseKeys } from "i18next";
import { Copy, Download, Printer, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { z } from "zod";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { ConfirmTransferDialog, newReasons } from "../../components/cleanup/ConfirmTransferDialog";
import { CleanupBadge, IvPercent, PokemonSprite, ScoreMeter, StatusBadges, pokemonName } from "../../components/pokemon";
import { Alert, Badge, Button, Card, Checkbox, EmptyState, Input, PageHeader, Pagination, Select, Spinner, Switch, Tabs } from "../../components/ui";
import { api, buildUrl, errorMessage } from "../../lib/api";
import { dateTime, ivs, num, pct } from "../../lib/format";
import { confidenceLabels, label, statusDescriptions, statusLabels } from "../../lib/i18n";
import { actionList, actionListUpdate, cleanupPage, pokemonSummary, type CleanupItem, type ConfirmationItem } from "../../lib/schemas";
import { serverText } from "../../lib/serverText";
import type { Rules } from "../../lib/types";
import { useUrlState } from "../../lib/useUrlState";

type Tab = "recommendations" | "duplicates" | "list" | "rules";
const STATUS_ORDER = ["TRANSFER_CANDIDATE", "REVIEW", "BUILD", "KEEP", "PROTECT", "UNKNOWN"];

const PAGE_SIZE = 50;
const POLL_MS = 3_000;

function ScoreBreakdown({ item }: { item: CleanupItem }) {
  const { t } = useTranslation();
  const battle = item.scores.battle;
  const keep = item.scores.keep;
  return (
    <details className="mt-1 text-xs">
      <summary className="cursor-pointer text-muted">{t("cleanup.breakdown.summary")}</summary>
      <div className="mt-2 grid gap-3 md:grid-cols-2">
        <div>
          <p className="font-medium">{t("cleanup.breakdown.battle", { score: num(item.battle_score) })}</p>
          <p className="text-muted">{t("cleanup.breakdown.battleNote")}</p>
          <ul className="mt-1 space-y-0.5">
            {battle?.parts.map((part, index) => (
              <li key={index} className={clsx("flex justify-between gap-3", part.code === battle.basis && "font-semibold")}>
                <span>{serverText("parts", part)}</span>
                <span className="tabular-nums">{Math.round(part.value)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="font-medium">{t("cleanup.breakdown.keep", { score: num(item.keep_score) })}</p>
          <p className="text-muted">
            {t("cleanup.breakdown.keepNote", { keep: num(keep?.keep_threshold, ""), review: num(keep?.review_threshold, "") })}
          </p>
          <ul className="mt-1 space-y-0.5">
            {keep?.parts.map((part, index) => (
              <li key={index} className="flex justify-between gap-3">
                <span>{serverText("parts", part)}</span>
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
  const { t } = useTranslation();
  if (!item.alternatives.length) return <p className="text-xs text-muted">{t("cleanup.similar.none")}</p>;
  return (
    <div className="mt-1 text-xs">
      <span className="text-muted">{t("cleanup.similar.label")} </span>
      {item.alternatives.map((alt, index) => (
        <span key={alt.pokemon_id}>
          {index > 0 && <span className="text-muted"> · </span>}
          <Link to={`/pokemon/${alt.pokemon_id}`} className="hover:text-oak-300">
            CP {num(alt.cp, "?")}
          </Link>{" "}
          <span className="text-muted">
            {t("cleanup.similar.scores", { iv: pct(alt.iv_percent, 0), battle: num(alt.battle_score, "?"), keep: num(alt.keep_score, "?") })}
            {alt.caught_year ? ` · ${alt.caught_year}` : ""}
          </span>{" "}
          <CleanupBadge status={alt.status} />
          {alt.better && <span className="ml-1 text-emerald-300">{t("cleanup.similar.better")}</span>}
        </span>
      ))}
    </div>
  );
}

function RecommendationRow({ item, selected, onSelect }: { item: CleanupItem; selected: boolean; onSelect?: (value: boolean) => void }) {
  const { t } = useTranslation();
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
          <Badge>{t("cleanup.row.confidence", { level: label(confidenceLabels, item.confidence) })}</Badge>
          {item.in_action_list && <Badge color="#38bdf8">{t("cleanup.row.inActionList")}</Badge>}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
          <ScoreMeter label={t("cleanup.row.battle")} value={item.battle_score} title={t("cleanup.row.battleTitle")} />
          <ScoreMeter label={t("cleanup.row.keep")} value={item.keep_score} title={t("cleanup.row.keepTitle")} />
          <StatusBadges pokemon={item.pokemon} compact />
        </div>
        {item.protection_reasons.length > 0 && (
          <p className="mt-1 text-xs text-sky-300">{t("cleanup.row.protection", { reasons: item.protection_reasons.map((r) => serverText("protections", r)).join(" · ") })}</p>
        )}
        {item.warnings.length > 0 && <p className="mt-1 text-xs text-amber-300">{item.warnings.map((w) => serverText("warnings", w)).join(" · ")}</p>}
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-muted">
          {item.reasons.map((r, i) => (
            <li key={i}>{serverText("reasons", r)}</li>
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
  { value: "", text: "cleanup.filters.all" },
  { value: "true", text: "cleanup.filters.only" },
  { value: "false", text: "cleanup.filters.without" },
] as const;
const GYM_FILTERS = [
  { value: "", text: "cleanup.filters.gym.all" },
  { value: "best", text: "cleanup.filters.gym.best" },
  { value: "in_gym", text: "cleanup.filters.gym.inGym" },
] as const;

function Recommendations({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
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
      const parts = [t("cleanup.recommendations.added", { n: num(result.count) })];
      if (result.skipped.length)
        parts.push(
          t("cleanup.recommendations.skipped", { n: num(result.skipped.length), reasons: [...new Set(result.skipped.map((s) => serverText("guard", s.reason_text ?? s.reason)))].join("; ") }),
        );
      if (result.needs_confirmation.length) parts.push(t("cleanup.recommendations.waiting", { count: result.needs_confirmation.length }));
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
            {t("cleanup.analysis.summary", {
              when: data.analysis.computed_at ? dateTime(data.analysis.computed_at) : t("cleanup.analysis.notRun"),
              engine: data.analysis.engine_version,
              version: data.analysis.game_data_version ?? "–",
            })}
            {data.analysis.stale && <span className="ml-2 text-amber-300">{t("cleanup.analysis.stale")}</span>}
            {data.analysis.pending && <span className="ml-2 text-sky-300">{t("cleanup.analysis.pending")}</span>}
          </span>
          <Button size="sm" variant="outline" icon={<RefreshCw className="h-3.5 w-3.5" />} loading={analyze.isPending} onClick={() => analyze.mutate()}>
            {t("cleanup.analysis.rerun")}
          </Button>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {["ALL", ...STATUS_ORDER].map((s) => (
          <button
            key={s}
            onClick={() => update({ status: s })}
            title={s === "ALL" ? t("cleanup.statusFilter.allTitle") : statusDescriptions[s]}
            className={clsx(
              "rounded-lg border px-3 py-2 text-left text-sm",
              s === status ? "border-oak-500 bg-oak-500/10" : "border-line hover:bg-surface-3",
            )}
          >
            <span className="block text-xs text-muted">{s === "ALL" ? t("cleanup.statusFilter.all") : statusLabels[s]}</span>
            <span className="font-semibold tabular-nums">{num(s === "ALL" ? total : (counts[s] ?? 0))}</span>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={sort} onChange={(e) => update({ sort: e.target.value })} aria-label={t("cleanup.sort.label")}>
          <option value="priority">{t("cleanup.sort.priority")}</option>
          <option value="keep">{t("cleanup.sort.keepAsc")}</option>
          <option value="-keep">{t("cleanup.sort.keepDesc")}</option>
          <option value="-battle">{t("cleanup.sort.battleDesc")}</option>
          <option value="battle">{t("cleanup.sort.battleAsc")}</option>
          <option value="cp">{t("cleanup.sort.cpAsc")}</option>
          <option value="-cp">{t("cleanup.sort.cpDesc")}</option>
          <option value="name">{t("cleanup.sort.name")}</option>
          <option value="iv">{t("cleanup.sort.ivAsc")}</option>
        </Select>
        <Select value={favorite} onChange={(e) => update({ favorite: e.target.value || null })} aria-label={t("cleanup.filters.favoritesLabel")}>
          {TRISTATE.map((o) => (
            <option key={o.value} value={o.value}>
              {t("cleanup.filters.favorites", { choice: t(o.text) })}
            </option>
          ))}
        </Select>
        <Select value={vintage} onChange={(e) => update({ vintage: e.target.value || null })} aria-label={t("cleanup.filters.vintageLabel")}>
          {TRISTATE.map((o) => (
            <option key={o.value} value={o.value}>
              {t("cleanup.filters.vintage", { choice: t(o.text) })}
            </option>
          ))}
        </Select>
        <Select
          value={gym}
          // A best defender is usually kept, so a gym filter looks at every status.
          onChange={(e) => update(e.target.value ? { gym: e.target.value, status: "ALL" } : { gym: null })}
          aria-label={t("cleanup.filters.gymLabel")}
        >
          {GYM_FILTERS.map((o) => (
            <option key={o.value} value={o.value}>
              {t(o.text)}
            </option>
          ))}
        </Select>
        {selected.size > 0 && (
          <Button variant="primary" onClick={() => addToList.mutate({ ids: [...selected] })} loading={addToList.isPending}>
            {t("cleanup.recommendations.addSelected", { n: num(selected.size) })}
          </Button>
        )}
        {SELECTABLE.has(status) && data && data.items.length > 0 && (
          <Button variant="outline" onClick={() => setSelected(new Set(data.items.filter((i) => !i.in_action_list && i.pokemon.vintage_year === null).map((i) => i.pokemon.id)))}>
            {t("cleanup.recommendations.selectPage")}
          </Button>
        )}
      </div>
      {message && <Alert tone="info">{message}</Alert>}
      {query.isLoading ? (
        <Spinner />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title={t("cleanup.recommendations.empty")}>{status !== "ALL" ? statusDescriptions[status] : undefined}</EmptyState>
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
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const query = useQuery({
    queryKey: ["duplicates", accountId],
    queryFn: async () => duplicatesSchema.parse(await api.get("/api/v1/cleanup/duplicates", { account_id: accountId })),
  });
  if (query.isLoading) return <Spinner />;
  const groups = (query.data?.groups ?? []).filter((g) => g.name.toLowerCase().includes(filter.toLowerCase()));
  return (
    <div className="space-y-3">
      <Input placeholder={t("cleanup.duplicates.search")} value={filter} onChange={(e) => setFilter(e.target.value)} className="max-w-xs" />
      <p className="text-xs text-muted">{t("cleanup.duplicates.intro")}</p>
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
                  <th>{t("cleanup.duplicates.columns.ivs")}</th>
                  <th>IV%</th>
                  <th>{t("cleanup.duplicates.columns.level")}</th>
                  <th>{t("cleanup.duplicates.columns.moves")}</th>
                  <th>GL / UL</th>
                  <th title={t("cleanup.duplicates.columns.battleTitle")}>{t("cleanup.duplicates.columns.battle")}</th>
                  <th title={t("cleanup.duplicates.columns.keepTitle")}>{t("cleanup.duplicates.columns.keep")}</th>
                  <th>{t("cleanup.duplicates.columns.advice")}</th>
                  <th>{t("cleanup.duplicates.columns.why")}</th>
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
                        {m.vintage_year !== null && <Badge color="#d97706">{t("cleanup.duplicates.vintage", { year: m.vintage_year })}</Badge>}
                        {m.favorite && <Badge color="#facc15">{t("cleanup.duplicates.favorite")}</Badge>}
                      </div>
                    </td>
                    <td className="max-w-md text-xs text-muted">{serverText("reasons", m.recommendation?.reasons[0])}</td>
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
  const { t } = useTranslation();
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
      <EmptyState title={t("cleanup.list.emptyTitle")}>{t("cleanup.list.emptyText")}</EmptyState>
    );
  }
  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text);
    setCopied(text);
  };
  const heldBack = data.items.filter((item) => item.status === "open" && !item.executable).length;
  const byId = new Map(data.items.map((item) => [item.pokemon.id, item.pokemon]));
  const searchLabel = (p: (typeof data.items)[number]["pokemon"]) => {
    const values = { name: pokemonName(p), nickname: p.nickname, cp: num(p.cp) };
    return t(p.nickname ? "cleanup.list.searchPokemonNickname" : "cleanup.list.searchPokemon", values);
  };
  return (
    <div className="space-y-4">
      <Alert tone="info" title={t("cleanup.list.noTransferTitle")}>
        {t("cleanup.list.noTransferText")}
      </Alert>
      <div className="no-print flex flex-wrap gap-2">
        <Select value={sort} onChange={(e) => setSort(e.target.value as "cp" | "-cp")}>
          <option value="cp">{t("cleanup.sort.cpAsc")}</option>
          <option value="-cp">{t("cleanup.sort.cpDesc")}</option>
        </Select>
        <a href={buildUrl("/api/v1/cleanup/export", { account_id: accountId, sort })}>
          <Button variant="outline" icon={<Download className="h-4 w-4" />}>
            CSV
          </Button>
        </a>
        <a href={buildUrl("/api/v1/cleanup/export", { account_id: accountId, sort, format: "html" })} target="_blank" rel="noreferrer">
          <Button variant="outline" icon={<Printer className="h-4 w-4" />}>
            {t("cleanup.list.printable")}
          </Button>
        </a>
        <Button variant="ghost" onClick={() => change.mutate({ ids: [], mode: "clear" })}>
          {t("cleanup.list.clear")}
        </Button>
      </div>
      {heldBack > 0 && (
        <Alert tone="warning" title={t("cleanup.list.heldBackTitle", { n: num(heldBack) })}>
          {t("cleanup.list.heldBackText")}
        </Alert>
      )}
      <Card title={t("cleanup.list.searches")}>
        <p className="mb-2 text-xs text-muted">{serverText("actionList", data.search_hint.note_text ?? data.search_hint.note)}</p>
        <div className="space-y-2">
          {data.search_hint.queries.map((q) => {
            const search = q.query + data.search_hint.safety_suffix;
            const found = q.pokemon_ids.flatMap((id) => byId.get(id) ?? []);
            return (
              <div key={q.query} className="rounded-lg border border-line px-3 py-2">
                <div className="flex items-center gap-2">
                  <p className="min-w-0 flex-1 text-sm">
                    {found.length ? found.map(searchLabel).join(" · ") : `#${q.species_id}`}
                  </p>
                  <Button size="sm" variant="ghost" icon={<Copy className="h-3.5 w-3.5" />} onClick={() => copy(search)}>
                    {copied === search ? t("cleanup.list.copied") : t("cleanup.list.copy")}
                  </Button>
                </div>
                <code className="mt-1 block truncate rounded bg-surface-3 px-2 py-1 text-xs text-muted" title={search}>
                  {search}
                </code>
              </div>
            );
          })}
        </div>
      </Card>
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-left text-xs text-muted">
            <tr>
              <th className="px-3 py-2">Pokémon</th>
              <th>CP</th>
              <th>IV</th>
              <th>{t("cleanup.list.columns.reason")}</th>
              <th>{t("cleanup.list.columns.protection")}</th>
              <th>{t("cleanup.list.columns.sourceId")}</th>
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
                  {!item.still_in_inventory && <Badge className="ml-2">{t("cleanup.list.gone")}</Badge>}
                  {item.blocked && (
                    <Badge className="ml-2" color="#f87171">
                      {t("cleanup.list.blocked", { reason: serverText("guard", item.blocked_text ?? item.blocked) })}
                    </Badge>
                  )}
                  {item.needs_confirmation && (
                    <Badge className="ml-2" color="#fbbf24">
                      {t("cleanup.list.reconfirm", {
                        reason: item.needs_confirmation.new_reasons.length
                          ? t("cleanup.list.newReasons", { reasons: newReasons(item.needs_confirmation) })
                          : item.needs_confirmation.message_texts.length
                            ? item.needs_confirmation.message_texts.map((m) => serverText("guard", m)).join("; ")
                            : item.needs_confirmation.message,
                      })}
                    </Badge>
                  )}
                </td>
                <td className="tabular-nums">{num(item.pokemon.cp, "?")}</td>
                <td className="font-mono text-xs">{ivs(item.pokemon.iv_attack, item.pokemon.iv_defense, item.pokemon.iv_stamina)}</td>
                <td className="max-w-xs text-xs text-muted">{item.reason_texts.length ? item.reason_texts.map((r) => serverText("reasons", r)).join("; ") : item.reason}</td>
                <td className="text-xs">
                  {item.protection.length ? (
                    <span className="text-amber-300">
                      {item.protection_texts.length ? item.protection_texts.map((r) => serverText("protections", r)).join(", ") : item.protection.join(", ")}
                    </span>
                  ) : (
                    "–"
                  )}
                </td>
                <td className="font-mono text-[10px] text-muted">{item.pokemon.source_pokemon_id}</td>
                <td className="no-print whitespace-nowrap pr-3 text-right">
                  {item.needs_confirmation && (
                    <Button size="sm" variant="ghost" onClick={() => setPending(item.needs_confirmation ? [item.needs_confirmation] : [])}>
                      {t("cleanup.list.confirm")}
                    </Button>
                  )}
                  {item.status === "open" && item.executable && (
                    <Button size="sm" variant="ghost" onClick={() => change.mutate({ ids: [item.pokemon.id], mode: "done" })}>
                      {t("cleanup.list.done")}
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => change.mutate({ ids: [item.pokemon.id], mode: "remove" })}>
                    {t("cleanup.list.remove")}
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

// Translation keys for the label and the optional hint of each rule.
const PROTECTION_RULES: Record<string, [ParseKeys, ParseKeys?]> = {
  protect_shiny: ["cleanup.rules.items.protectShiny.label"],
  protect_lucky: ["cleanup.rules.items.protectLucky.label"],
  protect_hundo: ["cleanup.rules.items.protectHundo.label"],
  protect_location_card: ["cleanup.rules.items.protectLocationCard.label"],
  protect_costume: ["cleanup.rules.items.protectCostume.label"],
  protect_mythical: ["cleanup.rules.items.protectMythical.label"],
  protect_legendary: ["cleanup.rules.items.protectLegendary.label"],
  protect_ultra_beast: ["cleanup.rules.items.protectUltraBeast.label"],
  protect_shadow: ["cleanup.rules.items.protectShadow.label"],
  protect_purified: ["cleanup.rules.items.protectPurified.label"],
  protect_dynamax: ["cleanup.rules.items.protectDynamax.label"],
  protect_gigantamax: ["cleanup.rules.items.protectGigantamax.label"],
  protect_event: ["cleanup.rules.items.protectEvent.label", "cleanup.rules.items.protectEvent.hint"],
  protect_nicknamed: ["cleanup.rules.items.protectNicknamed.label"],
  protect_mega_progress: ["cleanup.rules.items.protectMegaProgress.label"],
};
const ROLE_RULES: Record<string, [ParseKeys, ParseKeys?]> = {
  keep_best_great: ["cleanup.rules.items.keepBestGreat.label"],
  keep_best_ultra: ["cleanup.rules.items.keepBestUltra.label"],
  keep_best_master: ["cleanup.rules.items.keepBestMaster.label"],
  keep_best_raid: ["cleanup.rules.items.keepBestRaid.label", "cleanup.rules.items.keepBestRaid.hint"],
  keep_best_gym: ["cleanup.rules.items.keepBestGym.label", "cleanup.rules.items.keepBestGym.hint"],
  elite_tm_available: ["cleanup.rules.items.eliteTmAvailable.label", "cleanup.rules.items.eliteTmAvailable.hint"],
  include_best_buddy: ["cleanup.rules.items.includeBestBuddy.label"],
  consider_costs: ["cleanup.rules.items.considerCosts.label"],
  allow_transfer_on_partial_import: ["cleanup.rules.items.allowTransferOnPartialImport.label", "cleanup.rules.items.allowTransferOnPartialImport.hint"],
  use_events: ["cleanup.rules.items.useEvents.label", "cleanup.rules.items.useEvents.hint"],
};
const KEEP_RULES: Record<string, [ParseKeys, ParseKeys]> = {
  keep_weight_battle: ["cleanup.rules.items.keepWeightBattle.label", "cleanup.rules.items.keepWeightBattle.hint"],
  keep_points_best_copy: ["cleanup.rules.items.keepPointsBestCopy.label", "cleanup.rules.points"],
  keep_points_favorite: ["cleanup.rules.items.keepPointsFavorite.label", "cleanup.rules.items.keepPointsFavorite.hint"],
  keep_points_shiny: ["cleanup.rules.items.keepPointsShiny.label", "cleanup.rules.points"],
  keep_points_lucky: ["cleanup.rules.items.keepPointsLucky.label", "cleanup.rules.points"],
  keep_points_rarity: ["cleanup.rules.items.keepPointsRarity.label", "cleanup.rules.points"],
  keep_points_costume: ["cleanup.rules.items.keepPointsCostume.label", "cleanup.rules.points"],
  keep_points_location_card: ["cleanup.rules.items.keepPointsLocationCard.label", "cleanup.rules.points"],
  keep_points_event: ["cleanup.rules.items.keepPointsEvent.label", "cleanup.rules.points"],
  keep_points_max: ["cleanup.rules.items.keepPointsMax.label", "cleanup.rules.points"],
  keep_points_xxl: ["cleanup.rules.items.keepPointsXxl.label", "cleanup.rules.items.keepPointsXxl.hint"],
  keep_points_xxs: ["cleanup.rules.items.keepPointsXxs.label", "cleanup.rules.items.keepPointsXxs.hint"],
  keep_points_mega: ["cleanup.rules.items.keepPointsMega.label", "cleanup.rules.points"],
  keep_traits_cap: ["cleanup.rules.items.keepTraitsCap.label", "cleanup.rules.points"],
  keep_points_nickname: ["cleanup.rules.items.keepPointsNickname.label", "cleanup.rules.points"],
  keep_points_planned: ["cleanup.rules.items.keepPointsPlanned.label", "cleanup.rules.items.keepPointsPlanned.hint"],
  keep_threshold: ["cleanup.rules.items.keepThreshold.label", "cleanup.rules.scoreRange"],
  review_threshold: ["cleanup.rules.items.reviewThreshold.label", "cleanup.rules.items.reviewThreshold.hint"],
};
const ANALYSIS_RULES: Record<string, [ParseKeys, ParseKeys]> = {
  keep_min_per_species: ["cleanup.rules.items.keepMinPerSpecies.label", "cleanup.rules.items.keepMinPerSpecies.hint"],
  meta_rank_threshold: ["cleanup.rules.items.metaRankThreshold.label", "cleanup.rules.items.metaRankThreshold.hint"],
  species_rank_full: ["cleanup.rules.items.speciesRankFull.label", "cleanup.rules.items.speciesRankFull.hint"],
  raid_top_n: ["cleanup.rules.items.raidTopN.label", "cleanup.rules.items.raidTopN.hint"],
  gym_top_n: ["cleanup.rules.items.gymTopN.label", "cleanup.rules.items.gymTopN.hint"],
  good_iv_rank_threshold: ["cleanup.rules.items.goodIvRankThreshold.label", "cleanup.rules.of4096"],
  build_iv_rank_threshold: ["cleanup.rules.items.buildIvRankThreshold.label", "cleanup.rules.of4096"],
  ready_cp_fraction: ["cleanup.rules.items.readyCpFraction.label", "cleanup.rules.items.readyCpFraction.hint"],
  max_level: ["cleanup.rules.items.maxLevel.label", "cleanup.rules.items.maxLevel.hint"],
  event_hold_days: ["cleanup.rules.items.eventHoldDays.label", "cleanup.rules.items.eventHoldDays.hint"],
};
const STEPS: Record<string, number> = { ready_cp_fraction: 0.01, max_level: 0.5 };

function NumberRules({ rules, entries, set }: { rules: Rules; entries: Record<string, [ParseKeys, ParseKeys]>; set: (key: string, value: number | null) => void }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      {Object.entries(entries).map(([key, [text, hint]]) => (
        <label key={key} className="grid grid-cols-[minmax(0,1fr)_6rem] items-center gap-3">
          <span>
            <span className="block text-sm">{t(text)}</span>
            <span className="block text-xs text-muted">{t(hint)}</span>
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
  const { t } = useTranslation();
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
      setMessage({ tone: "success", text: t("cleanup.rules.saved") });
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
      <Card title={t("cleanup.rules.fixed.title")}>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {query.data.fixed.map((rule) => (
            <li key={rule.code}>{serverText("rules", rule)}</li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted">{t("cleanup.rules.fixed.text")}</p>
      </Card>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title={t("cleanup.rules.protection.title")}>
          <p className="mb-2 text-xs text-muted">{t("cleanup.rules.protection.text")}</p>
          {Object.entries(PROTECTION_RULES).map(([key, [text, description]]) => (
            <Switch key={key} checked={Boolean(rules[key])} onChange={(v) => set(key, v)} label={t(text)} description={description ? t(description) : undefined} />
          ))}
        </Card>
        <Card title={t("cleanup.rules.keep.title")}>
          <p className="mb-3 text-xs text-muted">{t("cleanup.rules.keep.text")}</p>
          <NumberRules rules={rules} entries={KEEP_RULES} set={set} />
        </Card>
        <Card title={t("cleanup.rules.roles.title")}>
          {Object.entries(ROLE_RULES).map(([key, [text, description]]) => (
            <Switch key={key} checked={Boolean(rules[key])} onChange={(v) => set(key, v)} label={t(text)} description={description ? t(description) : undefined} />
          ))}
        </Card>
        <Card title={t("cleanup.rules.analysis.title")}>
          <NumberRules rules={rules} entries={ANALYSIS_RULES} set={set} />
        </Card>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={!draft} loading={save.isPending} onClick={() => draft && save.mutate(draft)}>
          {t("cleanup.rules.save")}
        </Button>
        <Button variant="outline" onClick={() => setDraft(query.data.defaults)}>
          {t("cleanup.rules.defaults")}
        </Button>
        <span className="text-xs text-muted">{t("cleanup.rules.engine", { version: query.data.engine_version })}</span>
      </div>
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
    </div>
  );
}

function Cleanup({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const [state, update] = useUrlState();
  const tab = (state.tab as Tab) ?? "recommendations";
  return (
    <>
      <PageHeader title={t("cleanup.title")} description={t("cleanup.description")} />
      <Tabs
        value={tab}
        onChange={(value) => update({ tab: value === "recommendations" ? null : value, status: null, sort: null })}
        tabs={[
          { value: "recommendations", label: t("cleanup.tabs.recommendations") },
          { value: "duplicates", label: t("cleanup.tabs.duplicates") },
          { value: "list", label: t("cleanup.tabs.list") },
          { value: "rules", label: t("cleanup.tabs.rules") },
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
