import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { CleanupBadge, IvBars, IvPercent, PokemonSprite, ReadinessBadge, ScoreMeter, StatusBadges, TypeBadge, pokemonName } from "../../components/pokemon";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, KeyValue, Select, Spinner, Switch, Tabs, Textarea } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { date, dateTime, level, num, pct } from "../../lib/format";
import {
  availabilityLabels,
  changeLabels,
  conditionLabels,
  confidenceLabels,
  eventLabels,
  label,
  leagueNames,
  moveActionLabels,
  statusLabels,
} from "../../lib/i18n";
import { pokemonDetail, type PokemonDetail } from "../../lib/schemas";
import type { EvolutionPath, HistoryEvent, PokemonAnalysis, PowerUps, PurifyScenario, Scenario } from "../../lib/types";

const MEASURE_DIGITS = 2;
// Overrides that lift the hard protection of a vintage Pokémon; the API asks for a confirmation.
const VINTAGE_OVERRIDES = new Set(["REVIEW", "TRANSFER_CANDIDATE"]);

function decimal(value: unknown): string {
  return typeof value === "number" ? value.toLocaleString("nl-NL", { maximumFractionDigits: MEASURE_DIGITS }) : "onbekend";
}

/** Display name of a recommended move. The API sends keys and names in the same order. */
function moveName(moveset: { moveset: string[]; names: string[] } | null, key: string): string {
  const index = moveset ? moveset.moveset.indexOf(key) : -1;
  return moveset && index >= 0 ? (moveset.names[index] ?? key) : key.replace(/_FAST$/, "").replaceAll("_", " ").toLowerCase();
}

