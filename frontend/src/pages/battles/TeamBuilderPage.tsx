import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ParseKeys } from "i18next";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { ReadinessBadge, TypeBadge } from "../../components/pokemon";
import { Alert, Button, Card, Field, Input, PageHeader, Select, Spinner } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { num } from "../../lib/format";
import { typeNames } from "../../lib/i18n";
import { type ServerText, serverText } from "../../lib/serverText";
import { useLeagues } from "./shared";

interface Member {
  role: string;
  pokemon_id: number;
  name: string | null;
  target: string;
  is_evolution: boolean;
  cp: number | null;
  best_cp: number;
  iv_rank: number;
  species_rank: number | null;
  readiness: string;
  stardust: number | null;
  candy: number | null;
  xl_candy: number | null;
  moveset_quality: string;
  recommended_moveset: string[];
  types: string[];
}
interface Variant {
  mode: string;
  label: ServerText;
  team: Member[] | null;
  message?: ServerText;
  score?: number;
  investment?: { stardust: number };
  shared_weaknesses?: string[];
  move_type_coverage?: string[];
}
interface SavedTeam {
  id: number;
  name: string;
  league: string | null;
  members: { position: number; role: string | null; pokemon_id: number; name: string | null; cp: number | null; in_inventory: boolean }[];
}

const roleLabels: Record<string, ParseKeys> = {
  lead: "battles.teamBuilder.roles.lead",
  switch: "battles.teamBuilder.roles.switch",
  closer: "battles.teamBuilder.roles.closer",
};

function TeamBuilder({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const roleLabel = (role: string) => {
    const key = roleLabels[role];
    return key ? t(key) : role;
  };
  const client = useQueryClient();
  const [params] = useSearchParams();
  const [league, setLeague] = useState(params.get("league") ?? "great");
  const leagues = useLeagues();
  const leagueName = (id: string | null) => leagues.data?.find((l) => l.id === id)?.name ?? id ?? "";
  const [budget, setBudget] = useState(100_000);
  const [message, setMessage] = useState<string | null>(null);
  const build = useMutation({
    mutationFn: () => api.post<{ method: ServerText; variants: Variant[] }>("/api/v1/battles/team-builder", { account_id: accountId, league, stardust_budget: budget }),
  });
  const teams = useQuery({ queryKey: ["teams", accountId], queryFn: () => api.get<SavedTeam[]>("/api/v1/battles/teams", { account_id: accountId }) });
  const save = useMutation({
    mutationFn: (variant: Variant) =>
      api.post("/api/v1/battles/teams", {
        account_id: accountId,
        name: `${leagueName(league)} – ${serverText("battles", variant.label)}`,
        kind: "pvp",
        league,
        members: variant.team?.map((m) => ({ pokemon_id: m.pokemon_id, role: m.role })) ?? [],
      }),
    onSuccess: () => {
      setMessage(t("battles.teamBuilder.saved"));
      void client.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (error) => setMessage(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/v1/battles/teams/${id}`, undefined, { account_id: accountId }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["teams"] }),
  });
  return (
    <>
      <PageHeader title={t("battles.teamBuilder.title")} description={t("battles.teamBuilder.description")} />
      <Card className="mb-5">
        <div className="flex flex-wrap items-end gap-3">
          <Field label={t("battles.teamBuilder.league")}>
            <Select value={league} onChange={(e) => setLeague(e.target.value)}>
              {(["league", "cup"] as const).map((kind) => (
                <optgroup key={kind} label={kind === "league" ? t("battles.teamBuilder.leagues") : t("battles.teamBuilder.cups")}>
                  {(leagues.data ?? []).filter((l) => l.kind === kind).map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </optgroup>
              ))}
              {!leagues.data && <option value={league}>{league}</option>}
            </Select>
          </Field>
          <Field label={t("battles.teamBuilder.budget")}>
            <Input type="number" min={0} step={10000} value={budget} onChange={(e) => setBudget(Number(e.target.value))} className="w-48" />
          </Field>
          <Button variant="primary" loading={build.isPending} onClick={() => build.mutate()}>
            {t("battles.teamBuilder.suggest")}
          </Button>
        </div>
      </Card>
      {build.error && <Alert tone="error">{errorMessage(build.error)}</Alert>}
      {message && <Alert tone="success">{message}</Alert>}
      {build.data && (
        <>
          <Alert tone="info">{serverText("battles", build.data.method)}</Alert>
          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            {build.data.variants.map((variant) => (
              <Card
                key={variant.mode}
                title={serverText("battles", variant.label)}
                actions={
                  variant.team && (
                    <Button size="sm" onClick={() => save.mutate(variant)}>
                      {t("battles.teamBuilder.save")}
                    </Button>
                  )
                }
              >
                {!variant.team ? (
                  <p className="text-sm text-muted">{serverText("battles", variant.message)}</p>
                ) : (
                  <>
                    <ol className="space-y-3">
                      {variant.team.map((m) => (
                        <li key={m.pokemon_id} className="rounded-lg border border-line p-3">
                          <p className="text-xs uppercase tracking-wide text-muted">{roleLabel(m.role)}</p>
                          <Link to={`/pokemon/${m.pokemon_id}`} className="font-medium hover:text-oak-300">
                            {m.name} {m.is_evolution && `→ ${m.target}`}
                          </Link>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {m.types.map((type) => (
                              <TypeBadge key={type} type={type} />
                            ))}
                            <ReadinessBadge readiness={m.readiness} />
                          </div>
                          <p className="mt-1 text-xs text-muted">
                            {t("battles.teamBuilder.memberStats", {
                              cp: num(m.cp, "?"),
                              bestCp: num(m.best_cp),
                              ivRank: m.iv_rank,
                              speciesRank: m.species_rank ?? "–",
                            })}
                          </p>
                          <p className="text-xs text-muted">
                            {t("battles.teamBuilder.moves", { moves: m.recommended_moveset.join(" · ") || t("common.unknown") })}
                          </p>
                        </li>
                      ))}
                    </ol>
                    <p className="mt-3 text-xs text-muted">
                      {t("battles.teamBuilder.summary", {
                        stardust: num(variant.investment?.stardust ?? 0),
                        weaknesses: variant.shared_weaknesses?.length
                          ? variant.shared_weaknesses.map((type) => typeNames[type] ?? type).join(", ")
                          : t("battles.teamBuilder.noWeaknesses"),
                      })}
                    </p>
                  </>
                )}
              </Card>
            ))}
          </div>
        </>
      )}
      <Card className="mt-5" title={t("battles.teamBuilder.savedTeams")}>
        {teams.isLoading ? (
          <Spinner />
        ) : !teams.data?.length ? (
          <p className="text-sm text-muted">{t("battles.teamBuilder.noTeams")}</p>
        ) : (
          <ul className="divide-y divide-line">
            {teams.data.map((team) => (
              <li key={team.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <span>
                  <span className="font-medium">{team.name}</span>
                  <span className="ml-2 text-muted">
                    {team.members.map((m) => (m.in_inventory ? `${m.name}` : t("battles.teamBuilder.gone", { name: m.name }))).join(" · ")}
                  </span>
                </span>
                <Button size="sm" variant="ghost" onClick={() => remove.mutate(team.id)}>
                  {t("battles.teamBuilder.delete")}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

export function TeamBuilderPage() {
  return <RequireAccount>{(id) => <TeamBuilder accountId={id} />}</RequireAccount>;
}
