import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";
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
const classLabels: Record<string, string> = { legendary: "Legendary", mythical: "Mythical", ultra_beast: "Ultra Beast" };
const genderLabels: Record<string, string> = { MALE: "alleen mannetjes", FEMALE: "alleen vrouwtjes" };

function yesNo(value: boolean | null): string {
  return value === null ? "onbekend" : value ? "ja" : "nee";
}

function condition(value: string): string {
  if (value.startsWith("gender:")) return `Geslacht: ${genderLabels[value.slice(7)] ?? value.slice(7).toLowerCase()}`;
  return label(conditionLabels, value);
}

/** What one evolution step asks, in the words the game uses. */
function stepNeeds(step: PokedexStep): string[] {
  const needs = [step.candy !== null ? `${num(step.candy)} candy` : "candy onbekend"];
  if (step.item_name) {
    const have = step.item_have === undefined ? "" : step.item_have === null ? " (aantal in je tas onbekend)" : ` (je hebt er ${num(step.item_have)})`;
    needs.push(`${step.item_cost && step.item_cost > 1 ? `${step.item_cost}× ` : ""}${step.item_name}${have}`);
  }
  if (step.lure_name) needs.push(`binnen bereik van een ${step.lure_name}`);
  if (step.buddy_km) needs.push(`${num(step.buddy_km)} km lopen als buddy`);
  if (step.quest) needs.push("een evolutie-opdracht");
  if (step.no_candy_cost_via_trade) needs.push("gratis na ruilen");
  needs.push(...step.conditions.map(condition));
  return needs;
}

function SearchBox({ onPick }: { onPick: (dex: number) => void }) {
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
        placeholder="Naam of nummer, zoals Pyroar of 668"
        aria-label="Pokémon zoeken"
        className="pl-9"
        maxLength={40}
      />
      {query && (
        <div className="absolute z-10 mt-1 max-h-80 w-full overflow-y-auto rounded-lg border border-line bg-surface-2 shadow-lg">
          {results.isLoading && <p className="p-3 text-sm text-muted">Zoeken…</p>}
          {results.error && <p className="p-3 text-sm text-red-300">{errorMessage(results.error)}</p>}
          {results.data?.results.length === 0 && <p className="p-3 text-sm text-muted">Niets gevonden in de Game Data.</p>}
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
  const form = data.form;
  const facts: [string, string][] = [
    ["Familie", form.family ?? "onbekend"],
    ["Buddy-afstand", form.buddy_km !== null ? `${num(form.buddy_km)} km per candy` : "onbekend"],
    ["Ruilbaar", yesNo(form.tradable)],
    ["Over te zetten naar de professor", yesNo(form.transferable)],
    ["Mag in een gym", yesNo(form.deployable)],
  ];
  if (form.third_move?.stardust != null) facts.push(["Tweede charged-aanval", `${num(form.third_move.stardust)} stardust en ${num(form.third_move.candy, "?")} candy`]);
  if (form.shadow) facts.push(["Purify", `${num(form.shadow.purify_stardust, "?")} stardust en ${num(form.shadow.purify_candy, "?")} candy`]);
  if (form.mega.length) facts.push(["Mega-evolutie", form.mega.join(", ")]);
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
            {form.class && <Badge color="#f59e0b">{classLabels[form.class] ?? form.class}</Badge>}
          </div>
          {form.stats && (
            <p className="mt-1 text-sm text-muted">
              Basiswaarden: Attack {num(form.stats.atk, "?")} · Defense {num(form.stats.def, "?")} · HP {num(form.stats.sta, "?")}
            </p>
          )}
          {data.forms.length > 1 && (
            <Select className="mt-3" value={form.key} onChange={(e) => onForm(e.target.value)} aria-label="Vorm">
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
  const collection = data.collection;
  if (!collection) return null;
  const candy = collection.candy;
  return (
    <>
      <Card title={collection.owned_total ? `Je hebt ${num(collection.owned_total)} ${data.name}` : `Je hebt nog geen ${data.name}`}>
        {collection.owned.length === 0 ? (
          <p className="text-sm text-muted">Er staat geen {data.name} in de laatste import van dit traineraccount, in welke vorm dan ook.</p>
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
                {!p.same_form && <Badge>Andere vorm</Badge>}
                <StatusBadges pokemon={p} compact />
              </li>
            ))}
          </ul>
        )}
        {collection.owned_total > collection.owned.length && (
          <p className="mt-2 text-xs text-muted">De {collection.owned.length} met de hoogste CP staan hierboven.</p>
        )}
      </Card>
      <Card title={`Uit je collectie te evolueren tot ${data.form.name}`}>
        {collection.candidates.length === 0 ? (
          <p className="text-sm text-muted">
            {data.evolves_from.length === 0
              ? `${data.form.name} ontstaat niet door evolutie.`
              : `Je hebt geen ${data.evolves_from.map((f) => f.name).join(" of ")} of een eerdere vorm daarvan.`}
          </p>
        ) : (
          <>
            <p className="mb-3 text-xs text-muted">
              {candy.quantity !== null ? (
                <>Je hebt {num(candy.quantity)} candy voor deze familie, zelf ingevuld. </>
              ) : (
                <>
                  PGSharp exporteert geen candy, dus OAK weet niet of je genoeg hebt. Je kunt het zelf invullen bij{" "}
                  <Link to="/resources" className="text-oak-400 underline">
                    Stardust & Candy
                  </Link>
                  .{" "}
                </>
              )}
              Sterkste uitkomst eerst.
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
                        CP {num(c.pokemon.cp, "?")} → <span className="font-semibold">{num(c.cp_after, "onbekend")}</span> · {pct(c.pokemon.iv_percent)}
                      </span>
                      <StatusBadges pokemon={c.pokemon} compact />
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {c.steps.length > 1 ? `${c.steps.length} stappen, samen ${num(c.total_candy, "?")} candy. ` : ""}
                      {c.steps.map((s) => `${s.to_name}: ${stepNeeds(s).join(", ")}`).join(" → ")}
                    </p>
                    {c.cp_after === null && <p className="mt-1 text-xs text-muted">CP na evolutie onbekend, omdat level of IV's ontbreken.</p>}
                  </div>
                </li>
              ))}
            </ul>
            {collection.candidate_total > collection.candidates.length && (
              <p className="mt-2 text-xs text-muted">
                De eerste {collection.candidates.length} van {num(collection.candidate_total)} staan hierboven.
              </p>
            )}
          </>
        )}
      </Card>
    </>
  );
}

