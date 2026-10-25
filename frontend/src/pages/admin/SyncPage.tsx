import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, UploadCloud } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

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
      {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Gekopieerd" : "Kopiëren"}
    </Button>
  );
}

function WebhookCard({ accountId }: { accountId: number }) {
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
    <Card title="PGSharp-webhook">
      {webhook?.active ? (
        <>
          <p className="mb-1 text-xs text-muted">Webhook-URL (het geheime deel wordt nooit opnieuw getoond)</p>
          <code className="mb-3 block break-all rounded bg-surface-3 px-2 py-1.5 text-xs">{webhook.url_masked}</code>
          <KeyValue
            items={[
            ["Aangemaakt", dateTime(webhook.created_at)],
            ["Laatst gebruikt", webhook.last_used_at ? `${dateTime(webhook.last_used_at)} (${relative(webhook.last_used_at)})` : "nog nooit"],
            ]}
          />
        </>
      ) : (
        <p className="text-sm text-muted">Er is nog geen actieve webhook voor dit account.</p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant="primary"
          loading={generate.isPending}
          onClick={() => {
            if (!webhook?.active || window.confirm("Een nieuwe URL maakt de huidige ongeldig. PGSharp moet daarna de nieuwe URL krijgen. Doorgaan?")) generate.mutate();
          }}
        >
          {webhook?.active ? "Nieuwe URL maken" : "Webhook-URL maken"}
        </Button>
        {webhook?.active && (
          <Button
            variant="danger"
            onClick={() => {
              if (window.confirm("Webhook intrekken? PGSharp kan daarna niets meer naar dit account sturen.")) revoke.mutate();
            }}
          >
            Intrekken
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
          label="Diagnosemodus (24 uur)"
          description={
            diagActive
              ? `Actief tot ${dateTime(account?.diagnostics_until)}. OAK bewaart van elke binnenkomende export de volledige structuur, zonder waarden.`
              : "Handig als een import mislukt. OAK legt dan de veldnamen en typen van iedere export vast, nooit de inhoud."
          }
        />
      </div>
      <Dialog
        open={created !== null}
        onClose={() => setCreated(null)}
        title="Je nieuwe webhook-URL"
        footer={<Button onClick={() => setCreated(null)}>Ik heb hem opgeslagen</Button>}
        wide
      >
        <Alert tone="warning">{created?.message}</Alert>
        <div className="mt-3 flex items-center gap-2 rounded-lg bg-surface-3 p-3">
          <code className="flex-1 break-all text-xs">{created?.url}</code>
          {created && <CopyButton text={created.url} />}
        </div>
        <p className="mt-3 text-sm text-muted">De URL werkt als een wachtwoord. Deel hem niet en zet hem niet in screenshots.</p>
      </Dialog>
    </Card>
  );
}

function SetupSteps() {
  return (
    <Card title="PGSharp instellen">
      <ol className="list-decimal space-y-2 pl-5 text-sm">
        <li>Maak hiernaast een webhook-URL en kopieer hem.</li>
        <li>Open in PGSharp de instellingen en zoek de optie om accountgegevens te exporteren.</li>
        <li>Plak de URL bij de webhook voor Export Account Data.</li>
        <li>Start een export. Na een paar seconden verschijnt de import hieronder.</li>
        <li>Lukt de webhook niet, exporteer dan het bestand PGSStats.json en upload het hier.</li>
      </ol>
      <p className="mt-3 text-xs text-muted">
        De exacte namen van de menu-opties in PGSharp kunnen per versie verschillen. OAK vraagt nooit om je Pokémon GO-inloggegevens.
      </p>
    </Card>
  );
}

function UploadCard({ accountId }: { accountId: number }) {
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
        text: job.status === "duplicate" ? "Deze export was al eerder ontvangen. Er is niets veranderd." : "Upload ontvangen. De verwerking loopt op de achtergrond.",
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
    <Card title="Handmatige upload">
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
        <span>Sleep PGSStats.json hierheen of klik om een bestand te kiezen</span>
        <span className="text-xs text-muted">Het bestand doorloopt dezelfde verwerking als de webhook.</span>
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
            aria-label="Uploadvoortgang"
            aria-valuemin={0}
            aria-valuemax={PERCENT}
            aria-valuenow={Math.round(progress * PERCENT)}
          >
            <div className="h-full bg-oak-500 transition-all" style={{ width: `${Math.round(progress * PERCENT)}%` }} />
          </div>
          <Button size="sm" variant="ghost" onClick={() => abort.current?.abort()}>
            Annuleren
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
  const list = (key: string) => (Array.isArray(summary[key]) ? (summary[key] as string[]) : []);
  const counts = (summary.counts ?? {}) as Record<string, number | null>;
  const paths = (summary.paths ?? {}) as Record<string, string[]>;
  return (
    <div className="space-y-3 text-sm">
      <KeyValue
        items={[
          ["Type van de hoofdstructuur", String(summary.root_type ?? "onbekend")],
          ["Pokémon-records", num(counts.pokemons ?? null)],
          ["Item-records", num(counts.items ?? null)],
          ["Nieuwe velden in de hoofdstructuur", list("root_keys_new").join(", ") || "geen"],
          ["Nieuwe Pokémon-velden", list("pokemon_keys_new").join(", ") || "geen"],
          ["Ontbrekende Pokémon-velden", list("pokemon_keys_missing").join(", ") || "geen"],
        ]}
      />
      {Object.keys(paths).length > 0 && (
        <details>
          <summary className="cursor-pointer text-muted">Alle veldpaden ({Object.keys(paths).length})</summary>
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
              ["Status", label(importStatusLabels, j.status)],
              ["Classificatie", j.classification ? label(classificationLabels, j.classification) : "nog niet bepaald"],
              ["Bron", j.source === "webhook" ? "PGSharp-webhook" : j.source === "upload" ? `Upload${j.filename ? ` (${j.filename})` : ""}` : "Opnieuw verwerkt"],
              ["Ontvangen", dateTime(j.received_at)],
              ["Exportmoment volgens PGSharp", dateTime(j.export_time)],
              ["Grootte", bytes(j.payload_size)],
              ["Export nog opgeslagen", j.payload_available ? "ja" : "nee"],
              ...(j.error_message ? ([["Melding", j.error_message]] as [string, string][]) : []),
            ]}
          />
          {j.sync_run && (
            <Card title="Resultaat">
              <KeyValue
                items={[
                  ["Pokémon in export", num(j.sync_run.total_pokemon)],
                  ["Eieren", num(j.sync_run.eggs)],
                  ["Nieuw", num(j.sync_run.new_count)],
                  ["Gewijzigd", num(j.sync_run.changed_count)],
                  ["Ongewijzigd", num(j.sync_run.unchanged_count)],
                  ["Niet meer in inventaris", num(j.sync_run.missing_count)],
                  ["Ontbreekt, niet bevestigd", num(j.sync_run.missing_unconfirmed_count)],
                  ["Teruggekeerd", num(j.sync_run.reappeared_count)],
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
            <Alert tone="info" title="Was dit toch een volledige export?">
              OAK heeft deze import als gedeeltelijk behandeld, dus ontbrekende Pokémon zijn niet als verdwenen gemarkeerd. Weet je zeker dat je
              in-game echt Pokémon hebt overgezet, bevestig dan dat de export volledig was.
              <div className="mt-2">
                <Button
                  size="sm"
                  loading={confirmFull.isPending}
                  onClick={() => {
                    if (window.confirm("Bevestigen dat deze export je volledige inventaris bevat? Ontbrekende Pokémon krijgen dan de status 'niet meer in inventaris'.")) confirmFull.mutate();
                  }}
                >
                  Bevestig als volledig
                </Button>
              </div>
            </Alert>
          )}
          {["failed", "rejected", "partial"].includes(j.status) && j.payload_available && (
            <Button loading={retry.isPending} onClick={() => retry.mutate()}>
              Opnieuw verwerken
            </Button>
          )}
          {error && <Alert tone="error">{error}</Alert>}
          {issues.data && issues.data.length > 0 && (
            <Card title={`Meldingen (${issues.data.length})`}>
              <ul className="max-h-64 space-y-1 overflow-auto text-xs">
                {issues.data.map((i) => (
                  <li key={i.id} className="flex gap-2">
                    <Badge color={i.severity === "error" ? "#ef4444" : "#f59e0b"}>{i.severity === "error" ? "fout" : "waarschuwing"}</Badge>
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
            <Card title="Structuur van de export">
              <SchemaSummary summary={j.schema_summary} />
            </Card>
          )}
        </div>
      )}
    </Dialog>
  );
}

function ImportList({ accountId }: { accountId: number }) {
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
    <Card title="Imports">
      {items.length === 0 ? (
        <EmptyState title="Nog geen imports">Stuur een export vanuit PGSharp of upload een bestand.</EmptyState>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-1">Ontvangen</th>
                <th>Bron</th>
                <th>Status</th>
                <th>Pokémon</th>
                <th>Nieuw</th>
                <th>Gewijzigd</th>
                <th>Weg</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((j) => (
                <tr key={j.id} className="border-t border-line">
                  <td className="py-1.5">{dateTime(j.received_at)}</td>
                  <td>{j.source === "webhook" ? "Webhook" : j.source === "upload" ? "Upload" : "Opnieuw"}</td>
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
                      Details
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
  const status = useQuery({
    queryKey: ["sync-status", accountId],
    queryFn: () => api.get<SyncStatus>("/api/v1/sync/status", { account_id: accountId }),
    refetchInterval: (q) => (q.state.data?.pending_imports ? POLL_MS : false),
  });
  const tone = status.data?.state === "error" ? "error" : status.data?.state === "warning" ? "warning" : status.data?.state === "connected" ? "success" : "info";
  return (
    <>
      <PageHeader title="PGSharp Sync" description="Koppel PGSharp via een webhook of upload een export. Beide routes gebruiken dezelfde verwerking." />
      {status.data && (
        <div className="mb-5">
          <Alert tone={tone} title={status.data.message}>
            Laatste succesvolle sync: {dateTime(status.data.last_successful_sync_at)}
            {status.data.pending_imports > 0 && ` · ${status.data.pending_imports} import(s) in verwerking`}
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
