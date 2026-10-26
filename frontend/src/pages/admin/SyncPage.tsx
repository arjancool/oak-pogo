import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, UploadCloud } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { Alert, Badge, Button, Card, Dialog, EmptyState, KeyValue, PageHeader, Pagination, Spinner, Switch } from "../../components/ui";
import { useAccount } from "../../lib/account";
import { api, errorMessage, uploadWithProgress } from "../../lib/api";
import { bytes, dateTime, num, relative } from "../../lib/format";
import { classificationLabels, importStatusLabels, label } from "../../lib/i18n";
import type { ImportIssue, ImportJob, Paged, SyncStatus } from "../../lib/types";

const POLL_MS = 2000;
const PAGE_SIZE = 20;
const PERCENT = 100;

const statusColors: Record<string, string> = {
  succeeded: "#22c55e",
  partial: "#f59e0b",
  failed: "#ef4444",
  rejected: "#ef4444",
  duplicate: "#94a3b8",
  processing: "#38bdf8",
  queued: "#38bdf8",
  received: "#38bdf8",
};

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <Button
      size="sm"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), POLL_MS);
        });
      }}
    >
      {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? t("admin.sync.copied") : t("admin.sync.copy")}
    </Button>
  );
}

function WebhookCard({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const { account } = useAccount();
  const [created, setCreated] = useState<{ url: string; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["accounts"] });
    void client.invalidateQueries({ queryKey: ["sync-status"] });
  };
  const generate = useMutation({
    mutationFn: () => api.post<{ url: string; message: string }>(`/api/v1/accounts/${accountId}/webhook`),
    onSuccess: (data) => {
      setCreated(data);
      refresh();
    },
    onError: (err) => setError(errorMessage(err)),
  });
  const revoke = useMutation({ mutationFn: () => api.delete(`/api/v1/accounts/${accountId}/webhook`), onSuccess: refresh, onError: (err) => setError(errorMessage(err)) });
  const diagnostics = useMutation({
    mutationFn: (enabled: boolean) => api.put(`/api/v1/accounts/${accountId}/diagnostics`, { enabled }),
    onSuccess: refresh,
  });
  const webhook = account?.webhook;
  const diagActive = account?.diagnostics_until ? new Date(account.diagnostics_until) > new Date() : false;
  return (
    <Card title={t("admin.sync.webhook.title")}>
      {webhook?.active ? (
        <>
          <p className="mb-1 text-xs text-muted">{t("admin.sync.webhook.urlLabel")}</p>
          <code className="mb-3 block break-all rounded bg-surface-3 px-2 py-1.5 text-xs">{webhook.url_masked}</code>
          <KeyValue
            items={[
            [t("admin.sync.webhook.created"), dateTime(webhook.created_at)],
            [t("admin.sync.webhook.lastUsed"), webhook.last_used_at ? `${dateTime(webhook.last_used_at)} (${relative(webhook.last_used_at)})` : t("admin.sync.webhook.neverUsed")],
            ]}
          />
        </>
      ) : (
        <p className="text-sm text-muted">{t("admin.sync.webhook.none")}</p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant="primary"
          loading={generate.isPending}
          onClick={() => {
            if (!webhook?.active || window.confirm(t("admin.sync.webhook.regenerateConfirm"))) generate.mutate();
          }}
        >
          {webhook?.active ? t("admin.sync.webhook.regenerate") : t("admin.sync.webhook.create")}
        </Button>
        {webhook?.active && (
          <Button
            variant="danger"
            onClick={() => {
              if (window.confirm(t("admin.sync.webhook.revokeConfirm"))) revoke.mutate();
            }}
          >
            {t("admin.sync.webhook.revoke")}
          </Button>
        )}
      </div>
      {error && (
        <div className="mt-3">
          <Alert tone="error">{error}</Alert>
        </div>
      )}
      <div className="mt-5 border-t border-line pt-4">
        <Switch
          checked={diagActive}
          onChange={(value) => diagnostics.mutate(value)}
          label={t("admin.sync.diagnostics.label")}
          description={
            diagActive
              ? t("admin.sync.diagnostics.active", { date: dateTime(account?.diagnostics_until) })
              : t("admin.sync.diagnostics.inactive")
          }
        />
      </div>
      <Dialog
        open={created !== null}
        onClose={() => setCreated(null)}
        title={t("admin.sync.webhook.dialogTitle")}
        footer={<Button onClick={() => setCreated(null)}>{t("admin.sync.webhook.stored")}</Button>}
        wide
      >
        <Alert tone="warning">{created?.message}</Alert>
        <div className="mt-3 flex items-center gap-2 rounded-lg bg-surface-3 p-3">
          <code className="flex-1 break-all text-xs">{created?.url}</code>
          {created && <CopyButton text={created.url} />}
        </div>
        <p className="mt-3 text-sm text-muted">{t("admin.sync.webhook.secret")}</p>
      </Dialog>
    </Card>
  );
}

function SetupSteps() {
  const { t } = useTranslation();
  return (
    <Card title={t("admin.sync.setup.title")}>
      <ol className="list-decimal space-y-2 pl-5 text-sm">
        <li>{t("admin.sync.setup.step1")}</li>
        <li>{t("admin.sync.setup.step2")}</li>
        <li>{t("admin.sync.setup.step3")}</li>
        <li>{t("admin.sync.setup.step4")}</li>
        <li>{t("admin.sync.setup.step5")}</li>
      </ol>
      <p className="mt-3 text-xs text-muted">{t("admin.sync.setup.note")}</p>
    </Card>
  );
}

function UploadCard({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const abort = useRef<AbortController | null>(null);

  const send = async (file: File) => {
    if (abort.current) return;
    const form = new FormData();
    form.append("file", file);
    form.append("account_id", String(accountId));
    setResult(null);
    setProgress(0);
    const controller = new AbortController();
    abort.current = controller;
    try {
      const job = await uploadWithProgress<ImportJob>("/api/v1/imports/upload", form, setProgress, { signal: controller.signal });
      setResult({
        tone: "success",
        text: job.status === "duplicate" ? t("admin.sync.upload.duplicate") : t("admin.sync.upload.received"),
      });
      void client.invalidateQueries({ queryKey: ["imports"] });
      void client.invalidateQueries({ queryKey: ["sync-status"] });
    } catch (err) {
      setResult({ tone: "error", text: errorMessage(err) });
    } finally {
      abort.current = null;
      setProgress(null);
    }
  };
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) void send(file);
  };
  return (
    <Card title={t("admin.sync.upload.title")}>
      <div
        role="button"
        tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") input.current?.click();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center text-sm ${dragging ? "border-oak-400 bg-oak-500/10" : "border-line"}`}
      >
        <UploadCloud className="text-muted" />
        <span>{t("admin.sync.upload.drop")}</span>
        <span className="text-xs text-muted">{t("admin.sync.upload.samePipeline")}</span>
        <input
          ref={input}
          type="file"
          accept=".json,application/json"
          className="hidden"
          data-testid="upload-input"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void send(file);
            e.target.value = "";
          }}
        />
      </div>
      {progress !== null && (
        <div className="mt-3 flex items-center gap-3">
          <div
            className="h-2 flex-1 overflow-hidden rounded bg-surface-3"
            role="progressbar"
            aria-label={t("admin.sync.upload.progress")}
            aria-valuemin={0}
            aria-valuemax={PERCENT}
            aria-valuenow={Math.round(progress * PERCENT)}
          >
            <div className="h-full bg-oak-500 transition-all" style={{ width: `${Math.round(progress * PERCENT)}%` }} />
          </div>
          <Button size="sm" variant="ghost" onClick={() => abort.current?.abort()}>
            {t("common.cancel")}
          </Button>
        </div>
      )}
      {result && (
        <div className="mt-3">
          <Alert tone={result.tone}>{result.text}</Alert>
        </div>
      )}
    </Card>
  );
}

