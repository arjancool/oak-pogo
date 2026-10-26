import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ParseKeys } from "i18next";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Alert, Badge, Button, Card, KeyValue, PageHeader, Spinner } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { api, errorMessage } from "../../lib/api";
import { bytes, dateTime, num } from "../../lib/format";
import { serverText, type ServerText } from "../../lib/serverText";
import type { GameDataStatus, GameDataVersion } from "../../lib/types";

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

function Summary({ version }: { version: GameDataVersion }) {
  const { t } = useTranslation();
  const s = version.summary ?? {};
  const rankings = (s.rankings ?? {}) as Record<string, number | null>;
  return (
    <KeyValue
      items={[
        [t("admin.gamedata.summary.version"), `#${version.id} (${version.origin === "upload" ? t("admin.gamedata.summary.originUpload") : t("admin.gamedata.summary.originDownload")})`],
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
  const check = useMutation({
    mutationFn: () =>
      api.get<{ available: boolean | null; changed_sources?: string[]; repair_needed?: boolean; error: ServerText | null }>("/api/v1/gamedata/check"),
    onSuccess: (r) =>
      setMessage(
        r.error
          ? { tone: "error", text: serverText("gamedata", r.error) }
          : r.repair_needed
            ? { tone: "warning", text: t("admin.gamedata.repairNeeded") }
            : r.available
            ? { tone: "info", text: t("admin.gamedata.available", { sources: (r.changed_sources ?? []).join(", ") || t("admin.gamedata.noActiveVersion") }) }
            : { tone: "success", text: t("admin.gamedata.upToDate") },
      ),
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
            <Button loading={check.isPending} onClick={() => check.mutate()}>
              {t("admin.gamedata.check")}
            </Button>
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
