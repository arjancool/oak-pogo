import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Alert, Badge, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { errorMessage } from "../../lib/api";
import { num } from "../../lib/format";
import { CupRules, useLeagues } from "./shared";

export function CupsPage() {
  const { t } = useTranslation();
  const leagues = useLeagues();
  const cups = (leagues.data ?? []).filter((l) => l.kind === "cup");
  return (
    <>
      <PageHeader title={t("battles.cups.title")} description={t("battles.cups.description")} />
      {leagues.isLoading && <Spinner />}
      {leagues.error && <Alert tone="error">{errorMessage(leagues.error)}</Alert>}
      {leagues.data && cups.length === 0 && <EmptyState title={t("battles.cups.emptyTitle")}>{t("battles.cups.emptyText")}</EmptyState>}
      <div className="grid gap-4 lg:grid-cols-2">
        {cups.map((cup) => (
          <Card
            key={cup.id}
            title={cup.name}
            actions={
              cup.ranked_species ? (
                <Badge color="#34d399">{t("battles.cups.ranked")}</Badge>
              ) : (
                <Badge color="#94a3b8" title={t("battles.cups.unrankedHint")}>
                  {t("battles.cups.unranked")}
                </Badge>
              )
            }
          >
            <CupRules info={cup} />
            <p className="mt-3 text-xs text-muted">
              {t("battles.cups.eligible", { species: num(cup.eligible_species) })}
              {cup.ranked_species ? ` ${t("battles.cups.rankedCount", { species: num(cup.ranked_species) })}` : ""}
            </p>
            <div className="mt-3 flex flex-wrap gap-3 text-sm">
              <Link to={`/battles/${cup.id}`} className="text-oak-400 underline">
                {t("battles.cups.yourPokemon")}
              </Link>
              <Link to={`/battles/team-builder?league=${cup.id}`} className="text-oak-400 underline">
                {t("battles.cups.suggestTeam")}
              </Link>
              {cup.link && (
                <a href={cup.link} target="_blank" rel="noreferrer noopener" className="text-muted underline">
                  {t("battles.cups.about")}
                </a>
              )}
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
