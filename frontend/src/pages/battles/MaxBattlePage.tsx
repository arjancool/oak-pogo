import { useMutation } from "@tanstack/react-query";
import type { ParseKeys } from "i18next";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { TypeBadge } from "../../components/pokemon";
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { level, num } from "../../lib/format";
import { type ServerText, serverText } from "../../lib/serverText";
import { SpeciesPicker, type SpeciesOption } from "./shared";

interface MaxPokemon {
  pokemon_id: number;
  name: string | null;
  cp: number | null;
  level: number | null;
  gigantamax: boolean;
  types: string[];
  max_attack_type: string | null;
  max_attack_name: string | null;
  max_attack_source: "gmax_move" | "fast_move" | null;
  max_attack_unknown_reason: ServerText | null;
  fast_move: string | null;
  max_moves: Record<string, number>;
  next_upgrade_cost: Record<string, { mpCost?: number; candyCost?: number; xlCandyCost?: number } | null>;
  bread_group: string | null;
  attack_effectiveness: number | null;
  incoming_effectiveness: number | null;
}

const moveNames: Record<string, ParseKeys> = { attack: "battles.max.moves.attack", guard: "battles.max.moves.guard", spirit: "battles.max.moves.spirit" };

function MaxBattles({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const moveName = (move: string) => (moveNames[move] ? t(moveNames[move]) : move);
  const [boss, setBoss] = useState<SpeciesOption | null>(null);
  const run = useMutation({
    mutationFn: (bossKey: string | null) =>
      api.post<{ pokemon: MaxPokemon[]; advice: { attackers: MaxPokemon[]; defenders: MaxPokemon[] } | null; notes: ServerText[]; method: ServerText }>(
        "/api/v1/battles/max-counters",
        { account_id: accountId, boss_key: bossKey },
      ),
  });
  const { mutate } = run;
  useEffect(() => mutate(boss?.key ?? null), [boss, mutate]);
  const data = run.data;
  return (
    <>
      <PageHeader title={t("battles.max.title")} description={t("battles.max.description")} />
      <Card className="mb-5">
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-full max-w-md">
            <SpeciesPicker onPick={setBoss} placeholder={t("battles.max.search")} />
          </div>
          {boss && (
            <>
              <span className="font-medium">{boss.name}</span>
              {boss.types.map((type) => (
                <TypeBadge key={type} type={type} />
              ))}
              <Button size="sm" variant="ghost" onClick={() => setBoss(null)}>
                {t("battles.max.clear")}
              </Button>
            </>
          )}
        </div>
      </Card>
      {run.isPending && <Spinner />}
      {run.error && <Alert tone="error">{errorMessage(run.error)}</Alert>}
      {data && (
        <>
          <Alert tone="info">{data.notes.map((note) => serverText("battles", note)).join(" ")}</Alert>
          {data.advice && (
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <Card title={t("battles.max.attackers")}>
                <ul className="space-y-1 text-sm">
                  {data.advice.attackers.map((p) => (
                    <li key={p.pokemon_id}>
                      <Link to={`/pokemon/${p.pokemon_id}`} className="hover:text-oak-300">
                        {p.name}
                      </Link>{" "}
                      <span className="text-muted">
                        · {p.max_attack_source === "gmax_move" ? p.max_attack_name : p.fast_move} · ×{num(p.attack_effectiveness, "")}
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
              <Card title={t("battles.max.defenders")}>
                <ul className="space-y-1 text-sm">
                  {data.advice.defenders.map((p) => (
                    <li key={p.pokemon_id}>
                      <Link to={`/pokemon/${p.pokemon_id}`} className="hover:text-oak-300">
                        {p.name}
                      </Link>{" "}
                      <span className="text-muted">· {t("battles.max.incoming", { value: num(p.incoming_effectiveness, "") })}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
          )}
          <Card className="mt-4" title={t("battles.max.count", { number: num(data.pokemon.length) })}>
            {data.pokemon.length === 0 ? (
              <EmptyState title={t("battles.max.emptyTitle")}>{t("battles.max.emptyText")}</EmptyState>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm [&_td]:pr-3 [&_th]:pr-3">
                  <thead className="text-left text-xs text-muted">
                    <tr>
                      <th className="py-2">{t("battles.max.columns.pokemon")}</th>
                      <th>{t("battles.max.columns.maxAttackType")}</th>
                      <th>{t("battles.max.columns.maxMoves")}</th>
                      <th>{t("battles.max.columns.nextUpgrade")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.pokemon.map((p) => (
                      <tr key={p.pokemon_id} className="border-t border-line align-top">
                        <td className="py-2 pr-3">
                          <Link to={`/pokemon/${p.pokemon_id}`} className="font-medium hover:text-oak-300">
                            {p.name}
                          </Link>
                          {p.gigantamax && (
                            <Badge className="ml-1" color="#f43f5e">
                              {t("battles.max.gigantamax")}
                            </Badge>
                          )}
                          <span className="block text-xs text-muted">
                            CP {num(p.cp, "?")} · L{level(p.level)}
                          </span>
                        </td>
                        <td className="pr-3">
                          {p.max_attack_type ? (
                            <>
                              <TypeBadge type={p.max_attack_type} />
                              {p.max_attack_name && <span className="mt-1 block text-xs text-muted">{p.max_attack_name}</span>}
                            </>
                          ) : (
                            <span className="text-xs text-muted" title={p.max_attack_unknown_reason ? serverText("battles", p.max_attack_unknown_reason) : undefined}>
                              {t("common.unknown")}
                              {p.max_attack_unknown_reason && <span className="block">{serverText("battles", p.max_attack_unknown_reason)}</span>}
                            </span>
                          )}
                        </td>
                        <td className="pr-3 text-xs">
                          {Object.entries(p.max_moves).map(([move, lvl]) => (
                            <span key={move} className="block">
                              {t("battles.max.moveLevel", { move: moveName(move), level: num(lvl) })}
                            </span>
                          ))}
                        </td>
                        <td className="text-xs text-muted">
                          {Object.entries(p.next_upgrade_cost).map(([move, cost]) => (
                            <span key={move} className="block">
                              {moveName(move)}:{" "}
                              {cost
                                ? cost.candyCost
                                  ? t("battles.max.costCandy", { mp: num(cost.mpCost ?? null), candy: num(cost.candyCost) })
                                  : t("battles.max.costXl", { mp: num(cost.mpCost ?? null), xl: num(cost.xlCandyCost, "?") })
                                : t("battles.max.maxed")}
                            </span>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <p className="mt-3 text-xs text-muted">{serverText("battles", data.method)}</p>
        </>
      )}
    </>
  );
}

export function MaxBattlePage() {
  return <RequireAccount>{(id) => <MaxBattles accountId={id} />}</RequireAccount>;
}
