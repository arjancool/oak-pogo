import { useQuery } from "@tanstack/react-query";
import type { ParseKeys } from "i18next";
import { useTranslation } from "react-i18next";

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

const STAT_LABELS: Record<string, ParseKeys> = {
  numPokemonCaptured: "account.trainer.stats.numPokemonCaptured",
  numPokemonEncountered: "account.trainer.stats.numPokemonEncountered",
  numEvolutions: "account.trainer.stats.numEvolutions",
  numEggsHatched: "account.trainer.stats.numEggsHatched",
  pokeStopVisits: "account.trainer.stats.pokeStopVisits",
  uniquePokestopsVisited: "account.trainer.stats.uniquePokestopsVisited",
  kmWalked: "account.trainer.stats.kmWalked",
  numberOfPokeballThrown: "account.trainer.stats.numberOfPokeballThrown",
  numRaidBattleWon: "account.trainer.stats.numRaidBattleWon",
  numRaidBattleTotal: "account.trainer.stats.numRaidBattleTotal",
  numLegendaryBattleWon: "account.trainer.stats.numLegendaryBattleWon",
  numGruntsDefeated: "account.trainer.stats.numGruntsDefeated",
  numTrades: "account.trainer.stats.numTrades",
  numRemoteTrades: "account.trainer.stats.numRemoteTrades",
  numBestBuddies: "account.trainer.stats.numBestBuddies",
  numUniquePokedexEntries: "account.trainer.stats.numUniquePokedexEntries",
  numPokemonPurified: "account.trainer.stats.numPokemonPurified",
  numTotalMegaEvolutions: "account.trainer.stats.numTotalMegaEvolutions",
  numBreadBattlesWon: "account.trainer.stats.numBreadBattlesWon",
  numMaxLevelFriends: "account.trainer.stats.numMaxLevelFriends",
  numBerriesFed: "account.trainer.stats.numBerriesFed",
  numBattleTrainingWon: "account.trainer.stats.numBattleTrainingWon",
  numNpcCombatsWon: "account.trainer.stats.numNpcCombatsWon",
};

function TrainerView({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const query = useQuery({ queryKey: ["trainer", accountId], queryFn: () => api.get<Trainer>("/api/v1/trainer", { account_id: accountId }) });
  if (query.isLoading || !query.data) return <Spinner />;
  const trainer = query.data;
  const stats = trainer.stats;
  const leagues = (stats.leagueBattles ?? {}) as Record<string, { battles: number; wins: number }>;
  const byType = (stats.numPokemonCaughtByType ?? []) as number[];
  const typeOrder = ["normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost", "steel", "fire", "water", "grass", "electric", "psychic", "ice", "dragon", "dark", "fairy"];
  return (
    <>
      <PageHeader title={t("account.trainer.title")} description={t("account.trainer.description", { time: dateTime(trainer.last_successful_sync_at) })} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label={t("account.trainer.trainer")} value={trainer.source_nickname ?? trainer.nickname} hint={label(teamLabels as Record<string, string>, String(trainer.team ?? 0))} />
        <Stat label={t("account.trainer.level")} value={num(trainer.level)} />
        <Stat label={t("account.trainer.xp")} value={num(trainer.experience)} />
        <Stat label={t("account.trainer.stardust")} value={num(trainer.stardust)} />
        <Stat label={t("account.trainer.pokecoins")} value={num(trainer.pokecoins)} />
        <Stat
          label={t("account.trainer.storage")}
          value={`${num(trainer.storage.pokemon + trainer.storage.eggs)} / ${num(trainer.storage.max)}`}
          hint={t("account.trainer.eggs", { count: trainer.storage.eggs })}
        />
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card title={t("account.trainer.activity")}>
          <KeyValue items={Object.entries(STAT_LABELS).filter(([key]) => stats[key] !== undefined).map(([key, text]) => [t(text), num(stats[key] as number)])} />
        </Card>
        <div className="space-y-5">
          <Card title={t("account.trainer.gbl")}>
            <KeyValue
              items={[
                ...Object.entries(leagues).map(([league, value]): [string, string] => [leagueNames[league] ?? league, t("account.trainer.leagueWins", { wins: num(value.wins), battles: num(value.battles) })]),
                ...(["currentSeasonResults", "lifetimeResults"] as const)
                  .filter((key) => stats[key])
                  .map((key): [string, string] => {
                    const r = stats[key] as Record<string, number>;
                    return [
                      key === "currentSeasonResults" ? t("account.trainer.currentSeason") : t("account.trainer.lifetime"),
                      t("account.trainer.results", { wins: num(r.totalWins ?? null), battles: num(r.totalBattles ?? null), rank: num(r.rank ?? null, "–") }),
                    ];
                  }),
              ]}
            />
          </Card>
          {byType.length > 1 && (
            <Card title={t("account.trainer.byType")}>
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
