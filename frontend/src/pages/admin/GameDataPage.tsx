import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ParseKeys } from "i18next";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Alert, Badge, Button, Card, KeyValue, PageHeader, Spinner } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { api, errorMessage } from "../../lib/api";
import { bytes, date, dateTime, num } from "../../lib/format";
import { serverText, type ServerText } from "../../lib/serverText";
import type { GameDataStatus, GameDataVersion, RemoteCheck } from "../../lib/types";

const POLL_MS = 3000;
const UPLOAD_FIELDS = [
  { name: "pokeminers", label: "PokeMiners GAME_MASTER.json", required: true },
  { name: "pvpoke", label: "PvPoke gamemaster.json", required: false },
  { name: "rankings_great", label: "PvPoke rankings Great League", required: false },
  { name: "rankings_ultra", label: "PvPoke rankings Ultra League", required: false },
  { name: "rankings_master", label: "PvPoke rankings Master League", required: false },
] as const;

const statusText: Record<string, ParseKeys> = {
  active: "admin.gamedata.versionStatus.active",
  archived: "admin.gamedata.versionStatus.archived",
  ready: "admin.gamedata.versionStatus.ready",
  pruned: "admin.gamedata.versionStatus.pruned",
  failed: "admin.gamedata.versionStatus.failed",
};
const ACTIVATABLE = ["archived", "ready"];

interface Source {
  id: string;
  name: ServerText;
  url: string;
  license: ServerText;
  role: ServerText;
}

/** Validation errors one by one in the chosen language, joined like the server joins them. */
function errorsText(errors: ServerText[] | null | undefined, fallback: string): string {
  return errors?.length ? errors.map((e) => serverText("gamedata", e)).join("; ") : fallback;
}

const dateLabel: Record<string, ParseKeys> = {
  pokeminers: "admin.gamedata.summary.gameMasterDate",
  pvpoke: "admin.gamedata.summary.pvpokeDate",
};

/** A date of the data, or "onbekend" with the reason the server gives. */
function dataDate(value: string | null, reason: ServerText | null, unknown: string): string {
  if (value) return date(value);
  return reason ? `${unknown} (${serverText("gamedata", reason)})` : unknown;
}

export function Summary({ version }: { version: GameDataVersion }) {
  const { t } = useTranslation();
  const s = version.summary ?? {};
  const rankings = (s.rankings ?? {}) as Record<string, number | null>;
  const dates = (version.dates ?? []).flatMap((d): [string, string][] => {
    const label = dateLabel[d.source];
    return label ? [[t(label), dataDate(d.date, d.reason, t("common.unknown"))]] : [];
  });
  return (
    <KeyValue
      items={[
        [t("admin.gamedata.summary.version"), `#${version.id} (${version.origin === "upload" ? t("admin.gamedata.summary.originUpload") : t("admin.gamedata.summary.originDownload")})`],
        ...dates,
        [t("admin.gamedata.summary.activated"), dateTime(version.activated_at)],
        [t("admin.gamedata.summary.species"), num(s.species as number)],
        [t("admin.gamedata.summary.forms"), num(s.forms as number)],
        [t("admin.gamedata.summary.moves"), num(s.moves as number)],
        [t("admin.gamedata.summary.pvpokeForms"), num(s.pvpoke_mapped_forms as number)],
        [t("admin.gamedata.summary.rankings"), Object.entries(rankings).map(([league, count]) => `${league}: ${num(count)}`).join(" · ") || t("admin.gamedata.summary.noRankings")],
        [t("admin.gamedata.summary.maxLevel"), String(s.max_normal_level ?? t("common.unknown"))],
      ]}
    />
  );
}

