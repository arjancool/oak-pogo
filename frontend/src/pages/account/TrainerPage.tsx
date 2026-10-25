import { useQuery } from "@tanstack/react-query";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { Card, KeyValue, PageHeader, Spinner, Stat } from "../../components/ui";
import { api } from "../../lib/api";
import { dateTime, num } from "../../lib/format";
import { label, leagueNames, teamLabels, typeNames } from "../../lib/i18n";

interface Trainer {
  nickname: string;
  source_nickname: string | null;
  level: number | null;
  experience: number | null;
  stardust: number | null;
  pokecoins: number | null;
  team: number | null;
  storage: { pokemon: number; eggs: number; max: number | null };
  item_storage_max: number | null;
  stats: Record<string, unknown>;
  last_successful_sync_at: string | null;
}

const STAT_LABELS: Record<string, string> = {
  numPokemonCaptured: "Pokémon gevangen",
  numPokemonEncountered: "Pokémon tegengekomen",
  numEvolutions: "Evoluties",
  numEggsHatched: "Eieren uitgebroed",
  pokeStopVisits: "PokéStop-bezoeken",
  uniquePokestopsVisited: "Unieke PokéStops",
  kmWalked: "Kilometer gelopen",
  numberOfPokeballThrown: "Poké Balls gegooid",
  numRaidBattleWon: "Raids gewonnen",
  numRaidBattleTotal: "Raids totaal",
  numLegendaryBattleWon: "Legendary raids gewonnen",
  numGruntsDefeated: "Grunts verslagen",
  numTrades: "Ruilen",
  numRemoteTrades: "Ruilen op afstand",
  numBestBuddies: "Best Buddies",
  numUniquePokedexEntries: "Pokédex-inzendingen",
  numPokemonPurified: "Gepurified",
  numTotalMegaEvolutions: "Mega-evoluties",
  numBreadBattlesWon: "Max Battles gewonnen",
  numMaxLevelFriends: "Best Friends",
  numBerriesFed: "Berries gevoerd",
  numBattleTrainingWon: "Trainingsgevechten gewonnen",
  numNpcCombatsWon: "NPC-gevechten gewonnen",
};

function TrainerView({ accountId }: { accountId: number }) {
  const query = useQuery({ queryKey: ["trainer", accountId], queryFn: () => api.get<Trainer>("/api/v1/trainer", { account_id: accountId }) });
  if (query.isLoading || !query.data) return <Spinner />;
  const t = query.data;
  const stats = t.stats;
  const leagues = (stats.leagueBattles ?? {}) as Record<string, { battles: number; wins: number }>;
  const byType = (stats.numPokemonCaughtByType ?? []) as number[];
  const typeOrder = ["normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost", "steel", "fire", "water", "grass", "electric", "psychic", "ice", "dragon", "dark", "fairy"];
  return (
    <>
      <PageHeader title="Trainerstatistieken" description={`Bron: PGSharp-export · laatste sync ${dateTime(t.last_successful_sync_at)}`} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Trainer" value={t.source_nickname ?? t.nickname} hint={label(teamLabels as Record<string, string>, String(t.team ?? 0))} />
        <Stat label="Level" value={num(t.level)} />
        <Stat label="XP" value={num(t.experience)} />
        <Stat label="Stardust" value={num(t.stardust)} />
        <Stat label="PokéCoins" value={num(t.pokecoins)} />
        <Stat label="Pokémon-opslag" value={`${num(t.storage.pokemon + t.storage.eggs)} / ${num(t.storage.max)}`} hint={`${t.storage.eggs} eieren`} />
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card title="Activiteit">
          <KeyValue items={Object.entries(STAT_LABELS).filter(([key]) => stats[key] !== undefined).map(([key, text]) => [text, num(stats[key] as number)])} />
        </Card>
        <div className="space-y-5">
          <Card title="GO Battle League">
            <KeyValue
              items={[
                ...Object.entries(leagues).map(([league, value]): [string, string] => [leagueNames[league] ?? league, `${num(value.wins)} van ${num(value.battles)} gewonnen`]),
                ...(["currentSeasonResults", "lifetimeResults"] as const)
                  .filter((key) => stats[key])
                  .map((key): [string, string] => {
                    const r = stats[key] as Record<string, number>;
                    return [key === "currentSeasonResults" ? "Huidig seizoen" : "Totaal", `${num(r.totalWins ?? null)} / ${num(r.totalBattles ?? null)} · rang ${r.rank ?? "–"}`];
                  }),
              ]}
            />
          </Card>
          {byType.length > 1 && (
            <Card title="Gevangen per type">
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
                {typeOrder.map((type, index) => (
                  <div key={type} className="flex justify-between">
                    <span className="text-muted">{typeNames[type]}</span>
                    <span className="tabular-nums">{num(byType[index + 1] ?? null)}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

export function TrainerPage() {
  return <RequireAccount>{(id) => <TrainerView accountId={id} />}</RequireAccount>;
}
