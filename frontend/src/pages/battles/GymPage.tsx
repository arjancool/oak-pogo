import { useQuery } from "@tanstack/react-query";
import type { ParseKeys, TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { PokemonSprite, ScoreMeter, TypeBadge } from "../../components/pokemon";
import { Alert, Badge, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { level, num } from "../../lib/format";
import { type ServerText, serverText } from "../../lib/serverText";

interface Defender {
  pokemon_id: number;
  name: string | null;
  form_label: string | null;
  species_id: number;
  shadow: boolean;
  cp: number | null;
  level: number | null;
  types: string[];
  hp: number;
  defense: number;
  bulk: number;
  value: number | null;
  fast_move: string | null;
  charged_moves: string[];
  reasons: ServerText[];
  confidence: "high" | "medium" | "low";
  same_species: number;
  in_gym: boolean | null;
}

interface GymOverview {
  defenders: Defender[];
  excluded: Partial<Record<"not_deployable" | "unknown_form" | "unknown_stats", number>>;
  reference: { name: string | null; level: number } | null;
  unknown_reason: ServerText | null;
  method: ServerText;
  notes: ServerText[];
  source: ServerText;
  game_data_version: number;
}

const confidenceLabels: Record<Defender["confidence"], ParseKeys> = {
  high: "battles.gyms.confidenceLevels.high",
  medium: "battles.gyms.confidenceLevels.medium",
  low: "battles.gyms.confidenceLevels.low",
};

function excludedText(excluded: GymOverview["excluded"], t: TFunction): string | null {
  const parts = [
    excluded.not_deployable ? t("battles.gyms.excluded.notDeployable", { number: num(excluded.not_deployable) }) : null,
    excluded.unknown_form ? t("battles.gyms.excluded.unknownForm", { count: excluded.unknown_form, number: num(excluded.unknown_form) }) : null,
    excluded.unknown_stats ? t("battles.gyms.excluded.unknownStats", { count: excluded.unknown_stats, number: num(excluded.unknown_stats) }) : null,
  ].filter(Boolean);
  return parts.length ? t("battles.gyms.excluded.text", { parts: parts.join(", ") }) : null;
}

function Gyms({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ["gym-defenders", accountId],
    queryFn: () => api.get<GymOverview>("/api/v1/battles/gym-defenders", { account_id: accountId }),
  });
  const data = query.data;
  const excluded = data ? excludedText(data.excluded, t) : null;
  return (
    <>
      <PageHeader title={t("battles.gyms.title")} description={t("battles.gyms.description")} />
      {query.isLoading && <Spinner />}
      {query.error && <Alert tone="error">{errorMessage(query.error)}</Alert>}
      {data?.unknown_reason && <Alert tone="warning">{serverText("battles", data.unknown_reason)}</Alert>}
      {data && !data.unknown_reason && (
        <>
          <Card className="mb-5">
            <details>
              <summary className="cursor-pointer text-sm font-medium">{t("battles.gyms.howCalculated")}</summary>
              <p className="mt-2 text-sm text-muted">{serverText("battles", data.method)}</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted">
                {data.notes.map((note) => (
                  <li key={note.code ?? note.text}>{serverText("battles", note)}</li>
                ))}
              </ul>
            </details>
            <p className="mt-3 text-xs text-muted">
              {t("battles.gyms.source", { source: serverText("battles", data.source), version: data.game_data_version })}
              {excluded ? ` ${excluded}` : ""}
            </p>
          </Card>
          {data.defenders.length === 0 ? (
            <EmptyState title={t("battles.gyms.emptyTitle")}>{t("battles.gyms.emptyText")}</EmptyState>
          ) : (
            <Card title={t("battles.gyms.strongest", { count: data.defenders.length })}>
              <ol className="divide-y divide-line">
                {data.defenders.map((d, index) => (
                  <li key={d.pokemon_id} className="flex flex-wrap items-start gap-3 py-3">
                    <span className="w-6 pt-2 text-right text-sm text-muted">{index + 1}</span>
                    <PokemonSprite dex={d.species_id} types={d.types} size={40} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link to={`/pokemon/${d.pokemon_id}`} className="font-medium hover:text-oak-300">
                          {d.name}
                          {d.form_label ? ` (${d.form_label})` : ""}
                        </Link>
                        {d.types.map((type) => (
                          <TypeBadge key={type} type={type} />
                        ))}
                        {d.shadow && <Badge color="#a855f7">{t("battles.shared.shadow")}</Badge>}
                        {d.in_gym && <Badge color="#38bdf8">{t("battles.gyms.inGym")}</Badge>}
                        <ScoreMeter label={t("battles.gyms.value")} value={d.value} />
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        CP {num(d.cp, "?")} · L{level(d.level)}
                        {d.fast_move ? ` · ${[d.fast_move, ...d.charged_moves].join(", ")}` : ""}
                        {d.same_species > 0 ? ` · ${t("battles.gyms.sameSpecies", { number: num(d.same_species) })}` : ""}
                      </p>
                      <ul className="mt-1 space-y-0.5 text-xs text-muted">
                        {d.reasons.map((reason) => (
                          <li key={reason.code ?? reason.text}>{serverText("battles", reason)}</li>
                        ))}
                        <li>{t("battles.gyms.confidence", { level: t(confidenceLabels[d.confidence]) })}</li>
                      </ul>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          )}
        </>
      )}
    </>
  );
}

export function GymPage() {
  return <RequireAccount>{(id) => <Gyms accountId={id} />}</RequireAccount>;
}