/** The result of the last check, kept by the server, so it stays on the page (issue #28). */
export function LatestVersion({ check, active, owner }: { check: RemoteCheck | null; active: GameDataVersion | null; owner: boolean }) {
  const { t } = useTranslation();
  // Only the owner has the button to check.
  if (!check) return <p className="text-sm text-muted">{t(owner ? "admin.gamedata.latest.neverOwner" : "admin.gamedata.latest.never")}</p>;
  const latest = dataDate(check.latest.date, check.latest.reason, t("common.unknown"));
  // A version activated after the check, such as an upload, makes the result out of date.
  const stale = active?.activated_at != null && new Date(active.activated_at) > new Date(check.checked_at);
  const verdict = check.error
    ? { tone: "error" as const, text: t("admin.gamedata.latest.failed", { error: serverText("gamedata", check.error) }) }
    : stale
      ? { tone: "info" as const, text: t("admin.gamedata.latest.stale") }
      : check.repair_needed
        ? { tone: "warning" as const, text: t("admin.gamedata.repairNeeded") }
        : check.available
          ? { tone: "info" as const, text: t("admin.gamedata.available", { sources: (check.changed_sources ?? []).join(", ") || t("admin.gamedata.noActiveVersion") }) }
          : { tone: "success" as const, text: t("admin.gamedata.upToDate") };
  return (
    <div className="space-y-3 text-sm">
      <p>{t("admin.gamedata.latest.gameMaster", { date: latest, checked: dateTime(check.checked_at) })}</p>
      <Alert tone={verdict.tone}>{verdict.text}</Alert>
    </div>
  );
}

