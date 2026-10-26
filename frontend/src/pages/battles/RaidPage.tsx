import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { TypeBadge } from "../../components/pokemon";
import { Alert, Badge, Button, Card, PageHeader, SortHeader, Spinner } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { level, num } from "../../lib/format";
import { type ServerText, serverText } from "../../lib/serverText";
import { sortRows } from "../../lib/sort";
import { useUrlState } from "../../lib/useUrlState";
import { SpeciesPicker, type SpeciesOption } from "./shared";

interface Counter {
  pokemon_id: number;
  name: string | null;
  form_label: string | null;
  shadow: boolean;
  cp: number | null;
  level: number | null;
  types: string[];
  current: { dps: number; fast: string | null; charged: string | null; effectiveness: number };
  best_moveset: { dps: number; fast: string | null; charged: string | null; needs_tm: boolean; needs_elite_tm: boolean };
  weak_to_boss: boolean;
}

const DEFAULT_SORT = "-dps";
const COLUMNS = {
  name: (c: RankedCounter) => c.name?.toLocaleLowerCase("nl"),
  cp: (c: RankedCounter) => c.cp,
  dps: (c: RankedCounter) => c.current.dps,
  best_dps: (c: RankedCounter) => c.best_moveset.dps,
};

type RankedCounter = Counter & { rank: number };

function Raids({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const [boss, setBoss] = useState<SpeciesOption | null>(null);
  const [state, update] = useUrlState();
  const sort = state.sort ?? DEFAULT_SORT;
  const header = (label: string, sortKey: string, ascendingFirst = false) => (
    <SortHeader label={label} sortKey={sortKey} sort={sort} onSort={(value) => update({ sort: value === DEFAULT_SORT ? null : value })} ascendingFirst={ascendingFirst} />
  );
  const run = useMutation({
    mutationFn: (bossKey: string | null) =>
      api.post<{ method: ServerText; counters: Counter[]; boss: { name: string; types: string[] } | null; mode: string }>("/api/v1/battles/raid-counters", {
        account_id: accountId,
        boss_key: bossKey,
      }),
  });
  const { mutate } = run;
  useEffect(() => mutate(boss?.key ?? null), [boss, mutate]);
  const data = run.data;
  const counters = data ? sortRows<RankedCounter>(data.counters.map((c, index) => ({ ...c, rank: index + 1 })), sort, COLUMNS) : [];
  return (
    <>
      <PageHeader title={t("battles.raids.title")} description={t("battles.raids.description")} />
      <Card className="mb-5">
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-full max-w-md">
            <SpeciesPicker onPick={setBoss} placeholder={t("battles.raids.search")} />
          </div>
          {boss && (
            <>
              <span className="font-medium">{boss.name}</span>
              {boss.types.map((type) => (
                <TypeBadge key={type} type={type} />
              ))}
              <Button size="sm" variant="ghost" onClick={() => setBoss(null)}>
                {t("battles.raids.general")}
              </Button>
            </>
          )}
        </div>
      </Card>
      {run.isPending && <Spinner />}
      {run.error && <Alert tone="error">{errorMessage(run.error)}</Alert>}
      {data && (
        <Card title={data.boss ? t("battles.raids.countersAgainst", { name: data.boss.name }) : t("battles.raids.bestGeneral")}>
          <Alert tone="info">{serverText("battles", data.method)}</Alert>
          <p className="mt-2 text-xs text-muted">{t("battles.raids.intro", { count: data.counters.length })}</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm [&_td]:pr-3 [&_th]:pr-3">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-2">#</th>
                  <th>
                    {header(t("battles.raids.columns.pokemon"), "name", true)} · {header("CP", "cp")}
                  </th>
                  <th>{header(t("battles.raids.columns.dpsNow"), "dps")}</th>
                  <th>{t("battles.raids.columns.currentMoves")}</th>
                  <th>{header(t("battles.raids.columns.bestMoveset"), "best_dps")}</th>
                  <th>{t("battles.raids.columns.notes")}</th>
                </tr>
              </thead>
              <tbody>
                {counters.map((c) => (
                  <tr key={c.pokemon_id} className="border-t border-line align-top">
                    <td className="py-2 pr-2 text-muted">{c.rank}</td>
                    <td className="pr-3">
                      <Link to={`/pokemon/${c.pokemon_id}`} className="font-medium hover:text-oak-300">
                        {c.name}
                        {c.form_label ? ` (${c.form_label})` : ""}
                      </Link>
                      {c.shadow && (
                        <Badge className="ml-1" color="#a855f7">
                          {t("battles.shared.shadow")}
                        </Badge>
                      )}
                      <span className="block text-xs text-muted">
                        CP {num(c.cp, "?")} · L{level(c.level)}
                      </span>
                    </td>
                    <td className="pr-3 font-semibold tabular-nums">{num(c.current.dps)}</td>
                    <td className="pr-3 text-xs">
                      {c.current.fast} · {c.current.charged ?? t("battles.raids.fastOnly")}
                    </td>
                    <td className="pr-3 text-xs">
                      {c.best_moveset.needs_tm ? (
                        <>
                          {c.best_moveset.fast} · {c.best_moveset.charged} ({num(c.best_moveset.dps)} DPS)
                          {c.best_moveset.needs_elite_tm && <span className="block text-amber-300">{t("battles.raids.eliteTm")}</span>}
                        </>
                      ) : (
                        <span className="text-muted">{t("battles.raids.alreadyBest")}</span>
                      )}
                    </td>
                    <td className="text-xs">
                      {c.weak_to_boss && <Badge color="#f87171">{t("battles.raids.weakToBoss")}</Badge>}
                      {c.current.effectiveness > 1 && <Badge color="#34d399">{t("battles.raids.superEffective")}</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}

export function RaidPage() {
  return <RequireAccount>{(id) => <Raids accountId={id} />}</RequireAccount>;
}