function SchemaSummary({ summary }: { summary: Record<string, unknown> }) {
  const { t } = useTranslation();
  const list = (key: string) => (Array.isArray(summary[key]) ? (summary[key] as string[]) : []);
  const counts = (summary.counts ?? {}) as Record<string, number | null>;
  const paths = (summary.paths ?? {}) as Record<string, string[]>;
  return (
    <div className="space-y-3 text-sm">
      <KeyValue
        items={[
          [t("admin.sync.schema.rootType"), String(summary.root_type ?? t("common.unknown"))],
          [t("admin.sync.schema.pokemonRecords"), num(counts.pokemons ?? null)],
          [t("admin.sync.schema.itemRecords"), num(counts.items ?? null)],
          [t("admin.sync.schema.newRootKeys"), list("root_keys_new").join(", ") || t("admin.sync.schema.none")],
          [t("admin.sync.schema.newPokemonKeys"), list("pokemon_keys_new").join(", ") || t("admin.sync.schema.none")],
          [t("admin.sync.schema.missingPokemonKeys"), list("pokemon_keys_missing").join(", ") || t("admin.sync.schema.none")],
        ]}
      />
      {Object.keys(paths).length > 0 && (
        <details>
          <summary className="cursor-pointer text-muted">{t("admin.sync.schema.allPaths", { total: num(Object.keys(paths).length) })}</summary>
          <pre className="mt-2 max-h-72 overflow-auto rounded bg-surface-3 p-2 text-xs">
            {Object.entries(paths)
              .map(([path, types]) => `${path}: ${types.join(" | ")}`)
              .join("\n")}
          </pre>
        </details>
      )}
    </div>
  );
}

function ImportDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const job = useQuery({ queryKey: ["import", id], queryFn: () => api.get<ImportJob>(`/api/v1/imports/${id}`) });
  const issues = useQuery({ queryKey: ["import-errors", id], queryFn: () => api.get<ImportIssue[]>(`/api/v1/imports/${id}/errors`) });
  const after = () => {
    void client.invalidateQueries({ queryKey: ["imports"] });
    void client.invalidateQueries({ queryKey: ["sync-status"] });
    onClose();
  };
  const retry = useMutation({ mutationFn: () => api.post(`/api/v1/imports/${id}/retry`), onSuccess: after, onError: (err) => setError(errorMessage(err)) });
  const confirmFull = useMutation({ mutationFn: () => api.post(`/api/v1/imports/${id}/confirm-full`), onSuccess: after, onError: (err) => setError(errorMessage(err)) });
  const j = job.data;
  return (
    <Dialog open onClose={onClose} title={`Import #${id}`} wide>
      {!j ? (
        <Spinner />
      ) : (
        <div className="space-y-4">
          <KeyValue
            items={[
              [t("admin.sync.detail.status"), label(importStatusLabels, j.status)],
              [t("admin.sync.detail.classification"), j.classification ? label(classificationLabels, j.classification) : t("admin.sync.detail.notClassified")],
              [
                t("admin.sync.detail.source"),
                j.source === "webhook"
                  ? t("admin.sync.detail.sourceWebhook")
                  : j.source === "upload"
                    ? `${t("admin.sync.detail.sourceUpload")}${j.filename ? ` (${j.filename})` : ""}`
                    : t("admin.sync.detail.sourceReprocessed"),
              ],
              [t("admin.sync.detail.received"), dateTime(j.received_at)],
              [t("admin.sync.detail.exportTime"), dateTime(j.export_time)],
              [t("admin.sync.detail.size"), bytes(j.payload_size)],
              [t("admin.sync.detail.payloadStored"), j.payload_available ? t("admin.sync.detail.yes") : t("admin.sync.detail.no")],
              ...(j.error_message ? ([[t("admin.sync.detail.message"), j.error_message]] as [string, string][]) : []),
            ]}
          />
          {j.sync_run && (
            <Card title={t("admin.sync.result.title")}>
              <KeyValue
                items={[
                  [t("admin.sync.result.total"), num(j.sync_run.total_pokemon)],
                  [t("admin.sync.result.eggs"), num(j.sync_run.eggs)],
                  [t("admin.sync.result.new"), num(j.sync_run.new_count)],
                  [t("admin.sync.result.changed"), num(j.sync_run.changed_count)],
                  [t("admin.sync.result.unchanged"), num(j.sync_run.unchanged_count)],
                  [t("admin.sync.result.missing"), num(j.sync_run.missing_count)],
                  [t("admin.sync.result.missingUnconfirmed"), num(j.sync_run.missing_unconfirmed_count)],
                  [t("admin.sync.result.reappeared"), num(j.sync_run.reappeared_count)],
                ]}
              />
              {j.sync_run.warnings.map((w) => (
                <div key={w.code} className="mt-2">
                  <Alert tone="warning">{w.message}</Alert>
                </div>
              ))}
            </Card>
          )}
          {j.confirmable && (
            <Alert tone="info" title={t("admin.sync.confirmFull.title")}>
              {t("admin.sync.confirmFull.text")}
              <div className="mt-2">
                <Button
                  size="sm"
                  loading={confirmFull.isPending}
                  onClick={() => {
                    if (window.confirm(t("admin.sync.confirmFull.confirm"))) confirmFull.mutate();
                  }}
                >
                  {t("admin.sync.confirmFull.button")}
                </Button>
              </div>
            </Alert>
          )}
          {["failed", "rejected", "partial"].includes(j.status) && j.payload_available && (
            <Button loading={retry.isPending} onClick={() => retry.mutate()}>
              {t("admin.sync.detail.retry")}
            </Button>
          )}
          {error && <Alert tone="error">{error}</Alert>}
          {issues.data && issues.data.length > 0 && (
            <Card title={t("admin.sync.issues.title", { total: num(issues.data.length) })}>
              <ul className="max-h-64 space-y-1 overflow-auto text-xs">
                {issues.data.map((i) => (
                  <li key={i.id} className="flex gap-2">
                    <Badge color={i.severity === "error" ? "#ef4444" : "#f59e0b"}>{i.severity === "error" ? t("admin.sync.issues.error") : t("admin.sync.issues.warning")}</Badge>
                    <span>
                      {i.message}
                      {i.path && <span className="text-muted"> · {i.path}</span>}
                      {i.source_pokemon_id && <span className="text-muted"> · Pokémon {i.source_pokemon_id}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {j.schema_summary && (
            <Card title={t("admin.sync.schema.title")}>
              <SchemaSummary summary={j.schema_summary} />
            </Card>
          )}
        </div>
      )}
    </Dialog>
  );
}

function ImportList({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const query = useQuery({
    queryKey: ["imports", accountId, page],
    queryFn: () => api.get<Paged<ImportJob>>("/api/v1/imports", { account_id: accountId, page, page_size: PAGE_SIZE }),
    refetchInterval: (q) => (q.state.data?.items.some((j) => ["received", "queued", "processing"].includes(j.status)) ? POLL_MS : false),
  });
  if (query.isLoading) return <Spinner />;
  const items = query.data?.items ?? [];
  return (
    <Card title={t("admin.sync.list.title")}>
      {items.length === 0 ? (
        <EmptyState title={t("admin.sync.list.emptyTitle")}>{t("admin.sync.list.emptyText")}</EmptyState>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-1">{t("admin.sync.list.received")}</th>
                <th>{t("admin.sync.list.source")}</th>
                <th>{t("admin.sync.list.status")}</th>
                <th>{t("admin.sync.list.pokemon")}</th>
                <th>{t("admin.sync.list.new")}</th>
                <th>{t("admin.sync.list.changed")}</th>
                <th>{t("admin.sync.list.gone")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((j) => (
                <tr key={j.id} className="border-t border-line">
                  <td className="py-1.5">{dateTime(j.received_at)}</td>
                  <td>
                    {j.source === "webhook"
                      ? t("admin.sync.list.sourceWebhook")
                      : j.source === "upload"
                        ? t("admin.sync.list.sourceUpload")
                        : t("admin.sync.list.sourceReprocessed")}
                  </td>
                  <td>
                    <Badge color={statusColors[j.status]}>{label(importStatusLabels, j.status)}</Badge>
                    {["queued", "processing"].includes(j.status) && <span className="ml-2 text-xs text-muted">{Math.round(j.progress * PERCENT)}%</span>}
                  </td>
                  <td className="tabular-nums">{num(j.sync_run?.total_pokemon ?? null, "–")}</td>
                  <td className="tabular-nums">{num(j.sync_run?.new_count ?? null, "–")}</td>
                  <td className="tabular-nums">{num(j.sync_run?.changed_count ?? null, "–")}</td>
                  <td className="tabular-nums">{num(j.sync_run?.missing_count ?? null, "–")}</td>
                  <td className="text-right">
                    <Button size="sm" onClick={() => setOpen(j.id)}>
                      {t("admin.sync.list.details")}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {query.data && <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onPage={setPage} />}
      {open !== null && <ImportDetail id={open} onClose={() => setOpen(null)} />}
    </Card>
  );
}

function SyncView({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const status = useQuery({
    queryKey: ["sync-status", accountId],
    queryFn: () => api.get<SyncStatus>("/api/v1/sync/status", { account_id: accountId }),
    refetchInterval: (q) => (q.state.data?.pending_imports ? POLL_MS : false),
  });
  const tone = status.data?.state === "error" ? "error" : status.data?.state === "warning" ? "warning" : status.data?.state === "connected" ? "success" : "info";
  return (
    <>
      <PageHeader title={t("admin.sync.title")} description={t("admin.sync.description")} />
      {status.data && (
        <div className="mb-5">
          <Alert tone={tone} title={status.data.message}>
            {t("admin.sync.lastSync", { date: dateTime(status.data.last_successful_sync_at) })}
            {status.data.pending_imports > 0 &&
              ` · ${t("admin.sync.pending", { count: status.data.pending_imports, imports: num(status.data.pending_imports) })}`}
          </Alert>
        </div>
      )}
      <div className="mb-5 grid gap-5 lg:grid-cols-2">
        <WebhookCard accountId={accountId} />
        <div className="space-y-5">
          <SetupSteps />
          <UploadCard accountId={accountId} />
        </div>
      </div>
      <ImportList accountId={accountId} />
    </>
  );
}

export function SyncPage() {
  return <RequireAccount>{(id) => <SyncView accountId={id} />}</RequireAccount>;
}
