import { useQuery } from "@tanstack/react-query";
import type { ParseKeys, TFunction } from "i18next";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";

import { PokemonSprite, StatusBadges, TypeBadge, pokemonName } from "../../components/pokemon";
import { Alert, Badge, Card, EmptyState, Input, KeyValue, PageHeader, Select, Spinner } from "../../components/ui";
import { errorMessage, getParsed } from "../../lib/api";
import { useAccount } from "../../lib/account";
import { level, num, pct } from "../../lib/format";
import { conditionLabels, label } from "../../lib/i18n";
import { type PokedexSpecies, type PokedexStep, pokedexSearch, pokedexSpecies } from "../../lib/schemas";
import { useUrlState } from "../../lib/useUrlState";

const SEARCH_DELAY_MS = 250;
const classLabels: Record<string, ParseKeys> = {
  legendary: "pokedex.classes.legendary",
  mythical: "pokedex.classes.mythical",
  ultra_beast: "pokedex.classes.ultraBeast",
};
const genderLabels: Record<string, ParseKeys> = { MALE: "pokedex.gender.male", FEMALE: "pokedex.gender.female" };

function yesNo(t: TFunction, value: boolean | null): string {
  return value === null ? t("common.unknown") : value ? t("pokedex.yes") : t("pokedex.no");
}

function condition(t: TFunction, value: string): string {
  if (value.startsWith("gender:")) {
    const gender = genderLabels[value.slice(7)];
    return t("pokedex.gender.label", { gender: gender ? t(gender) : value.slice(7).toLowerCase() });
  }
  return label(conditionLabels, value);
}

/** What one evolution step asks, in the words the game uses. */
function stepNeeds(t: TFunction, step: PokedexStep): string[] {
  const needs = [step.candy !== null ? `${num(step.candy)} candy` : t("pokedex.needs.candyUnknown")];
  if (step.item_name) {
    const item = `${step.item_cost && step.item_cost > 1 ? `${step.item_cost}× ` : ""}${step.item_name}`;
    needs.push(
      step.item_have === undefined
        ? item
        : step.item_have === null
          ? t("pokedex.needs.itemHaveUnknown", { item })
          : t("pokedex.needs.itemHave", { item, have: num(step.item_have) }),
    );
  }
  if (step.lure_name) needs.push(t("pokedex.needs.lure", { lure: step.lure_name }));
  if (step.buddy_km) needs.push(t("pokedex.needs.buddyKm", { km: num(step.buddy_km) }));
  if (step.quest) needs.push(t("pokedex.needs.quest"));
  if (step.no_candy_cost_via_trade) needs.push(t("pokedex.needs.freeAfterTrade"));
  needs.push(...step.conditions.map((value) => condition(t, value)));
  return needs;
}