function RecommendationCard({ pokemon }: { pokemon: PokemonDetail }) {
  const rec = pokemon.recommendation;
  if (!rec) {
    return (
      <Card title="Cleanup-advies">
        <p className="text-sm text-muted">Nog geen analyse beschikbaar. De analyse draait na iedere import automatisch.</p>
      </Card>
    );
  }
  return (
    <Card
      title="Cleanup-advies"
      actions={
        <>
          <CleanupBadge status={rec.status} />
          <Badge title="Betrouwbaarheid">Betrouwbaarheid: {label(confidenceLabels, rec.confidence)}</Badge>
        </>
      }
    >
      <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1">
        <ScoreMeter label="Bruikbaarheid" value={rec.battle_score} title="Feitelijke waarde in gevechten, 0–100" />
        <ScoreMeter label="Bewaarscore" value={rec.keep_score} title="Reden om te bewaren, 0–100" />
      </div>
      {rec.protection_reasons.length > 0 && (
        <p className="mb-2 text-sm text-sky-300">Bescherming: {rec.protection_reasons.map((r) => r.text).join(" · ")}</p>
      )}
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {rec.reasons.map((reason, index) => (
          <li key={index}>{reason.text}</li>
        ))}
      </ul>
      <details className="mt-3 text-xs">
        <summary className="cursor-pointer text-muted">Hoe zijn de scores opgebouwd?</summary>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <ul className="space-y-0.5">
            {rec.scores.battle?.parts.map((part, index) => (
              <li key={index} className={clsx("flex justify-between gap-3", part.code === rec.scores.battle?.basis && "font-semibold")}>
                <span>{part.text}</span>
                <span className="tabular-nums">{Math.round(part.value)}</span>
              </li>
            ))}
          </ul>
          <ul className="space-y-0.5">
            {rec.scores.keep?.parts.map((part, index) => (
              <li key={index} className="flex justify-between gap-3">
                <span>{part.text}</span>
                <span className="tabular-nums">+{Math.round(part.value)}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="mt-1 text-muted">Bruikbaarheid is de hoogste deelwaarde. De bewaarscore telt punten op tot maximaal 100.</p>
      </details>
      {rec.warnings.length > 0 && (
        <div className="mt-3">
          <Alert tone="warning">{rec.warnings.map((w) => w.text).join(" · ")}</Alert>
        </div>
      )}
      {rec.alternatives.length > 0 && (
        <div className="mt-3 text-sm">
          <p className="mb-1 text-xs text-muted">Vergelijkbare Pokémon in je collectie</p>
          <div className="flex flex-wrap gap-2">
            {rec.alternatives.map((alt) => (
              <Link key={alt.pokemon_id} to={`/pokemon/${alt.pokemon_id}`} className="rounded-lg border border-line px-2 py-1 text-xs hover:bg-surface-3">
                {alt.name} · CP {num(alt.cp, "?")} · {pct(alt.iv_percent)} · bruikbaarheid {alt.battle_score ?? "?"} · {label(statusLabels, alt.status)}
                {alt.better && <span className="ml-1 text-emerald-300">beter</span>}
              </Link>
            ))}
          </div>
        </div>
      )}
      <p className="mt-3 text-xs text-muted">Berekend op {dateTime(rec.computed_at)}. OAK zet nooit zelf een Pokémon over.</p>
    </Card>
  );
}

function MetadataCard({ pokemon }: { pokemon: PokemonDetail }) {
  const client = useQueryClient();
  const meta = pokemon.metadata;
  const [form, setForm] = useState({
    protected: meta?.protected ?? false,
    protection_reason: meta?.protection_reason ?? "",
    notes: meta?.notes ?? "",
    tags: (meta?.tags ?? []).join(", "),
    planned_action: meta?.planned_action ?? "",
    planned_league: meta?.planned_league ?? "",
    review_status: meta?.review_status ?? "none",
    override_status: meta?.override_status ?? "",
  });
  const [saved, setSaved] = useState<string | null>(null);
  const liftsVintage = pokemon.vintage_year !== null && VINTAGE_OVERRIDES.has(form.override_status) && form.override_status !== (meta?.override_status ?? "");
  const save = useMutation({
    mutationFn: (confirmVintage: boolean) =>
      api.patch(`/api/v1/pokemon/${pokemon.id}/metadata`, {
        confirm_vintage_override: confirmVintage,
        protected: form.protected,
        protection_reason: form.protection_reason || null,
        notes: form.notes,
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
        planned_action: form.planned_action || null,
        planned_league: form.planned_league || null,
        review_status: form.review_status,
        override_status: form.override_status || null,
        clear: [
          ...(form.planned_action ? [] : ["planned_action"]),
          ...(form.planned_league ? [] : ["planned_league"]),
          ...(form.override_status ? [] : ["override_status"]),
          ...(form.protection_reason ? [] : ["protection_reason"]),
        ],
      }),
    onSuccess: () => {
      setSaved("Opgeslagen. De analyse wordt opnieuw berekend.");
      void client.invalidateQueries({ queryKey: ["pokemon-detail", pokemon.id] });
      void client.invalidateQueries({ queryKey: ["pokemon"] });
    },
    onError: (error) => setSaved(errorMessage(error)),
  });
  return (
    <Card title="Jouw gegevens (OAK)">
      <div className="space-y-3">
        <Switch
          checked={form.protected}
          onChange={(v) => setForm({ ...form, protected: v })}
          label="Handmatig beschermen"
          description="Een beschermde Pokémon wordt nooit als transfer-kandidaat voorgesteld."
        />
        {form.protected && (
          <Field label="Reden">
            <Input value={form.protection_reason} onChange={(e) => setForm({ ...form, protection_reason: e.target.value })} maxLength={200} />
          </Field>
        )}
        <Field label="Notities">
          <Textarea rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </Field>
        <Field label="OAK-tags" hint="komma-gescheiden">
          <Input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Geplande actie">
            <Select className="w-full" value={form.planned_action} onChange={(e) => setForm({ ...form, planned_action: e.target.value })}>
              <option value="">Geen</option>
              <option value="keep">Bewaren</option>
              <option value="evolve">Evolueren</option>
              <option value="power_up">Power-up</option>
              <option value="tm">TM gebruiken</option>
              <option value="purify">Purifyen</option>
              <option value="trade">Ruilen</option>
              <option value="mega">Mega</option>
              <option value="buddy">Buddy</option>
              <option value="transfer">Overzetten</option>
            </Select>
          </Field>
          <Field label="Geplande league">
            <Select className="w-full" value={form.planned_league} onChange={(e) => setForm({ ...form, planned_league: e.target.value })}>
              <option value="">Geen</option>
              <option value="great">Great League</option>
              <option value="ultra">Ultra League</option>
              <option value="master">Master League</option>
            </Select>
          </Field>
          <Field label="Review">
            <Select className="w-full" value={form.review_status} onChange={(e) => setForm({ ...form, review_status: e.target.value })}>
              <option value="none">Geen</option>
              <option value="to_review">Te beoordelen</option>
              <option value="reviewed">Beoordeeld</option>
            </Select>
          </Field>
          <Field label="Advies overschrijven">
            <Select className="w-full" value={form.override_status} onChange={(e) => setForm({ ...form, override_status: e.target.value })}>
              <option value="">Advies van OAK volgen</option>
              {Object.entries(statusLabels)
                .filter(([key]) => key !== "UNKNOWN")
                .map(([key, text]) => (
                  <option key={key} value={key}>
                    {text}
                  </option>
                ))}
            </Select>
          </Field>
        </div>
        {liftsVintage && (
          <Alert tone="warning" title={`Vintage ${pokemon.vintage_year}`}>
            OAK beschermt Pokémon uit 2016 tot en met 2019 altijd. Met deze keuze hef je die bescherming op voor deze ene Pokémon.
          </Alert>
        )}
        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            loading={save.isPending}
            onClick={() => {
              if (!liftsVintage) save.mutate(false);
              else if (window.confirm(`Dit is een vintage Pokémon uit ${pokemon.vintage_year}. Weet je zeker dat je de bescherming wilt opheffen?`))
                save.mutate(true);
            }}
          >
            Opslaan
          </Button>
          {saved && <span className="text-xs text-muted">{saved}</span>}
        </div>
      </div>
    </Card>
  );
}

const scenarioParams = (scenario: Scenario) => (scenario === "purified" ? { scenario } : undefined);

/** Lets the battle analysis, evolutions and power-ups describe a Shadow Pokémon after purification. */
function ScenarioCard({ value, onChange }: { value: Scenario; onChange: (value: Scenario) => void }) {
  return (
    <Card title="Rekenen met">
      <Tabs
        value={value}
        onChange={onChange}
        tabs={[
          { value: "current", label: "Als Shadow" },
          { value: "purified", label: "Na purify" },
        ]}
      />
      <p className="mt-3 text-xs text-muted">
        Purify zet een Shadow Pokémon op level 25, of op je trainerlevel als dat lager is, en geeft iedere IV 2 punten extra tot 15. Dat is
        niet terug te draaien, en een level kun je niet verlagen. Een Pokémon kan daardoor te sterk worden voor Great League.
      </p>
    </Card>
  );
}

function PurifySummary({ scenario }: { scenario: PurifyScenario }) {
  return (
    <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3 text-sm">
      <p>
        Na purify: level {level(scenario.level)}, IV {scenario.ivs.attack}/{scenario.ivs.defense}/{scenario.ivs.stamina}, CP {num(scenario.cp, "onbekend")}.
        Purify kost {num(scenario.cost.stardust, "onbekend")} stardust en {num(scenario.cost.candy, "onbekend")} candy.
      </p>
      {scenario.assumption && <p className="mt-1 text-xs text-amber-300">{scenario.assumption}</p>}
      {scenario.source && <p className="mt-1 text-xs text-muted">Regels voor level en IV's: {scenario.source}.</p>}
    </div>
  );
}

function AnalysisCard({ pokemonId, scenario }: { pokemonId: number; scenario: Scenario }) {
  const [league, setLeague] = useState<"great" | "ultra" | "master">("great");
  const analysis = useQuery({
    queryKey: ["pokemon-analysis", pokemonId, scenario],
    queryFn: () => api.get<PokemonAnalysis>(`/api/v1/pokemon/${pokemonId}/analysis`, scenarioParams(scenario)),
  });
  if (analysis.isLoading) return <Card title="Battle-analyse"><Spinner /></Card>;
  const data = analysis.data;
  if (!data?.available || !data.leagues) {
    return (
      <Card title="Battle-analyse">
        <p className="text-sm text-muted">{analysis.error ? errorMessage(analysis.error) : (data?.reason ?? "Niet beschikbaar.")}</p>
      </Card>
    );
  }
  const current = data.leagues[league];
  return (
    <Card title="Battle-analyse" actions={<span className="text-xs text-muted">Game Data v{data.game_data_version}</span>}>
      <Tabs
        value={league}
        onChange={setLeague}
        tabs={(["great", "ultra", "master"] as const).map((l) => ({ value: l, label: leagueNames[l] }))}
      />
      {data.scenario && <PurifySummary scenario={data.scenario} />}
      <div className="mt-3 grid gap-2 text-xs text-muted md:grid-cols-3">
        <p><b className="text-ink">IV-rang</b>: {data.method?.iv_rank}</p>
        <p><b className="text-ink">Soortrang</b>: {data.method?.species_rank}</p>
        <p><b className="text-ink">Inzetbaarheid</b>: {data.method?.readiness}</p>
      </div>
      {!current || current.targets.length === 0 ? (
        <p className="mt-4 text-sm text-muted">Geen geschikte vorm voor deze league.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-2 pr-3">Doel</th>
                <th className="pr-3">IV-rang</th>
                <th className="pr-3">% van beste</th>
                <th className="pr-3">Beste CP / level</th>
                <th className="pr-3">Inzetbaarheid</th>
                <th className="pr-3">Kosten</th>
                <th className="pr-3">Soortrang</th>
              </tr>
            </thead>
            <tbody>
              {current.targets.map((t) => (
                <tr key={t.target_key} className="border-t border-line align-top">
                  <td className="py-2 pr-3">
                    <p className="font-medium">
                      {t.target_name}
                      {t.target_key === current.primary_target && <Badge className="ml-2">primair</Badge>}
                    </p>
                    {t.is_evolution && (
                      <p className="text-xs text-muted">
                        na evolutie · {num(t.evolution_candy, "?")} candy{t.evolution_item ? ` + ${t.evolution_item.replace("ITEM_", "").toLowerCase()}` : ""}
                      </p>
                    )}
                    {t.moveset && (
                      <div className="mt-1 text-xs">
                        <span className="text-muted">Aanbevolen: </span>
                        {t.moveset.names.join(" · ")}
                        {t.moveset.source === "pvpoke_usage_filtered" && <span className="text-amber-300"> (zonder Elite TM)</span>}
                        <ul className="mt-1 space-y-0.5">
                          {t.moveset.needs
                            .filter((n) => n.action !== "none")
                            .map((n, i) => (
                              <li key={i} className={n.action === "impossible" ? "text-red-300" : "text-muted"}>
                                {label(moveActionLabels, n.action)}
                                {n.target ? ` → ${moveName(t.moveset, n.target)}` : ""}
                                {n.pool_size && n.action.endsWith("_tm") && !n.action.startsWith("elite") ? ` (willekeurig uit ${n.pool_size})` : ""}
                              </li>
                            ))}
                        </ul>
                      </div>
                    )}
                  </td>
                  <td className="pr-3 tabular-nums">{t.rank}</td>
                  <td className="pr-3 tabular-nums">{pct(t.percent, 2)}</td>
                  <td className="pr-3 tabular-nums">
                    {num(t.best_cp)} / L{level(t.best_level)}
                    <p className="text-xs text-muted">nu {num(t.cp_now, "?")}</p>
                  </td>
                  <td className="pr-3">
                    <ReadinessBadge readiness={t.readiness} />
                    <p className="mt-0.5 text-xs text-muted">{t.readiness_reason}</p>
                  </td>
                  <td className="pr-3 text-xs tabular-nums">
                    {t.cost ? (
                      <>
                        {num(t.cost.stardust)} stardust
                        <br />
                        {num(t.cost.candy)} candy{t.cost.xl_candy ? `, ${num(t.cost.xl_candy)} XL` : ""}
                      </>
                    ) : (
                      "–"
                    )}
                  </td>
                  <td className="pr-3 tabular-nums">
                    {t.species_rank ?? "–"}
                    {t.species_score !== null && <p className="text-xs text-muted">score {t.species_score}</p>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.current_moves && data.current_moves.length > 0 && (
        <div className="mt-4 text-sm">
          <p className="mb-1 text-xs text-muted">Huidige aanvallen</p>
          <div className="flex flex-wrap gap-2">
            {data.current_moves.map((m) => (
              <Badge key={m.key}>
                {m.name} · {label(availabilityLabels, m.availability)}
              </Badge>
            ))}
          </div>
        </div>
      )}
      <p className="mt-3 text-xs text-muted">
        Max level {data.rules?.max_level}
        {data.rules?.include_best_buddy ? " + Best Buddy" : ""} · Elite TM {data.rules?.elite_tm_available ? "beschikbaar" : "niet beschikbaar"} ·
        Een Pokémon met uitstekende IV's is niet automatisch een goede battle-Pokémon: kijk ook naar de soortrang en inzetbaarheid.
      </p>
    </Card>
  );
}

function EvolutionsCard({ pokemonId, scenario }: { pokemonId: number; scenario: Scenario }) {
  const query = useQuery({
    queryKey: ["pokemon-evolutions", pokemonId, scenario],
    queryFn: () =>
      api.get<{ available: boolean; paths: EvolutionPath[]; reason?: string }>(`/api/v1/pokemon/${pokemonId}/evolutions`, scenarioParams(scenario)),
  });
  if (query.isLoading) return null;
  const paths = query.data?.paths ?? [];
  return (
    <Card title={scenario === "purified" ? "Evoluties na purify" : "Evoluties"}>
      {paths.length === 0 ? (
        <p className="text-sm text-muted">{query.error ? errorMessage(query.error) : (query.data?.reason ?? "Geen verdere evoluties.")}</p>
      ) : (
        <ul className="space-y-3">
          {paths.map((path) => (
            <li key={path.target_key} className="rounded-lg border border-line p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">{path.target_name}</p>
                <span className="tabular-nums">CP na evolutie: {num(path.cp_after, "onbekend")}</span>
              </div>
              <p className="mt-1 text-xs text-muted">
                {num(path.total_candy, "?")} candy
                {path.steps.map((s) =>
                  [s.item && ` · ${s.item.replace("ITEM_", "").toLowerCase()}`, s.lure && ` · ${s.lure.replace("ITEM_", "").toLowerCase()}`, s.buddy_km && ` · ${s.buddy_km} km als buddy`, s.quest && " · evolutie-opdracht", ...s.conditions.map((c) => ` · ${label(conditionLabels, c)}`)].filter(Boolean).join(""),
                )}
              </p>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                {Object.entries(path.leagues).map(([lg, info]) => (
                  <Badge key={lg} color={info.over_cap ? "#f87171" : undefined}>
                    {leagueNames[lg]}: {info.over_cap ? "boven CP-limiet" : `rang ${info.rank ?? "–"}`}
                  </Badge>
                ))}
              </div>
              {path.elite_moves.length > 0 && <p className="mt-1 text-xs text-amber-300">Let op: sommige aanvallen van deze evolutie zijn alleen met Elite TM te leren.</p>}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-muted">Een hogere CP alleen is nooit een reden om te evolueren. Vergelijk de league-rangen.</p>
    </Card>
  );
}

function PowerUpCard({ pokemonId, scenario }: { pokemonId: number; scenario: Scenario }) {
  const query = useQuery({
    queryKey: ["pokemon-powerups", pokemonId, scenario],
    queryFn: () => api.get<PowerUps>(`/api/v1/pokemon/${pokemonId}/powerups`, scenarioParams(scenario)),
  });
  const [showAll, setShowAll] = useState(false);
  const data = query.data;
  if (!data?.available || !data.steps) return null;
  const steps = showAll ? data.steps : data.steps.filter((_, i) => i < 6 || i % 4 === 3);
  return (
    <Card title={data.scenario ? "Power-ups na purify" : "Power-ups"} actions={<span className="text-xs text-muted">Max level {level(data.max_level)}</span>}>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted">
          <tr>
            <th className="py-1">Level</th>
            <th>CP</th>
            <th>Stardust</th>
            <th>Candy</th>
            <th>XL Candy</th>
          </tr>
        </thead>
        <tbody>
          {steps.map((s) => (
            <tr key={s.level} className="border-t border-line tabular-nums">
              <td className="py-1">{level(s.level)}</td>
              <td>{num(s.cp, "?")}</td>
              <td>{num(s.cost?.stardust ?? null, "?")}</td>
              <td>{num(s.cost?.candy ?? null, "?")}</td>
              <td>{num(s.cost?.xl_candy ?? null, "?")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button size="sm" variant="ghost" className="mt-2" onClick={() => setShowAll((v) => !v)}>
        {showAll ? "Minder tonen" : "Alle levels tonen"}
      </Button>
      <p className="mt-2 text-xs text-muted">
        Kosten zijn cumulatief vanaf {data.scenario ? "het level na purify" : "het huidige level"}{data.modifiers?.lucky ? ", met Lucky-korting" : ""}
        {data.modifiers?.shadow ? ", Shadow-toeslag" : ""}
        {data.modifiers?.purified ? ", Purified-korting" : ""}. Je candyvoorraad is onbekend: PGSharp exporteert die niet. {data.note}
      </p>
    </Card>
  );
}

function HistoryCard({ pokemonId }: { pokemonId: number }) {
  const query = useQuery({ queryKey: ["pokemon-history", pokemonId], queryFn: () => api.get<HistoryEvent[]>(`/api/v1/pokemon/${pokemonId}/history`) });
  const events = query.data ?? [];
  return (
    <Card title="Historie">
      {events.length === 0 ? (
        <p className="text-sm text-muted">Geen wijzigingen.</p>
      ) : (
        <ol className="space-y-2 text-sm">
          {events.map((e) => (
            <li key={e.id} className="border-l-2 border-line pl-3">
              <p className="font-medium">
                {label(eventLabels, e.type)} <span className="text-xs font-normal text-muted">{dateTime(e.at)}</span>
              </p>
              {e.labels.length > 0 && <p className="text-xs text-muted">{e.labels.map((l) => label(changeLabels, l)).join(", ")}</p>}
              {Object.entries(e.changes).slice(0, 6).map(([field, change]) => (
                <p key={field} className="font-mono text-xs text-muted">
                  {field}: {JSON.stringify(change[0])} → {JSON.stringify(change[1])}
                </p>
              ))}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

export function DetailPage() {
  const { id } = useParams();
  const pokemonId = Number(id);
  const [copied, setCopied] = useState(false);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const query = useQuery({
    queryKey: ["pokemon-detail", pokemonId],
    queryFn: async () => pokemonDetail.parse(await api.get(`/api/v1/pokemon/${pokemonId}`)),
    enabled: Number.isFinite(pokemonId),
  });
  useEffect(() => {
    setCopied(false);
    setScenario(null);
  }, [pokemonId]);
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <EmptyState title="Pokémon niet gevonden">{query.error ? errorMessage(query.error) : null}</EmptyState>;
  const p = query.data;
  const details = p.details as Record<string, unknown>;
  // A Shadow Pokémon you plan to purify is shown as purified, until you choose otherwise.
  const chosen: Scenario = p.shadow ? (scenario ?? (p.metadata?.planned_action === "purify" ? "purified" : "current")) : "current";
  return (
    <>
      <Link to="/pokemon" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Pokémon Box
      </Link>
      <div className="mb-5 flex flex-wrap items-start gap-5 rounded-2xl border border-line bg-surface p-5">
        <PokemonSprite dex={p.species_id} shiny={p.shiny} types={p.types} size={112} />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold">{pokemonName(p)}</h1>
            {p.nickname && <span className="text-muted">“{p.nickname}”</span>}
            <CleanupBadge status={p.cleanup?.status} />
          </div>
          <div className="flex flex-wrap gap-1">
            {p.types.map((t) => (
              <TypeBadge key={t} type={t} />
            ))}
          </div>
          <StatusBadges pokemon={p} />
          <p className="text-sm text-muted">
            #{p.species_id} · {p.hatched_from_egg ? "uitgebroed" : "gevangen"} {date(p.caught_at)} · {p.inventory_status === "in_inventory" ? "in inventaris" : "niet meer in inventaris"}
          </p>
          <button
            className="inline-flex items-center gap-1 font-mono text-xs text-muted hover:text-ink"
            onClick={() => {
              void navigator.clipboard?.writeText(p.source_pokemon_id);
              setCopied(true);
            }}
            title="Unieke Pokémon-ID uit PGSharp"
          >
            ID {p.source_pokemon_id} <Copy className="h-3 w-3" /> {copied && "gekopieerd"}
          </button>
          {p.form_resolution === "fallback_default_form" && (
            <Alert tone="warning">Deze vorm ({p.form_name}) staat niet in de Game Data. OAK gebruikt de standaardvorm van de soort.</Alert>
          )}
        </div>
        <div className="grid w-full grid-cols-3 gap-3 sm:w-auto sm:grid-cols-1">
          <div className="text-right">
            <p className="text-xs text-muted">CP</p>
            <p className="text-3xl font-semibold tabular-nums">{num(p.cp, "?")}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted">HP · level</p>
            <p className="tabular-nums">
              {num(p.max_hp, "?")} · L{level(p.level)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted">IV</p>
            <IvPercent value={p.iv_percent} />
          </div>
        </div>
      </div>
      <div className="grid gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <RecommendationCard pokemon={p} />
          {p.shadow && <ScenarioCard value={chosen} onChange={setScenario} />}
          <AnalysisCard pokemonId={p.id} scenario={chosen} />
          <EvolutionsCard pokemonId={p.id} scenario={chosen} />
          <PowerUpCard pokemonId={p.id} scenario={chosen} />
        </div>
        <div className="space-y-5">
          <Card title="Waarden">
            <IvBars attack={p.iv_attack} defense={p.iv_defense} stamina={p.iv_stamina} />
            <div className="mt-4">
              <KeyValue
                items={[
                  ["Snelle aanval", p.fast_move?.name ?? "?"],
                  ["Geladen aanvallen", p.charged_moves.map((m) => m.name).join(" / ") || "?"],
                  ["Tweede aanval vrijgespeeld", p.second_move_unlocked === null ? "onbekend" : p.second_move_unlocked ? "ja" : "nee"],
                  ["Max Moves", p.max_moves.length ? p.max_moves.map((m) => `${m.type.replace("max_", "Max ")} ${m.level}`).join(", ") : "–"],
                  ["Lengte / gewicht", `${decimal(details.height_m)} m / ${decimal(details.weight_kg)} kg`],
                  ["Power-ups gedaan", num(details.num_upgrades as number | null)],
                  ["Buddy-km", num(details.buddy_km_walked as number | null)],
                  ["Uit ei", p.hatched_from_egg === null ? "onbekend" : p.hatched_from_egg ? "ja" : "nee"],
                  ["Eerst gezien in OAK", dateTime(p.first_seen_at)],
                  ["Laatst gewijzigd", dateTime(p.last_changed_at)],
                ]}
              />
            </div>
            {Array.isArray(details.origin_events) && details.origin_events.length > 0 && (
              <p className="mt-3 text-xs text-muted">Event: {(details.origin_events as string[]).join(", ")}</p>
            )}
            {p.tag_ids.length > 0 && (
              <p className="mt-2 text-xs text-muted">
                Tags in het spel: {p.tag_labels.length ? p.tag_labels.join(", ") : `${p.tag_ids.length} (namen onbekend, geef ze een label in Instellingen)`}
              </p>
            )}
          </Card>
          <MetadataCard key={p.id} pokemon={p} />
          <HistoryCard pokemonId={p.id} />
        </div>
      </div>
    </>
  );
}
