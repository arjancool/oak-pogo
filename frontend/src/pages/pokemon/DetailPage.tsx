import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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
import { type ServerText, serverText } from "../../lib/serverText";
import type { EvolutionPath, HistoryEvent, PokemonAnalysis, PowerUps, PurifyScenario, Scenario } from "../../lib/types";
import { useLeagues } from "../battles/shared";

const MEASURE_DIGITS = 2;
// Overrides that lift the hard protection of a vintage Pokémon; the API asks for a confirmation.
const VINTAGE_OVERRIDES = new Set(["REVIEW", "TRANSFER_CANDIDATE"]);

function decimal(value: unknown): string {
  return num(typeof value === "number" ? Math.round(value * 10 ** MEASURE_DIGITS) / 10 ** MEASURE_DIGITS : null);
}

/** Display name of a recommended move. The API sends keys and names in the same order. */
function moveName(moveset: { moveset: string[]; names: string[] } | null, key: string): string {
  const index = moveset ? moveset.moveset.indexOf(key) : -1;
  return moveset && index >= 0 ? (moveset.names[index] ?? key) : key.replace(/_FAST$/, "").replaceAll("_", " ").toLowerCase();
}

function RecommendationCard({ pokemon }: { pokemon: PokemonDetail }) {
  const { t } = useTranslation();
  const rec = pokemon.recommendation;
  if (!rec) {
    return (
      <Card title={t("detail.recommendation.title")}>
        <p className="text-sm text-muted">{t("detail.recommendation.none")}</p>
      </Card>
    );
  }
  return (
    <Card
      title={t("detail.recommendation.title")}
      actions={
        <>
          <CleanupBadge status={rec.status} />
          <Badge title={t("detail.recommendation.confidenceTitle")}>
            {t("detail.recommendation.confidence", { level: label(confidenceLabels, rec.confidence) })}
          </Badge>
        </>
      }
    >
      <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1">
        <ScoreMeter label={t("detail.recommendation.usefulness")} value={rec.battle_score} title={t("detail.recommendation.usefulnessTitle")} />
        <ScoreMeter label={t("detail.recommendation.keepScore")} value={rec.keep_score} title={t("detail.recommendation.keepScoreTitle")} />
      </div>
      {rec.protection_reasons.length > 0 && (
        <p className="mb-2 text-sm text-sky-300">{t("detail.recommendation.protection", { reasons: rec.protection_reasons.map((r) => serverText("protections", r)).join(" · ") })}</p>
      )}
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {rec.reasons.map((reason, index) => (
          <li key={index}>{serverText("reasons", reason)}</li>
        ))}
      </ul>
      <details className="mt-3 text-xs">
        <summary className="cursor-pointer text-muted">{t("detail.recommendation.scoresHow")}</summary>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <ul className="space-y-0.5">
            {rec.scores.battle?.parts.map((part, index) => (
              <li key={index} className={clsx("flex justify-between gap-3", part.code === rec.scores.battle?.basis && "font-semibold")}>
                <span>{serverText("parts", part)}</span>
                <span className="tabular-nums">{Math.round(part.value)}</span>
              </li>
            ))}
          </ul>
          <ul className="space-y-0.5">
            {rec.scores.keep?.parts.map((part, index) => (
              <li key={index} className="flex justify-between gap-3">
                <span>{serverText("parts", part)}</span>
                <span className="tabular-nums">+{Math.round(part.value)}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="mt-1 text-muted">{t("detail.recommendation.scoresNote")}</p>
      </details>
      {rec.warnings.length > 0 && (
        <div className="mt-3">
          <Alert tone="warning">{rec.warnings.map((w) => serverText("warnings", w)).join(" · ")}</Alert>
        </div>
      )}
      {rec.alternatives.length > 0 && (
        <div className="mt-3 text-sm">
          <p className="mb-1 text-xs text-muted">{t("detail.recommendation.alternatives")}</p>
          <div className="flex flex-wrap gap-2">
            {rec.alternatives.map((alt) => (
              <Link key={alt.pokemon_id} to={`/pokemon/${alt.pokemon_id}`} className="rounded-lg border border-line px-2 py-1 text-xs hover:bg-surface-3">
                {t("detail.recommendation.alternative", {
                  name: alt.name,
                  cp: num(alt.cp, "?"),
                  iv: pct(alt.iv_percent),
                  score: alt.battle_score ?? "?",
                  status: label(statusLabels, alt.status),
                })}
                {alt.better && <span className="ml-1 text-emerald-300">{t("detail.recommendation.better")}</span>}
              </Link>
            ))}
          </div>
        </div>
      )}
      <p className="mt-3 text-xs text-muted">{t("detail.recommendation.computed", { date: dateTime(rec.computed_at) })}</p>
    </Card>
  );
}

function MetadataCard({ pokemon }: { pokemon: PokemonDetail }) {
  const { t } = useTranslation();
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
        tags: form.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
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
      setSaved(t("detail.metadata.saved"));
      void client.invalidateQueries({ queryKey: ["pokemon-detail", pokemon.id] });
      void client.invalidateQueries({ queryKey: ["pokemon"] });
    },
    onError: (error) => setSaved(errorMessage(error)),
  });
  return (
    <Card title={t("detail.metadata.title")}>
      <div className="space-y-3">
        <Switch
          checked={form.protected}
          onChange={(v) => setForm({ ...form, protected: v })}
          label={t("detail.metadata.protect")}
          description={t("detail.metadata.protectHint")}
        />
        {form.protected && (
          <Field label={t("detail.metadata.reason")}>
            <Input value={form.protection_reason} onChange={(e) => setForm({ ...form, protection_reason: e.target.value })} maxLength={200} />
          </Field>
        )}
        <Field label={t("detail.metadata.notes")}>
          <Textarea rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </Field>
        <Field label={t("detail.metadata.tags")} hint={t("detail.metadata.tagsHint")}>
          <Input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("detail.metadata.plannedAction")}>
            <Select className="w-full" value={form.planned_action} onChange={(e) => setForm({ ...form, planned_action: e.target.value })}>
              <option value="">{t("detail.metadata.none")}</option>
              <option value="keep">{t("detail.metadata.actions.keep")}</option>
              <option value="evolve">{t("detail.metadata.actions.evolve")}</option>
              <option value="power_up">{t("detail.metadata.actions.powerUp")}</option>
              <option value="tm">{t("detail.metadata.actions.tm")}</option>
              <option value="purify">{t("detail.metadata.actions.purify")}</option>
              <option value="trade">{t("detail.metadata.actions.trade")}</option>
              <option value="mega">{t("detail.metadata.actions.mega")}</option>
              <option value="buddy">{t("detail.metadata.actions.buddy")}</option>
              <option value="transfer">{t("detail.metadata.actions.transfer")}</option>
            </Select>
          </Field>
          <Field label={t("detail.metadata.plannedLeague")}>
            <Select className="w-full" value={form.planned_league} onChange={(e) => setForm({ ...form, planned_league: e.target.value })}>
              <option value="">{t("detail.metadata.none")}</option>
              <option value="great">Great League</option>
              <option value="ultra">Ultra League</option>
              <option value="master">Master League</option>
            </Select>
          </Field>
          <Field label={t("detail.metadata.review")}>
            <Select className="w-full" value={form.review_status} onChange={(e) => setForm({ ...form, review_status: e.target.value })}>
              <option value="none">{t("detail.metadata.none")}</option>
              <option value="to_review">{t("detail.metadata.toReview")}</option>
              <option value="reviewed">{t("detail.metadata.reviewed")}</option>
            </Select>
          </Field>
          <Field label={t("detail.metadata.override")}>
            <Select className="w-full" value={form.override_status} onChange={(e) => setForm({ ...form, override_status: e.target.value })}>
              <option value="">{t("detail.metadata.followOak")}</option>
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
          <Alert tone="warning" title={t("detail.metadata.vintageTitle", { year: pokemon.vintage_year })}>
            {t("detail.metadata.vintageWarning")}
          </Alert>
        )}
        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            loading={save.isPending}
            onClick={() => {
              if (!liftsVintage) save.mutate(false);
              else if (window.confirm(t("detail.metadata.vintageConfirm", { year: pokemon.vintage_year }))) save.mutate(true);
            }}
          >
            {t("detail.metadata.save")}
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
  const { t } = useTranslation();
  return (
    <Card title={t("detail.scenario.title")}>
      <Tabs
        value={value}
        onChange={onChange}
        tabs={[
          { value: "current", label: t("detail.scenario.current") },
          { value: "purified", label: t("detail.scenario.purified") },
        ]}
      />
      <p className="mt-3 text-xs text-muted">{t("detail.scenario.explanation")}</p>
    </Card>
  );
}

