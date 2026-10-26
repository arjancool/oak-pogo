import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable, type VisibilityState } from "@tanstack/react-table";
import clsx from "clsx";
import type { ParseKeys } from "i18next";
import { Download, Filter, HelpCircle, LayoutGrid, Rows3, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
import { z } from "zod";

import { ConfirmTransferDialog } from "../../components/cleanup/ConfirmTransferDialog";
import { RequireAccount } from "../../components/layout/RequireAccount";
import { CleanupBadge, IvPercent, MoveLine, PokemonSprite, StatusBadges, TypeBadge, pokemonName } from "../../components/pokemon";
import { Alert, Badge, Button, Card, Checkbox, Dialog, EmptyState, Input, PageHeader, Pagination, Select, SortHeader, Spinner } from "../../components/ui";
import { api, buildUrl, errorMessage } from "../../lib/api";
import { date, ivs, level, num } from "../../lib/format";
import { statusLabels, typeNames } from "../../lib/i18n";
import { confirmationItem, pokemonPage, type ConfirmationItem, type PokemonSummary } from "../../lib/schemas";
import type { Facets } from "../../lib/types";
import { useUrlState } from "../../lib/useUrlState";

const FLAGS: [string, ParseKeys][] = [
  ["shiny", "box.flags.shiny"],
  ["lucky", "box.flags.lucky"],
  ["shadow", "box.flags.shadow"],
  ["purified", "box.flags.purified"],
  ["favorite", "box.flags.favorite"],
  ["vintage", "box.flags.vintage"],
  ["unknown_date", "box.flags.unknownDate"],
  ["hundo", "box.flags.hundo"],
  ["shundo", "box.flags.shundo"],
  ["legendary", "box.flags.legendary"],
  ["mythical", "box.flags.mythical"],
  ["ultrabeast", "box.flags.ultrabeast"],
  ["costume", "box.flags.costume"],
  ["background", "box.flags.background"],
  ["dynamax", "box.flags.dynamax"],
  ["gigantamax", "box.flags.gigantamax"],
  ["traded", "box.flags.traded"],
  ["new", "box.flags.new"],
  ["protected", "box.flags.protected"],
  ["untagged", "box.flags.untagged"],
  ["duplicate", "box.flags.duplicate"],
  ["nicknamed", "box.flags.nicknamed"],
];
const SORTS: [string, ParseKeys][] = [
  ["-cp", "box.sorts.cpDesc"],
  ["cp", "box.sorts.cpAsc"],
  ["name", "box.sorts.name"],
  ["dex", "box.sorts.dex"],
  ["-iv", "box.sorts.iv"],
  ["-atk", "box.sorts.atk"],
  ["-def", "box.sorts.def"],
  ["-sta", "box.sorts.sta"],
  ["-level", "box.sorts.level"],
  ["-caught", "box.sorts.caughtDesc"],
  ["caught", "box.sorts.caughtAsc"],
  ["great", "box.sorts.great"],
  ["ultra", "box.sorts.ultra"],
  ["-master", "box.sorts.master"],
  ["-cleanup", "box.sorts.cleanup"],
  ["-battle", "box.sorts.battle"],
  ["keep", "box.sorts.keepAsc"],
  ["-keep", "box.sorts.keepDesc"],
  ["-changed", "box.sorts.changed"],
];
interface BulkBody {
  action: string;
  value?: string | null;
  ids?: number[];
  confirmed_ids?: number[];
}
const bulkResult = z.object({
  updated: z.number(),
  skipped: z.array(z.object({ pokemon_id: z.number(), reason: z.string() })),
  needs_confirmation: z.array(confirmationItem),
});

const FILTER_KEYS = [
  ...FLAGS.map(([key]) => key),
  "cp_min", "cp_max", "iv_min", "iv_max", "level_min", "level_max", "species", "years", "cleanup", "league", "move",
  "family", "type", "tag", "status", "planned",
];
const COLUMNS_KEY = "oak.boxColumns";
const DEFAULT_PAGE_SIZE = 50;

function loadColumns(): VisibilityState {
  try {
    return JSON.parse(window.localStorage.getItem(COLUMNS_KEY) ?? "{}") as VisibilityState;
  } catch {
    return {};
  }
}

const column = createColumnHelper<PokemonSummary>();

function TriState({ name, label, value, onChange }: { name: string; label: string; value: string | undefined; onChange: (v: string | null) => void }) {
  const { t } = useTranslation();
  const next = value === "true" ? "false" : value === "false" ? null : "true";
  return (
    <button
      data-flag={name}
      onClick={() => onChange(next)}
      className={clsx(
        "rounded-full border px-3 py-1 text-xs transition",
        value === "true" && "border-oak-500 bg-oak-500/15 text-oak-300",
        value === "false" && "border-red-500/60 bg-red-500/10 text-red-300 line-through",
        !value && "border-line text-muted hover:text-ink",
      )}
      title={t("box.filters.flagHint")}
    >
      {label}
    </button>
  );
}

function FilterPanel({ state, update, facets }: { state: Record<string, string>; update: (c: Record<string, string | null>) => void; facets: Facets | undefined }) {
  const { t } = useTranslation();
  const [speciesInput, setSpeciesInput] = useState("");
  const selectedSpecies = (state.species ?? "").split(",").filter(Boolean);
  const selectedYears = (state.years ?? "").split(",").filter(Boolean);
  const selectedStatuses = (state.cleanup ?? "").split(",").filter(Boolean);
  const toggleList = (key: string, list: string[], value: string) => {
    const next = list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
    update({ [key]: next.join(",") || null });
  };
  const range = (key: string, placeholder: string) => (
    <Input
      type="number"
      inputMode="decimal"
      placeholder={placeholder}
      defaultValue={state[key] ?? ""}
      key={`${key}-${state[key] ?? ""}`}
      onBlur={(event) => update({ [key]: event.target.value || null })}
      className="w-24"
    />
  );
  return (
    <Card className="mb-4">
      <div className="space-y-4">
        <div className="flex flex-wrap gap-1.5">
          {FLAGS.map(([key, text]) => (
            <TriState key={key} name={key} label={t(text)} value={state[key]} onChange={(v) => update({ [key]: v })} />
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div>
            <p className="mb-1 text-xs text-muted">CP</p>
            <div className="flex items-center gap-2">
              {range("cp_min", t("box.filters.min"))} – {range("cp_max", t("box.filters.max"))}
            </div>
          </div>
          <div>
            <p className="mb-1 text-xs text-muted">{t("box.filters.ivPercent")}</p>
            <div className="flex items-center gap-2">
              {range("iv_min", t("box.filters.min"))} – {range("iv_max", t("box.filters.max"))}
            </div>
          </div>
          <div>
            <p className="mb-1 text-xs text-muted">{t("box.filters.level")}</p>
            <div className="flex items-center gap-2">
              {range("level_min", t("box.filters.min"))} – {range("level_max", t("box.filters.max"))}
            </div>
          </div>
          <div>
            <p className="mb-1 text-xs text-muted">{t("box.filters.league")}</p>
            <Select value={state.league ?? ""} onChange={(e) => update({ league: e.target.value || null })} className="w-full">
              <option value="">{t("box.filters.all")}</option>
              <option value="great">Great League</option>
              <option value="ultra">Ultra League</option>
              <option value="master">Master League</option>
            </Select>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-1 text-xs text-muted">{t("box.filters.species")}</p>
            <div className="flex flex-wrap items-center gap-1.5">
              {selectedSpecies.map((id) => {
                const name = facets?.species.find((s) => String(s.species_id) === id)?.name ?? `#${id}`;
                return (
                  <Badge key={id}>
                    {name}
                    <button aria-label={t("box.filters.removeSpecies", { name })} onClick={() => toggleList("species", selectedSpecies, id)}>
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                );
              })}
              <Input
                list="oak-species"
                placeholder={t("box.filters.addSpecies")}
                value={speciesInput}
                className="w-48"
                onChange={(event) => {
                  const value = event.target.value;
                  const match = facets?.species.find((s) => `${s.name} (#${s.species_id})` === value);
                  if (match) {
                    toggleList("species", selectedSpecies, String(match.species_id));
                    setSpeciesInput("");
                  } else setSpeciesInput(value);
                }}
              />
              <datalist id="oak-species">
                {facets?.species.map((s) => (
                  <option key={s.species_id} value={`${s.name} (#${s.species_id})`}>
                    {s.count}×
                  </option>
                ))}
              </datalist>
            </div>
          </div>
          <div>
            <p className="mb-1 text-xs text-muted">{t("box.filters.year")}</p>
            <div className="flex flex-wrap gap-1.5">
              {facets?.years.map((y) => (
                <button
                  key={y.year}
                  onClick={() => toggleList("years", selectedYears, String(y.year))}
                  className={clsx(
                    "rounded-full border px-3 py-1 text-xs",
                    selectedYears.includes(String(y.year)) ? "border-oak-500 bg-oak-500/15 text-oak-300" : "border-line text-muted",
                  )}
                >
                  {y.year} <span className="opacity-60">{y.count}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div>
            <p className="mb-1 text-xs text-muted">{t("box.filters.cleanup")}</p>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(statusLabels).map(([key, text]) => (
                <button
                  key={key}
                  onClick={() => toggleList("cleanup", selectedStatuses, key)}
                  className={clsx(
                    "rounded-full border px-3 py-1 text-xs",
                    selectedStatuses.includes(key) ? "border-oak-500 bg-oak-500/15 text-oak-300" : "border-line text-muted",
                  )}
                >
                  {text}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-1 text-xs text-muted">{t("box.filters.type")}</p>
            <Select value={state.type ?? ""} onChange={(e) => update({ type: e.target.value || null })} className="w-full">
              <option value="">{t("box.filters.allTypes")}</option>
              {facets?.types.map((t) => (
                <option key={t} value={t}>
                  {typeNames[t] ?? t}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <p className="mb-1 text-xs text-muted">{t("box.filters.move")}</p>
            <Input defaultValue={state.move ?? ""} key={`move-${state.move ?? ""}`} placeholder={t("box.filters.movePlaceholder")} onBlur={(e) => update({ move: e.target.value || null })} />
          </div>
          <div>
            <p className="mb-1 text-xs text-muted">{t("box.filters.family")}</p>
            <Select value={state.family ?? ""} onChange={(e) => update({ family: e.target.value || null })} className="w-full">
              <option value="">{t("box.filters.allFamilies")}</option>
              {facets?.families.map((f) => (
                <option key={f} value={f}>
                  {f.replace("FAMILY_", "").replaceAll("_", " ").toLowerCase()}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <div>
          <p className="mb-1 text-xs text-muted">{t("box.filters.inventory")}</p>
          <Select value={state.status ?? ""} onChange={(e) => update({ status: e.target.value || null })}>
            <option value="">{t("box.filters.inInventory")}</option>
            <option value="not_in_inventory">{t("box.filters.notInInventory")}</option>
            <option value="all">{t("box.filters.everything")}</option>
          </Select>
        </div>
      </div>
    </Card>
  );
}

function SyntaxHelp({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  // The examples are search syntax and stay as they are; only the explanations are translated.
  // One example has the word "of" (or) between two terms, so that example has its own key.
  const rows: [string, string][] = [
    ["gyarados", t("box.syntax.name")],
    ["cp>2500  cp<=1500  cp:1000-2000", t("box.syntax.cp")],
    ["iv>=90  atk:0  def:15  sta:15", t("box.syntax.iv")],
    [t("box.syntax.exactExample"), t("box.syntax.exact")],
    ["shiny lucky shadow purified favorite", t("box.syntax.properties")],
    ["legendary mythical ultrabeast dynamax gigantamax", t("box.syntax.classes")],
    ["costume background traded nieuw verdwenen", t("box.syntax.extras")],
    ["2018  year<2019", t("box.syntax.year")],
    ["#130  dex:130", t("box.syntax.dex")],
    ["move:hydro  type:water  family:magikarp", t("box.syntax.moveTypeFamily")],
    ["status:transfer_candidate  beschermd  dubbel", t("box.syntax.status")],
    ["vintage  datumonbekend", t("box.syntax.vintage")],
    ["bruikbaarheid>=60  bewaar<40", t("box.syntax.scores")],
    ["!favorite", t("box.syntax.not")],
  ];
  return (
    <Dialog open={open} onClose={onClose} title={t("box.syntax.title")} wide>
      <p className="mb-3 text-sm text-muted">{t("box.syntax.intro")}</p>
      <table className="w-full text-sm">
        <tbody>
          {rows.map(([example, meaning]) => (
            <tr key={example} className="border-t border-line">
              <td className="py-1.5 pr-4 font-mono text-xs text-oak-300">{example}</td>
              <td className="py-1.5 text-muted">{meaning}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Dialog>
  );
}

function Box({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const [state, update] = useUrlState();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [search, setSearch] = useState(state.q ?? "");
  const [showFilters, setShowFilters] = useState(() => FILTER_KEYS.some((k) => state[k]));
  const [help, setHelp] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [tagDialog, setTagDialog] = useState(false);
  const [tagValue, setTagValue] = useState("");
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [columns, setColumns] = useState<VisibilityState>(loadColumns);
  const view = state.view === "cards" ? "cards" : "table";
  const sort = state.sort ?? "-cp";
  const page = Number(state.page ?? 1);
  const pageSize = Number(state.page_size ?? DEFAULT_PAGE_SIZE);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if ((state.q ?? "") !== search) update({ q: search || null });
    }, 350);
    return () => window.clearTimeout(handle);
  }, [search, state.q, update]);

  useEffect(() => {
    try {
      window.localStorage.setItem(COLUMNS_KEY, JSON.stringify(columns));
    } catch {
      // not essential
    }
  }, [columns]);

  const params = useMemo(() => {
    const result: Record<string, string> = { account_id: String(accountId), sort, page: String(page), page_size: String(pageSize) };
    for (const key of [...FILTER_KEYS, "q"]) if (state[key]) result[key] = state[key] as string;
    return result;
  }, [accountId, state, sort, page, pageSize]);

  const query = useQuery({
    queryKey: ["pokemon", params],
    queryFn: async () => pokemonPage.parse(await api.get("/api/v1/pokemon", params)),
    placeholderData: (previous) => previous,
  });
  const facets = useQuery({
    queryKey: ["facets", accountId],
    queryFn: () => api.get<Facets>("/api/v1/pokemon/facets", { account_id: accountId }),
    staleTime: 60_000,
  });

  const [pending, setPending] = useState<{ body: BulkBody; items: ConfirmationItem[] } | null>(null);
  const bulk = useMutation({
    mutationFn: async (body: BulkBody) =>
      bulkResult.parse(await api.post("/api/v1/pokemon/bulk", { account_id: accountId, ids: body.ids ?? [...selected], ...body })),
    onSuccess: (result, body) => {
      const parts = [t("box.bulk.updated", { count: result.updated })];
      if (result.skipped.length)
        parts.push(t("box.bulk.skipped", { count: result.skipped.length, reasons: [...new Set(result.skipped.map((s) => s.reason))].join("; ") }));
      if (result.needs_confirmation.length) parts.push(t("box.bulk.waiting", { count: result.needs_confirmation.length }));
      parts.push(t("box.bulk.oakOnly"));
      setMessage({ tone: "success", text: parts.join(" ") });
      setPending(result.needs_confirmation.length ? { body, items: result.needs_confirmation } : null);
      void client.invalidateQueries({ queryKey: ["pokemon"] });
    },
    onError: (error) => setMessage({ tone: "error", text: errorMessage(error) }),
  });

  const items = useMemo(() => query.data?.items ?? [], [query.data]);
  const allSelected = items.length > 0 && items.every((p) => selected.has(p.id));
  const toggle = (id: number) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const columnDefs = useMemo(
    () => [
      column.display({
        id: "select",
        header: () => (
          <Checkbox
            checked={allSelected}
            onChange={(checked) =>
              setSelected((current) => {
                const next = new Set(current);
                for (const p of items) {
                  if (checked) next.add(p.id);
                  else next.delete(p.id);
                }
                return next;
              })
            }
          />
        ),
        cell: ({ row }) => <Checkbox checked={selected.has(row.original.id)} onChange={() => toggle(row.original.id)} />,
        enableHiding: false,
      }),
      column.accessor("species_name", {
        id: "name",
        header: () => <SortHeader label="Pokémon" sortKey="name" sort={sort} onSort={(s) => update({ sort: s })} />,
        cell: ({ row }) => (
          <Link to={`/pokemon/${row.original.id}`} className="flex min-w-56 items-center gap-3">
            <PokemonSprite dex={row.original.species_id} shiny={row.original.shiny} types={row.original.types} size={40} />
            <div className="min-w-0">
              <p className="truncate font-medium hover:text-oak-300">
                {pokemonName(row.original)}
                {row.original.nickname && <span className="ml-1 text-xs text-muted">“{row.original.nickname}”</span>}
              </p>
              <StatusBadges pokemon={row.original} compact />
            </div>
          </Link>
        ),
        enableHiding: false,
      }),
      column.accessor("cp", {
        header: () => <SortHeader label="CP" sortKey="cp" sort={sort} onSort={(s) => update({ sort: s })} />,
        cell: (info) => <span className="font-semibold tabular-nums">{num(info.getValue(), "?")}</span>,
      }),
      column.accessor("level", {
        header: () => <SortHeader label={t("box.columns.level")} sortKey="level" sort={sort} onSort={(s) => update({ sort: s })} />,
        cell: (info) => level(info.getValue()),
      }),
      column.display({
        id: "ivs",
        header: t("box.columns.ivs"),
        cell: ({ row }) => <span className="font-mono text-xs">{ivs(row.original.iv_attack, row.original.iv_defense, row.original.iv_stamina)}</span>,
      }),
      column.accessor("iv_percent", {
        header: () => <SortHeader label="IV%" sortKey="iv" sort={sort} onSort={(s) => update({ sort: s })} />,
        cell: (info) => <IvPercent value={info.getValue()} />,
      }),
      column.display({ id: "moves", header: t("box.columns.moves"), cell: ({ row }) => <MoveLine pokemon={row.original} /> }),
      column.display({
        id: "types",
        header: t("box.columns.type"),
        cell: ({ row }) => (
          <div className="flex gap-1">
            {row.original.types.map((t) => (
              <TypeBadge key={t} type={t} />
            ))}
          </div>
        ),
      }),
      column.accessor("caught_at", {
        header: () => <SortHeader label={t("box.columns.caught")} sortKey="caught" sort={sort} onSort={(s) => update({ sort: s })} />,
        cell: (info) => <span className="whitespace-nowrap text-xs">{date(info.getValue())}</span>,
      }),
      column.display({
        id: "great",
        header: () => <SortHeader label={t("box.columns.greatRank")} sortKey="great" sort={sort} onSort={(s) => update({ sort: s === "-great" ? "great" : "-great" })} />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.pvp.great.rank ?? "–"}</span>,
      }),
      column.display({
        id: "ultra",
        header: () => <SortHeader label={t("box.columns.ultraRank")} sortKey="ultra" sort={sort} onSort={(s) => update({ sort: s === "-ultra" ? "ultra" : "-ultra" })} />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.pvp.ultra.rank ?? "–"}</span>,
      }),
      column.display({
        id: "battle",
        header: () => <SortHeader label={t("box.columns.battle")} sortKey="battle" sort={sort} onSort={(s) => update({ sort: s === "-battle" ? "battle" : "-battle" })} />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.cleanup?.battle_score ?? "–"}</span>,
      }),
      column.display({
        id: "keep",
        header: () => <SortHeader label={t("box.columns.keep")} sortKey="keep" sort={sort} onSort={(s) => update({ sort: s === "-keep" ? "keep" : "-keep" })} />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.cleanup?.keep_score ?? "–"}</span>,
      }),
      column.display({
        id: "cleanup",
        header: () => <SortHeader label={t("box.columns.cleanup")} sortKey="cleanup" sort={sort} onSort={(s) => update({ sort: s })} />,
        cell: ({ row }) => <CleanupBadge status={row.original.cleanup?.status} />,
      }),
    ],
    [allSelected, items, selected, sort, t, update],
  );

  const table = useReactTable({
    data: items,
    columns: columnDefs,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    state: { columnVisibility: columns },
    onColumnVisibilityChange: setColumns,
    getRowId: (row) => String(row.id),
  });

  const activeFilters = FILTER_KEYS.filter((k) => state[k]);
  const exportUrl = buildUrl("/api/v1/pokemon/export/csv", { ...params, page: undefined, page_size: undefined });

  return (
    <>
      <PageHeader
        title={t("box.title")}
        description={t("box.description")}
        actions={
          <>
            <a href={exportUrl}>
              <Button variant="outline" icon={<Download className="h-4 w-4" />}>
                CSV
              </Button>
            </a>
            <Button variant={view === "table" ? "primary" : "outline"} onClick={() => update({ view: null }, false)} icon={<Rows3 className="h-4 w-4" />} aria-label={t("box.toolbar.table")} />
            <Button variant={view === "cards" ? "primary" : "outline"} onClick={() => update({ view: "cards" }, false)} icon={<LayoutGrid className="h-4 w-4" />} aria-label={t("box.toolbar.cards")} />
          </>
        }
      />
      <div className="no-print mb-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-64 flex-1">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("box.toolbar.searchPlaceholder")} aria-label={t("box.toolbar.search")} />
        </div>
        <Button variant="ghost" onClick={() => setHelp(true)} icon={<HelpCircle className="h-4 w-4" />}>
          {t("box.toolbar.syntax")}
        </Button>
        <Select value={sort} onChange={(e) => update({ sort: e.target.value })} aria-label={t("box.toolbar.sort")}>
          {SORTS.map(([value, text]) => (
            <option key={value} value={value}>
              {t(text)}
            </option>
          ))}
        </Select>
        <Button variant={showFilters ? "primary" : "outline"} onClick={() => setShowFilters((v) => !v)} icon={<Filter className="h-4 w-4" />}>
          {t("box.toolbar.filters")}{activeFilters.length ? ` (${activeFilters.length})` : ""}
        </Button>
        {(activeFilters.length > 0 || state.q) && (
          <Button
            variant="ghost"
            onClick={() => {
              setSearch("");
              update(Object.fromEntries([...FILTER_KEYS, "q"].map((k) => [k, null])));
            }}
          >
            {t("box.toolbar.clear")}
          </Button>
        )}
        {view === "table" && (
          <details className="relative">
            <summary className="cursor-pointer list-none rounded-lg border border-line px-3 py-2 text-sm text-muted">{t("box.toolbar.columns")}</summary>
            <div className="absolute right-0 z-20 mt-1 w-48 space-y-1 rounded-lg border border-line bg-surface p-3 shadow-lg">
              {table.getAllLeafColumns().filter((c) => c.getCanHide()).map((c) => (
                <Checkbox key={c.id} checked={c.getIsVisible()} onChange={(v) => c.toggleVisibility(v)} label={c.id} />
              ))}
            </div>
          </details>
        )}
      </div>
      {showFilters && <FilterPanel state={state} update={update} facets={facets.data} />}
      {message && (
        <div className="mb-3">
          <Alert tone={message.tone}>{message.text}</Alert>
        </div>
      )}
      {selected.size > 0 && (
        <div className="no-print sticky top-14 z-20 mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-oak-500/40 bg-surface p-3 shadow-lg">
          <span className="text-sm font-medium">{t("box.selection.selected", { count: selected.size })}</span>
          <Button size="sm" onClick={() => bulk.mutate({ action: "protect" })}>{t("box.selection.protect")}</Button>
          <Button size="sm" onClick={() => bulk.mutate({ action: "unprotect" })}>{t("box.selection.unprotect")}</Button>
          <Button size="sm" onClick={() => setTagDialog(true)}>{t("box.selection.addTag")}</Button>
          <Button size="sm" onClick={() => bulk.mutate({ action: "review" })}>{t("box.selection.review")}</Button>
          <Button size="sm" onClick={() => bulk.mutate({ action: "transfer_candidate" })}>{t("box.selection.transferCandidate")}</Button>
          <Button size="sm" onClick={() => bulk.mutate({ action: "add_to_list", value: "cleanup" })}>{t("box.selection.actionList")}</Button>
          <Button size="sm" disabled={selected.size < 2 || selected.size > 6} onClick={() => navigate(`/compare?ids=${[...selected].join(",")}`)}>
            {t("box.selection.compare")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
            {t("box.selection.clear")}
          </Button>
        </div>
      )}
      {query.isLoading ? (
        <Spinner />
      ) : query.error ? (
        <Alert tone="error">{errorMessage(query.error)}</Alert>
      ) : items.length === 0 ? (
        <EmptyState title={t("box.empty.title")}>{t("box.empty.text")}</EmptyState>
      ) : view === "table" ? (
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-left text-xs text-muted">
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers.map((header) => (
                    <th key={header.id} className="whitespace-nowrap px-3 py-2 font-medium">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id} className={clsx("border-t border-line hover:bg-surface-3/40", selected.has(row.original.id) && "bg-oak-500/5")}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2 align-middle">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((p) => (
            <div key={p.id} className={clsx("rounded-xl border bg-surface p-3", selected.has(p.id) ? "border-oak-500" : "border-line")}>
              <div className="flex items-start gap-3">
                <Checkbox checked={selected.has(p.id)} onChange={() => toggle(p.id)} />
                <Link to={`/pokemon/${p.id}`} className="flex min-w-0 flex-1 items-center gap-3">
                  <PokemonSprite dex={p.species_id} shiny={p.shiny} types={p.types} size={52} />
                  <div className="min-w-0">
                    <p className="truncate font-medium">{pokemonName(p)}</p>
                    <p className="text-sm">
                      <span className="font-semibold">CP {num(p.cp, "?")}</span> · L{level(p.level)} · <IvPercent value={p.iv_percent} />
                    </p>
                    <p className="font-mono text-xs text-muted">{ivs(p.iv_attack, p.iv_defense, p.iv_stamina)}</p>
                  </div>
                </Link>
              </div>
              <div className="mt-2 space-y-2">
                <MoveLine pokemon={p} />
                <StatusBadges pokemon={p} compact />
                <div className="flex items-center justify-between text-xs text-muted">
                  <CleanupBadge status={p.cleanup?.status} />
                  <span>GL {p.pvp.great.rank ?? "–"} · UL {p.pvp.ultra.rank ?? "–"}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {query.data && (
        <div className="mt-4">
          <Pagination page={page} pageSize={pageSize} total={query.data.total} onPage={(p) => update({ page: String(p) }, false)} />
        </div>
      )}
      <SyntaxHelp open={help} onClose={() => setHelp(false)} />
      <ConfirmTransferDialog
        key={pending?.items.map((i) => i.pokemon_id).join(",") ?? "none"}
        items={pending?.items ?? []}
        busy={bulk.isPending}
        onCancel={() => setPending(null)}
        onConfirm={(ids) => pending && bulk.mutate({ ...pending.body, ids, confirmed_ids: ids })}
      />
      <Dialog
        open={tagDialog}
        onClose={() => setTagDialog(false)}
        title={t("box.tagDialog.title")}
        footer={
          <Button
            variant="primary"
            disabled={!tagValue.trim()}
            onClick={() => {
              bulk.mutate({ action: "add_tag", value: tagValue.trim() });
              setTagDialog(false);
              setTagValue("");
            }}
          >
            {t("box.tagDialog.add")}
          </Button>
        }
      >
        <Input value={tagValue} onChange={(e) => setTagValue(e.target.value)} placeholder={t("box.tagDialog.placeholder")} maxLength={40} autoFocus />
        <p className="mt-2 text-xs text-muted">{t("box.tagDialog.hint")}</p>
      </Dialog>
    </>
  );
}

export function BoxPage() {
  return <RequireAccount>{(id) => <Box accountId={id} />}</RequireAccount>;
}