export function GameDataPage() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const [message, setMessage] = useState<{ tone: "success" | "error" | "warning" | "info"; text: string } | null>(null);
  const status = useQuery({
    queryKey: ["gamedata"],
    queryFn: () => api.get<GameDataStatus>("/api/v1/gamedata/status"),
    refetchInterval: (q) => (q.state.data?.update_pending ? POLL_MS : false),
  });
  const sources = useQuery({
    queryKey: ["gamedata-sources"],
    queryFn: () => api.get<Source[]>("/api/v1/gamedata/sources"),
  });
  const refresh = () => void client.invalidateQueries({ queryKey: ["gamedata"] });
  // The server keeps the result; the page shows it under "Nieuwste versie" (issue #28).
  const check = useMutation({
    mutationFn: () => api.post<RemoteCheck>("/api/v1/gamedata/check"),
    onSuccess: () => {
      setMessage(null);
      refresh();
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  const update = useMutation({
    mutationFn: () => api.post("/api/v1/gamedata/update"),
    onSuccess: () => {
      setMessage({ tone: "info", text: t("admin.gamedata.updateStarted") });
      refresh();
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  const activate = useMutation({
    mutationFn: (id: number) => api.post(`/api/v1/gamedata/versions/${id}/activate`),
    onSuccess: () => {
      setMessage({ tone: "success", text: t("admin.gamedata.versionActivated") });
      refresh();
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  const upload = useMutation({
    mutationFn: (form: FormData) =>
      api.upload<{ status: string; message: ServerText; warnings: ServerText[]; errors?: ServerText[] }>("/api/v1/gamedata/upload", form),
    onSuccess: (r) => {
      const text = [errorsText(r.errors, serverText("gamedata", r.message)), ...r.warnings.map((w) => serverText("gamedata", w))].join(" ");
      setMessage({ tone: r.status === "activated" ? "success" : r.status === "failed" ? "error" : "info", text });
      refresh();
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });

  const versionStatus = (code: string) => {
    const key = statusText[code];
    return key ? t(key) : code;
  };

  if (status.isLoading || !status.data) return <Spinner />;
  const s = status.data;
  return (
    <>
      <PageHeader
        title={t("admin.gamedata.title")}
        description={t("admin.gamedata.description")}
        actions={
          <>
            {owner && (
              <Button loading={check.isPending} onClick={() => check.mutate()}>
                {t("admin.gamedata.check")}
              </Button>
            )}
            {owner && (
              <Button variant="primary" loading={update.isPending || s.update_pending} onClick={() => update.mutate()}>
                {t("admin.gamedata.updateNow")}
              </Button>
            )}
          </>
        }
      />
      {message && (
        <div className="mb-4">
          <Alert tone={message.tone}>{message.text}</Alert>
        </div>
      )}
      {!s.active && (
        <div className="mb-4">
          <Alert tone="warning" title={t("admin.gamedata.noActiveTitle")}>
            {t("admin.gamedata.noActiveText")}
          </Alert>
        </div>
      )}
      {s.last_error && (
        <div className="mb-4">
          <Alert tone="error" title={t("admin.gamedata.lastErrorTitle")}>
            {t("admin.gamedata.lastErrorText", { error: errorsText(s.last_errors, s.last_error) })}
          </Alert>
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title={t("admin.gamedata.activeTitle")}>
          {s.active ? <Summary version={s.active} /> : <p className="text-sm text-muted">{t("admin.gamedata.noActive")}</p>}
          <p className="mt-3 text-xs text-muted">
            {t("admin.gamedata.autoUpdate", {
              state: s.auto_update
                ? t("admin.gamedata.autoUpdateOn", { count: s.interval_hours, hours: num(s.interval_hours) })
                : t("admin.gamedata.autoUpdateOff"),
              checked: dateTime(s.last_check?.at),
            })}
          </p>
        </Card>
        <Card title={t("admin.gamedata.latest.title")}>
          <LatestVersion check={s.remote_check} active={s.active} owner={owner} />
        </Card>
        <Card title={t("admin.gamedata.dependentTitle")}>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {s.dependent_analyses.map((a) => (
              <li key={a.code ?? a.text}>{serverText("gamedata", a)}</li>
            ))}
          </ul>
        </Card>
        <Card title={t("admin.gamedata.versionsTitle")}>
          <ul className="divide-y divide-line text-sm">
            {s.versions.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>
                  #{v.id} · {dateTime(v.created_at)} · <Badge color={v.status === "active" ? "#22c55e" : v.status === "failed" ? "#ef4444" : undefined}>{versionStatus(v.status)}</Badge>
                  {v.error && <span className="block text-xs text-red-300">{errorsText(v.errors, v.error)}</span>}
                </span>
                {owner && ACTIVATABLE.includes(v.status) && (
                  <Button size="sm" loading={activate.isPending} onClick={() => activate.mutate(v.id)}>
                    {t("admin.gamedata.activate")}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </Card>
        <Card title={t("admin.gamedata.sourcesTitle")}>
          <ul className="space-y-3 text-sm">
            {sources.data?.map((src) => (
              <li key={src.id}>
                <p className="font-medium">
                  {serverText("gamedata", src.name)} <span className="text-xs text-muted">({serverText("gamedata", src.role)})</span>
                </p>
                <p className="break-all text-xs text-muted">{src.url}</p>
                <p className="text-xs">{t("admin.gamedata.license", { license: serverText("gamedata", src.license) })}</p>
              </li>
            ))}
          </ul>
          {s.active && (
            <details className="mt-3 text-xs">
              <summary className="cursor-pointer text-muted">{t("admin.gamedata.checksums")}</summary>
              <ul className="mt-2 space-y-1">
                {s.active.sources.map((src) => (
                  <li key={src.id} className="break-all">
                    {src.id}: {src.sha256?.slice(0, 16)}… · {bytes(src.bytes ?? null)} · {t("admin.gamedata.retrieved", { date: dateTime(src.retrieved_at) })}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </Card>
        {owner && (
          <Card title={t("admin.gamedata.offlineTitle")} className="lg:col-span-2">
            <p className="mb-3 text-sm text-muted">{t("admin.gamedata.offlineText")}</p>
            <form
              className="grid gap-3 md:grid-cols-2"
              onSubmit={(e) => {
                e.preventDefault();
                upload.mutate(new FormData(e.currentTarget));
              }}
            >
              {UPLOAD_FIELDS.map((f) => (
                <label key={f.name} className="text-sm">
                  <span className="mb-1 block text-muted">
                    {f.label}
                    {f.required && ` (${t("admin.gamedata.required")})`}
                  </span>
                  <input type="file" name={f.name} accept=".json,application/json" required={f.required} className="text-xs" />
                </label>
              ))}
              <div className="md:col-span-2">
                <Button type="submit" variant="primary" loading={upload.isPending}>
                  {t("admin.gamedata.uploadSubmit")}
                </Button>
              </div>
            </form>
          </Card>
        )}
      </div>
    </>
  );
}