function PurifySummary({ scenario }: { scenario: PurifyScenario }) {
  const { t } = useTranslation();
  return (
    <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3 text-sm">
      <p>
        {t("detail.purify.summary", {
          level: level(scenario.level),
          ivs: `${scenario.ivs.attack}/${scenario.ivs.defense}/${scenario.ivs.stamina}`,
          cp: num(scenario.cp),
          stardust: num(scenario.cost.stardust),
          candy: num(scenario.cost.candy),
        })}
      </p>
      {scenario.assumption && <p className="mt-1 text-xs text-amber-300">{serverText("analysis", scenario.assumption)}</p>}
      {scenario.source && <p className="mt-1 text-xs text-muted">{t("detail.purify.source", { source: scenario.source })}</p>}
    </div>
  );
}

function AnalysisCard({ pokemonId, scenario }: { pokemonId: number; scenario: Scenario }) {
  const { t } = useTranslation();
  const [league, setLeague] = useState<"great" | "ultra" | "master">("great");
  const analysis = useQuery({
    queryKey: ["pokemon-analysis", pokemonId, scenario],
    queryFn: () => api.get<PokemonAnalysis>(`/api/v1/pokemon/${pokemonId}/analysis`, scenarioParams(scenario)),
  });
  if (analysis.isLoading) return <Card title={t("detail.analysis.title")}><Spinner /></Card>;
  const data = analysis.data;
  if (!data?.available || !data.leagues) {
    return (
      <Card title={t("detail.analysis.title")}>
        <p className="text-sm text-muted">
          {analysis.error ? errorMessage(analysis.error) : data?.reason ? serverText("analysis", data.reason) : t("detail.analysis.unavailable")}
        </p>
      </Card>
    );
  }
  const current = data.leagues[league];
  return (
    <Card title={t("detail.analysis.title")} actions={<span className="text-xs text-muted">Game Data v{data.game_data_version}</span>}>
      <Tabs
        value={league}
        onChange={setLeague}
        tabs={(["great", "ultra", "master"] as const).map((l) => ({ value: l, label: leagueNames[l] }))}
      />
      {data.scenario && <PurifySummary scenario={data.scenario} />}
      <div className="mt-3 grid gap-2 text-xs text-muted md:grid-cols-3">
        <p><b className="text-ink">{t("detail.analysis.ivRank")}</b>: {serverText("analysis", data.method?.iv_rank)}</p>
        <p><b className="text-ink">{t("detail.analysis.speciesRank")}</b>: {serverText("analysis", data.method?.species_rank)}</p>
        <p><b className="text-ink">{t("detail.analysis.readiness")}</b>: {serverText("analysis", data.method?.readiness)}</p>
      </div>
      {!current || current.targets.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{t("detail.analysis.noTarget")}</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-2 pr-3">{t("detail.analysis.target")}</th>
                <th className="pr-3">{t("detail.analysis.ivRank")}</th>
                <th className="pr-3">{t("detail.analysis.percentOfBest")}</th>
                <th className="pr-3">{t("detail.analysis.bestCp")}</th>
                <th className="pr-3">{t("detail.analysis.readiness")}</th>
                <th className="pr-3">{t("detail.analysis.cost")}</th>
                <th className="pr-3">{t("detail.analysis.speciesRank")}</th>
              </tr>
            </thead>
            <tbody>
              {current.targets.map((target) => (
                <tr key={target.target_key} className="border-t border-line align-top">
                  <td className="py-2 pr-3">
                    <p className="font-medium">
                      {target.target_name}
                      {target.target_key === current.primary_target && <Badge className="ml-2">{t("detail.analysis.primary")}</Badge>}
                    </p>
                    {target.is_evolution && (
                      <p className="text-xs text-muted">
                        {t("detail.analysis.afterEvolution", { candy: num(target.evolution_candy, "?") })}
                        {target.evolution_item ? ` + ${target.evolution_item.replace("ITEM_", "").toLowerCase()}` : ""}
                      </p>
                    )}
                    {target.moveset && (
                      <div className="mt-1 text-xs">
                        <span className="text-muted">{t("detail.analysis.recommended")} </span>
                        {target.moveset.names.join(" · ")}
                        {target.moveset.source === "pvpoke_usage_filtered" && <span className="text-amber-300"> {t("detail.analysis.withoutElite")}</span>}
                        <ul className="mt-1 space-y-0.5">
                          {target.moveset.needs
                            .filter((n) => n.action !== "none")
                            .map((n, i) => (
                              <li key={i} className={n.action === "impossible" ? "text-red-300" : "text-muted"}>
                                {label(moveActionLabels, n.action)}
                                {n.target ? ` → ${moveName(target.moveset, n.target)}` : ""}
                                {n.pool_size && n.action.endsWith("_tm") && !n.action.startsWith("elite")
                                  ? ` ${t("detail.analysis.randomFrom", { size: n.pool_size })}`
                                  : ""}
                              </li>
                            ))}
                        </ul>
                      </div>
                    )}
                  </td>
                  <td className="pr-3 tabular-nums">{target.rank}</td>
                  <td className="pr-3 tabular-nums">{pct(target.percent, 2)}</td>
                  <td className="pr-3 tabular-nums">
                    {num(target.best_cp)} / L{level(target.best_level)}
                    <p className="text-xs text-muted">{t("detail.analysis.cpNow", { cp: num(target.cp_now, "?") })}</p>
                  </td>
                  <td className="pr-3">
                    <ReadinessBadge readiness={target.readiness} />
                    <p className="mt-0.5 text-xs text-muted">{serverText("readiness", target.readiness_reason)}</p>
                  </td>
                  <td className="pr-3 text-xs tabular-nums">
                    {target.cost ? (
                      <>
                        {num(target.cost.stardust)} stardust
                        <br />
                        {num(target.cost.candy)} candy{target.cost.xl_candy ? `, ${num(target.cost.xl_candy)} XL` : ""}
                      </>
                    ) : (
                      "–"
                    )}
                  </td>
                  <td className="pr-3 tabular-nums">
                    {target.species_rank ?? "–"}
                    {target.species_score !== null && <p className="text-xs text-muted">{t("detail.analysis.score", { score: target.species_score })}</p>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.current_moves && data.current_moves.length > 0 && (
        <div className="mt-4 text-sm">
          <p className="mb-1 text-xs text-muted">{t("detail.analysis.currentMoves")}</p>
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
        {t("detail.maxLevel", { level: level(data.rules?.max_level) })}
        {data.rules?.include_best_buddy ? " + Best Buddy" : ""} ·{" "}
        {data.rules?.elite_tm_available ? t("detail.analysis.eliteAvailable") : t("detail.analysis.eliteUnavailable")} · {t("detail.analysis.ivNote")}
      </p>
    </Card>
  );
}

function EvolutionsCard({ pokemonId, scenario }: { pokemonId: number; scenario: Scenario }) {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ["pokemon-evolutions", pokemonId, scenario],
    queryFn: () =>
      api.get<{ available: boolean; paths: EvolutionPath[]; reason?: ServerText }>(`/api/v1/pokemon/${pokemonId}/evolutions`, scenarioParams(scenario)),
  });
  if (query.isLoading) return null;
  const paths = query.data?.paths ?? [];
  return (
    <Card title={scenario === "purified" ? t("detail.evolutions.titlePurified") : t("detail.evolutions.title")}>
      {paths.length === 0 ? (
        <p className="text-sm text-muted">
          {query.error ? errorMessage(query.error) : query.data?.reason ? serverText("analysis", query.data.reason) : t("detail.evolutions.none")}
        </p>
      ) : (
        <ul className="space-y-3">
          {paths.map((path) => (
            <li key={path.target_key} className="rounded-lg border border-line p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">{path.target_name}</p>
                <span className="tabular-nums">{t("detail.evolutions.cpAfter", { cp: num(path.cp_after) })}</span>
              </div>
              <p className="mt-1 text-xs text-muted">
                {num(path.total_candy, "?")} candy
                {path.steps.map((s) =>
                  [
                    s.item && ` · ${s.item.replace("ITEM_", "").toLowerCase()}`,
                    s.lure && ` · ${s.lure.replace("ITEM_", "").toLowerCase()}`,
                    s.buddy_km && ` · ${t("detail.evolutions.buddyKm", { km: num(s.buddy_km) })}`,
                    s.quest && ` · ${t("detail.evolutions.quest")}`,
                    ...s.conditions.map((c) => ` · ${label(conditionLabels, c)}`),
                  ]
                    .filter(Boolean)
                    .join(""),
                )}
              </p>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                {Object.entries(path.leagues).map(([lg, info]) => (
                  <Badge key={lg} color={info.over_cap ? "#f87171" : undefined}>
                    {leagueNames[lg]}: {info.over_cap ? t("detail.evolutions.overCap") : t("detail.evolutions.rank", { rank: info.rank ?? "–" })}
                  </Badge>
                ))}
              </div>
              {path.elite_moves.length > 0 && <p className="mt-1 text-xs text-amber-300">{t("detail.evolutions.eliteWarning")}</p>}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-muted">{t("detail.evolutions.note")}</p>
    </Card>
  );
}

function PowerUpCard({ pokemonId, scenario }: { pokemonId: number; scenario: Scenario }) {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ["pokemon-powerups", pokemonId, scenario],
    queryFn: () => api.get<PowerUps>(`/api/v1/pokemon/${pokemonId}/powerups`, scenarioParams(scenario)),
  });
  const [showAll, setShowAll] = useState(false);
  const data = query.data;
  if (!data?.available || !data.steps) return null;
  const steps = showAll ? data.steps : data.steps.filter((_, i) => i < 6 || i % 4 === 3);
  return (
    <Card
      title={data.scenario ? t("detail.powerUps.titlePurified") : t("detail.powerUps.title")}
      actions={<span className="text-xs text-muted">{t("detail.maxLevel", { level: level(data.max_level) })}</span>}
    >
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted">
          <tr>
            <th className="py-1">{t("detail.powerUps.level")}</th>
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
        {showAll ? t("detail.powerUps.showLess") : t("detail.powerUps.showAll")}
      </Button>
      <p className="mt-2 text-xs text-muted">
        {t("detail.powerUps.costs", {
          start: data.scenario ? t("detail.powerUps.fromPurified") : t("detail.powerUps.fromCurrent"),
          modifiers: [
            data.modifiers?.lucky && `, ${t("detail.powerUps.lucky")}`,
            data.modifiers?.shadow && `, ${t("detail.powerUps.shadow")}`,
            data.modifiers?.purified && `, ${t("detail.powerUps.purified")}`,
          ]
            .filter(Boolean)
            .join(""),
        })}{" "}
        {t("detail.powerUps.candyUnknown")} {serverText("analysis", data.note)}
      </p>
    </Card>
  );
}

interface CupRanking {
  league: string;
  target: string;
  rank: number;
  percent: number;
  best_cp: number;
  readiness: string;
  species_rank: number | null;
}

/** The cups this Pokémon, or an evolution of it, may enter (ADR-0027). */
function CupsCard({ pokemonId }: { pokemonId: number }) {
  const { t } = useTranslation();
  const leagues = useLeagues();
  const query = useQuery({
    queryKey: ["pokemon-battle", pokemonId],
    queryFn: () => api.get<{ rankings: CupRanking[] }>(`/api/v1/battles/pokemon/${pokemonId}`),
  });
  const cups = (leagues.data ?? []).filter((l) => l.kind === "cup");
  if (!cups.length || !query.data) return null;
  const rows = cups
    .map((cup) => {
      const usable = query.data.rankings.filter((r) => r.league === cup.id && r.readiness !== "not_suitable" && r.readiness !== "unknown");
      const best = usable.sort((a, b) => (a.species_rank ?? 9999) - (b.species_rank ?? 9999) || a.rank - b.rank)[0];
      return best ? { cup, best } : null;
    })
    .filter((row) => row !== null);
  return (
    <Card title={t("detail.cups.title")}>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("detail.cups.none")}</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {rows.map(({ cup, best }) => (
            <li key={cup.id} className="flex flex-wrap items-center justify-between gap-2">
              <Link to={`/battles/${cup.id}`} className="font-medium hover:text-oak-300">
                {cup.name}
              </Link>
              <span className="text-xs text-muted">
                {t("detail.cups.ranking", { target: best.target, rank: best.rank, cp: num(best.best_cp) })}
                {best.species_rank !== null ? ` · ${t("detail.cups.speciesRank", { rank: best.species_rank })}` : ""}
              </span>
              <ReadinessBadge readiness={best.readiness} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function HistoryCard({ pokemonId }: { pokemonId: number }) {
  const { t } = useTranslation();
  const query = useQuery({ queryKey: ["pokemon-history", pokemonId], queryFn: () => api.get<HistoryEvent[]>(`/api/v1/pokemon/${pokemonId}/history`) });
  const events = query.data ?? [];
  return (
    <Card title={t("detail.history.title")}>
      {events.length === 0 ? (
        <p className="text-sm text-muted">{t("detail.history.none")}</p>
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
  const { t } = useTranslation();
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
  if (query.error || !query.data) return <EmptyState title={t("detail.notFound")}>{query.error ? errorMessage(query.error) : null}</EmptyState>;
  const p = query.data;
  const details = p.details as Record<string, unknown>;
  // A Shadow Pokémon you plan to purify is shown as purified, until you choose otherwise.
  const chosen: Scenario = p.shadow ? (scenario ?? (p.metadata?.planned_action === "purify" ? "purified" : "current")) : "current";
  return (
    <>
      <Link to="/pokemon" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> {t("detail.back")}
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
            #{p.species_id} · {p.hatched_from_egg ? t("detail.hatched", { date: date(p.caught_at) }) : t("detail.caught", { date: date(p.caught_at) })} ·{" "}
            {p.inventory_status === "in_inventory" ? t("detail.inInventory") : t("detail.gone")}
          </p>
          <button
            className="inline-flex items-center gap-1 font-mono text-xs text-muted hover:text-ink"
            onClick={() => {
              void navigator.clipboard?.writeText(p.source_pokemon_id);
              setCopied(true);
            }}
            title={t("detail.idTitle")}
          >
            ID {p.source_pokemon_id} <Copy className="h-3 w-3" /> {copied && t("detail.copied")}
          </button>
          {p.form_resolution === "fallback_default_form" && <Alert tone="warning">{t("detail.formFallback", { form: p.form_name ?? "" })}</Alert>}
        </div>
        <div className="grid w-full grid-cols-3 gap-3 sm:w-auto sm:grid-cols-1">
          <div className="text-right">
            <p className="text-xs text-muted">CP</p>
            <p className="text-3xl font-semibold tabular-nums">{num(p.cp, "?")}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted">{t("detail.hpLevel")}</p>
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
          {chosen === "current" && <CupsCard pokemonId={p.id} />}
        </div>
        <div className="space-y-5">
          <Card title={t("detail.values.title")}>
            <IvBars attack={p.iv_attack} defense={p.iv_defense} stamina={p.iv_stamina} />
            <div className="mt-4">
              <KeyValue
                items={[
                  [t("detail.values.fastMove"), p.fast_move?.name ?? "?"],
                  [t("detail.values.chargedMoves"), p.charged_moves.map((m) => m.name).join(" / ") || "?"],
                  [
                    t("detail.values.secondMove"),
                    p.second_move_unlocked === null ? t("common.unknown") : p.second_move_unlocked ? t("detail.yes") : t("detail.no"),
                  ],
                  [t("detail.values.maxMoves"), p.max_moves.length ? p.max_moves.map((m) => `${m.type.replace("max_", "Max ")} ${m.level}`).join(", ") : "–"],
                  [t("detail.values.size"), `${decimal(details.height_m)} m / ${decimal(details.weight_kg)} kg`],
                  [t("detail.values.powerUps"), num(details.num_upgrades as number | null)],
                  [t("detail.values.buddyKm"), num(details.buddy_km_walked as number | null)],
                  [t("detail.values.fromEgg"), p.hatched_from_egg === null ? t("common.unknown") : p.hatched_from_egg ? t("detail.yes") : t("detail.no")],
                  [t("detail.values.firstSeen"), dateTime(p.first_seen_at)],
                  [t("detail.values.lastChanged"), dateTime(p.last_changed_at)],
                ]}
              />
            </div>
            {Array.isArray(details.origin_events) && details.origin_events.length > 0 && (
              <p className="mt-3 text-xs text-muted">{t("detail.values.event", { events: (details.origin_events as string[]).join(", ") })}</p>
            )}
            {p.tag_ids.length > 0 && (
              <p className="mt-2 text-xs text-muted">
                {t("detail.values.gameTags", {
                  tags: p.tag_labels.length ? p.tag_labels.join(", ") : t("detail.values.tagNamesUnknown", { count: p.tag_ids.length }),
                })}
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