function SearchBox({ onPick }: { onPick: (dex: number) => void }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(text.trim()), SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [text]);
  const results = useQuery({
    queryKey: ["pokedex-search", query],
    queryFn: () => getParsed(pokedexSearch, "/api/v1/pokedex/search", { q: query }),
    enabled: query.length > 0,
  });
  return (
    <div className="relative mb-5 max-w-xl">
      <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" />
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t("pokedex.search.placeholder")}
        aria-label={t("pokedex.search.label")}
        className="pl-9"
        maxLength={40}
      />
      {query && (
        <div className="absolute z-10 mt-1 max-h-80 w-full overflow-y-auto rounded-lg border border-line bg-surface-2 shadow-lg">
          {results.isLoading && <p className="p-3 text-sm text-muted">{t("pokedex.search.searching")}</p>}
          {results.error && <p className="p-3 text-sm text-red-300">{errorMessage(results.error)}</p>}
          {results.data?.results.length === 0 && <p className="p-3 text-sm text-muted">{t("pokedex.search.none")}</p>}
          {results.data?.results.map((hit) => (
            <button
              key={hit.dex}
              className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-surface-3"
              onClick={() => {
                setText("");
                setQuery("");
                onPick(hit.dex);
              }}
            >
              <PokemonSprite dex={hit.dex} types={hit.types} size={28} />
              <span className="w-12 font-mono text-xs text-muted">#{hit.dex}</span>
              <span className="flex-1 font-medium">{hit.name}</span>
              {hit.types.map((t) => (
                <TypeBadge key={t} type={t} />
              ))}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Overview({ data, onForm }: { data: PokedexSpecies; onForm: (key: string) => void }) {
  const { t } = useTranslation();
  const form = data.form;
  const classLabel = form.class ? classLabels[form.class] : undefined;
  const facts: [string, string][] = [
    [t("pokedex.facts.family"), form.family ?? t("common.unknown")],
    [t("pokedex.facts.buddyKm"), form.buddy_km !== null ? t("pokedex.facts.buddyKmValue", { km: num(form.buddy_km) }) : t("common.unknown")],
    [t("pokedex.facts.tradable"), yesNo(t, form.tradable)],
    [t("pokedex.facts.transferable"), yesNo(t, form.transferable)],
    [t("pokedex.facts.deployable"), yesNo(t, form.deployable)],
  ];
  if (form.third_move?.stardust != null)
    facts.push([t("pokedex.facts.thirdMove"), t("pokedex.facts.cost", { stardust: num(form.third_move.stardust), candy: num(form.third_move.candy, "?") })]);
  if (form.shadow)
    facts.push([t("pokedex.facts.purify"), t("pokedex.facts.cost", { stardust: num(form.shadow.purify_stardust, "?"), candy: num(form.shadow.purify_candy, "?") })]);
  if (form.mega.length) facts.push([t("pokedex.facts.mega"), form.mega.join(", ")]);
  return (
    <Card>
      <div className="flex flex-wrap items-start gap-4">
        <PokemonSprite dex={data.dex} types={form.types} size={72} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold">{form.name}</h2>
            <span className="font-mono text-sm text-muted">#{data.dex}</span>
            {form.types.map((t) => (
              <TypeBadge key={t} type={t} />
            ))}
            {form.class && <Badge color="#f59e0b">{classLabel ? t(classLabel) : form.class}</Badge>}
          </div>
          {form.stats && (
            <p className="mt-1 text-sm text-muted">
              {t("pokedex.baseStats", { atk: num(form.stats.atk, "?"), def: num(form.stats.def, "?"), sta: num(form.stats.sta, "?") })}
            </p>
          )}
          {data.forms.length > 1 && (
            <Select className="mt-3" value={form.key} onChange={(e) => onForm(e.target.value)} aria-label={t("pokedex.form")}>
              {data.forms.map((f) => (
                <option key={f.key} value={f.key}>
                  {f.name}
                </option>
              ))}
            </Select>
          )}
        </div>
      </div>
      <div className="mt-4">
        <KeyValue items={facts} />
      </div>
    </Card>
  );
}

function Collection({ data }: { data: PokedexSpecies }) {
  const { t } = useTranslation();
  const collection = data.collection;
  if (!collection) return null;
  const candy = collection.candy;
  return (
    <>
      <Card
        title={
          collection.owned_total
            ? t("pokedex.collection.owned", { amount: num(collection.owned_total), name: data.name })
            : t("pokedex.collection.none", { name: data.name })
        }
      >
        {collection.owned.length === 0 ? (
          <p className="text-sm text-muted">{t("pokedex.collection.noneText", { name: data.name })}</p>
        ) : (
          <ul className="divide-y divide-line">
            {collection.owned.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                <PokemonSprite dex={p.species_id} shiny={p.shiny} types={p.types} size={32} />
                <Link to={`/pokemon/${p.id}`} className="font-medium hover:text-oak-300">
                  {pokemonName(p)}
                </Link>
                <span className="tabular-nums text-muted">
                  CP {num(p.cp, "?")} · L{level(p.level)} · {pct(p.iv_percent)}
                </span>
                {!p.same_form && <Badge>{t("pokedex.collection.otherForm")}</Badge>}
                <StatusBadges pokemon={p} compact />
              </li>
            ))}
          </ul>
        )}
        {collection.owned_total > collection.owned.length && (
          <p className="mt-2 text-xs text-muted">{t("pokedex.collection.topCp", { shown: num(collection.owned.length) })}</p>
        )}
      </Card>
      <Card title={t("pokedex.candidates.title", { name: data.form.name })}>
        {collection.candidates.length === 0 ? (
          <p className="text-sm text-muted">
            {data.evolves_from.length === 0
              ? t("pokedex.candidates.notEvolved", { name: data.form.name })
              : t("pokedex.candidates.none", { names: data.evolves_from.map((f) => f.name).join(` ${t("pokedex.or")} `) })}
          </p>
        ) : (
          <>
            <p className="mb-3 text-xs text-muted">
              {candy.quantity !== null ? (
                <>{t("pokedex.candidates.candyKnown", { candy: num(candy.quantity) })} </>
              ) : (
                <>
                  <Trans i18nKey="pokedex.candidates.candyUnknown" components={{ resourcesLink: <Link to="/resources" className="text-oak-400 underline" /> }} />{" "}
                </>
              )}
              {t("pokedex.candidates.strongestFirst")}
            </p>
            <ul className="divide-y divide-line">
              {collection.candidates.map((c) => (
                <li key={c.pokemon.id} className="flex flex-wrap items-start gap-3 py-3 text-sm">
                  <PokemonSprite dex={c.pokemon.species_id} shiny={c.pokemon.shiny} types={c.pokemon.types} size={36} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link to={`/pokemon/${c.pokemon.id}`} className="font-medium hover:text-oak-300">
                        {pokemonName(c.pokemon)}
                      </Link>
                      <span className="tabular-nums text-muted">
                        CP {num(c.pokemon.cp, "?")} → <span className="font-semibold">{num(c.cp_after)}</span> · {pct(c.pokemon.iv_percent)}
                      </span>
                      <StatusBadges pokemon={c.pokemon} compact />
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {c.steps.length > 1 ? `${t("pokedex.candidates.steps", { steps: num(c.steps.length), candy: num(c.total_candy, "?") })} ` : ""}
                      {c.steps.map((s) => `${s.to_name}: ${stepNeeds(t, s).join(", ")}`).join(" → ")}
                    </p>
                    {c.cp_after === null && <p className="mt-1 text-xs text-muted">{t("pokedex.candidates.cpUnknown")}</p>}
                  </div>
                </li>
              ))}
            </ul>
            {collection.candidate_total > collection.candidates.length && (
              <p className="mt-2 text-xs text-muted">
                {t("pokedex.candidates.firstShown", { shown: num(collection.candidates.length), total: num(collection.candidate_total) })}
              </p>
            )}
          </>
        )}
      </Card>
    </>
  );
}

function Evolution({ data, onPick }: { data: PokedexSpecies; onPick: (dex: number, form?: string) => void }) {
  const { t } = useTranslation();
  if (data.evolves_from.length === 0 && data.evolves_to.length === 0) return null;
  return (
    <Card title={t("pokedex.evolution.title")}>
      {data.evolves_from.length > 0 && (
        <p className="text-sm">
          <Trans
            i18nKey="pokedex.evolution.from"
            components={{
              names: (
                <>
                  {data.evolves_from.map((f, index) => (
                    <span key={f.key}>
                      {index > 0 && ` ${t("pokedex.or")} `}
                      <button className="text-oak-400 underline" onClick={() => onPick(f.dex, f.key)}>
                        {f.name}
                      </button>
                    </span>
                  ))}
                </>
              ),
            }}
          />
        </p>
      )}
      {data.evolves_to.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {data.evolves_to.map((step) => (
            <li key={step.to_key}>
              <Trans
                i18nKey="pokedex.evolution.to"
                values={{ name: step.to_name }}
                components={{ target: <button className="text-oak-400 underline" onClick={() => onPick(step.dex, step.to_key)} /> }}
              />
              <span className="text-muted">: {stepNeeds(t, step).join(", ")}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Battle({ data }: { data: PokedexSpecies }) {
  const { t } = useTranslation();
  return (
    <Card title={t("pokedex.battle.title")}>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <p className="mb-1 text-xs font-medium uppercase text-muted">{t("pokedex.battle.cpTable")}</p>
          <ul className="space-y-0.5 text-sm">
            {data.cp_table.map((row) => (
              <li key={row.level} className="flex justify-between gap-4">
                <span className="text-muted">{row.label}</span>
                <span className="tabular-nums">{num(row.cp)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="mb-1 text-xs font-medium uppercase text-muted">{t("pokedex.battle.speciesRank")}</p>
          <ul className="space-y-1 text-sm">
            {data.leagues.map((lg) => (
              <li key={lg.league}>
                <span className="text-muted">{lg.name}: </span>
                {lg.species_rank !== null ? `#${lg.species_rank}` : t("pokedex.battle.notRanked")}
                {lg.shadow_rank !== null && <span className="text-muted"> · Shadow #{lg.shadow_rank}</span>}
                {lg.moveset.length > 0 && <span className="block text-xs text-muted">{t("pokedex.battle.moveset", { moves: lg.moveset.join(", ") })}</span>}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <p className="mt-3 text-sm">
        <span className="text-muted">{t("pokedex.battle.gym")} </span>
        {data.gym
          ? data.gym.is_evolution
            ? t("pokedex.battle.gymRankEvolution", { rank: data.gym.rank, name: data.gym.target_name })
            : t("pokedex.battle.gymRank", { rank: data.gym.rank })
          : data.form.deployable === false
            ? t("pokedex.battle.gymNotAllowed")
            : t("pokedex.battle.gymUnknown")}
      </p>
    </Card>
  );
}

function Moves({ data }: { data: PokedexSpecies }) {
  const { t } = useTranslation();
  const groups = [
    ["pokedex.moves.fast", data.moves.fast],
    ["pokedex.moves.charged", data.moves.charged],
  ] as const;
  return (
    <Card title={t("pokedex.moves.title")}>
      <div className="grid gap-4 md:grid-cols-2">
        {groups.map(([title, moves]) => (
          <div key={title}>
            <p className="mb-1 text-xs font-medium uppercase text-muted">{t(title)}</p>
            <ul className="space-y-1 text-sm">
              {moves.map((m) => (
                <li key={m.key} className="flex flex-wrap items-center gap-2">
                  {m.name}
                  {m.type && <TypeBadge type={m.type} />}
                  {m.elite && <Badge color="#f59e0b">Elite TM</Badge>}
                  {m.legacy && !m.elite && <Badge color="#94a3b8">{t("pokedex.moves.legacy")}</Badge>}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Species({ dex, form, accountId, onPick }: { dex: number; form: string | null; accountId: number | null; onPick: (dex: number, form?: string) => void }) {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ["pokedex", dex, form, accountId],
    queryFn: () => getParsed(pokedexSpecies, `/api/v1/pokedex/${dex}`, { form, account_id: accountId }),
  });
  if (query.isLoading) return <Spinner />;
  if (query.error) return <Alert tone="error">{errorMessage(query.error)}</Alert>;
  const data = query.data;
  if (!data) return null;
  return (
    <div className="space-y-5">
      <Overview data={data} onForm={(key) => onPick(dex, key)} />
      {accountId === null && <Alert tone="info">{t("pokedex.noAccount")}</Alert>}
      <Collection data={data} />
      <Evolution data={data} onPick={onPick} />
      <Battle data={data} />
      <Moves data={data} />
      <p className="text-xs text-muted">{t("pokedex.source", { version: data.game_data_version })}</p>
    </div>
  );
}

export function PokedexPage() {
  const { t } = useTranslation();
  const params = useParams();
  const navigate = useNavigate();
  const [state] = useUrlState();
  const { accountId } = useAccount();
  const dex = params.dex ? Number(params.dex) : null;
  const pick = (next: number, form?: string) => void navigate(`/pokedex/${next}${form ? `?form=${encodeURIComponent(form)}` : ""}`);
  return (
    <>
      <PageHeader title={t("pokedex.title")} description={t("pokedex.description")} />
      <SearchBox onPick={(next) => pick(next)} />
      {dex !== null && Number.isInteger(dex) && dex > 0 ? (
        <Species dex={dex} form={state.form ?? null} accountId={accountId} onPick={pick} />
      ) : (
        <EmptyState title={t("pokedex.empty.title")}>{t("pokedex.empty.text")}</EmptyState>
      )}
    </>
  );
}