function Evolution({ data, onPick }: { data: PokedexSpecies; onPick: (dex: number, form?: string) => void }) {
  if (data.evolves_from.length === 0 && data.evolves_to.length === 0) return null;
  return (
    <Card title="Evolutielijn">
      {data.evolves_from.length > 0 && (
        <p className="text-sm">
          Evolueert uit{" "}
          {data.evolves_from.map((f, index) => (
            <span key={f.key}>
              {index > 0 && " of "}
              <button className="text-oak-400 underline" onClick={() => onPick(f.dex, f.key)}>
                {f.name}
              </button>
            </span>
          ))}
          .
        </p>
      )}
      {data.evolves_to.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {data.evolves_to.map((step) => (
            <li key={step.to_key}>
              Evolueert tot{" "}
              <button className="text-oak-400 underline" onClick={() => onPick(step.dex, step.to_key)}>
                {step.to_name}
              </button>
              <span className="text-muted">: {stepNeeds(step).join(", ")}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Battle({ data }: { data: PokedexSpecies }) {
  return (
    <Card title="In gevechten">
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <p className="mb-1 text-xs font-medium uppercase text-muted">CP met 15/15/15</p>
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
          <p className="mb-1 text-xs font-medium uppercase text-muted">Plaats van de soort bij PvPoke</p>
          <ul className="space-y-1 text-sm">
            {data.leagues.map((lg) => (
              <li key={lg.league}>
                <span className="text-muted">{lg.name}: </span>
                {lg.species_rank !== null ? `#${lg.species_rank}` : "niet gerangschikt"}
                {lg.shadow_rank !== null && <span className="text-muted"> · Shadow #{lg.shadow_rank}</span>}
                {lg.moveset.length > 0 && <span className="block text-xs text-muted">Aanvallen: {lg.moveset.join(", ")}</span>}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <p className="mt-3 text-sm">
        <span className="text-muted">Als gymverdediger: </span>
        {data.gym
          ? `#${data.gym.rank} van alle Pokémon die in een gym mogen${data.gym.is_evolution ? `, na evolutie tot ${data.gym.target_name}` : ""}.`
          : data.form.deployable === false
            ? "mag niet in een gym."
            : "onbekend, de Game Data zegt niet of hij in een gym mag."}
      </p>
    </Card>
  );
}

function Moves({ data }: { data: PokedexSpecies }) {
  const groups = [
    ["Fast", data.moves.fast],
    ["Charged", data.moves.charged],
  ] as const;
  return (
    <Card title="Aanvallen">
      <div className="grid gap-4 md:grid-cols-2">
        {groups.map(([title, moves]) => (
          <div key={title}>
            <p className="mb-1 text-xs font-medium uppercase text-muted">{title}</p>
            <ul className="space-y-1 text-sm">
              {moves.map((m) => (
                <li key={m.key} className="flex flex-wrap items-center gap-2">
                  {m.name}
                  {m.type && <TypeBadge type={m.type} />}
                  {m.elite && <Badge color="#f59e0b">Elite TM</Badge>}
                  {m.legacy && !m.elite && <Badge color="#94a3b8">Legacy</Badge>}
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
      {accountId === null && <Alert tone="info">Maak een traineraccount aan om te zien wat je collectie met deze Pokémon kan.</Alert>}
      <Collection data={data} />
      <Evolution data={data} onPick={onPick} />
      <Battle data={data} />
      <Moves data={data} />
      <p className="text-xs text-muted">Bron: de actieve Game Data, versie {data.game_data_version}. De ranglijsten komen van PvPoke.</p>
    </div>
  );
}

export function PokedexPage() {
  const params = useParams();
  const navigate = useNavigate();
  const [state] = useUrlState();
  const { accountId } = useAccount();
  const dex = params.dex ? Number(params.dex) : null;
  const pick = (next: number, form?: string) => void navigate(`/pokedex/${next}${form ? `?form=${encodeURIComponent(form)}` : ""}`);
  return (
    <>
      <PageHeader
        title="Pokédex"
        description="Zoek iedere Pokémon uit de Game Data. Je ziet wat hij kan, of je hem al hebt en welke Pokémon uit je collectie je ernaartoe kunt evolueren."
      />
      <SearchBox onPick={(next) => pick(next)} />
      {dex !== null && Number.isInteger(dex) && dex > 0 ? (
        <Species dex={dex} form={state.form ?? null} accountId={accountId} onPick={pick} />
      ) : (
        <EmptyState title="Zoek een Pokémon">Typ een naam of een Pokédex-nummer. Je hoeft de Pokémon niet zelf te hebben.</EmptyState>
      )}
    </>
  );
}
