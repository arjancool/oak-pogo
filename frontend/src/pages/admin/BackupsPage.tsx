import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Trash2 } from "lucide-react";
import { useState } from "react";

import { Alert, Button, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { api, errorMessage } from "../../lib/api";
import { bytes, dateTime } from "../../lib/format";

interface Backup {
  name: string;
  size_bytes: number;
  created_at: string;
}

export function BackupsPage() {
  const client = useQueryClient();
  const { user } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const owner = user?.role === "owner";
  const list = useQuery({ queryKey: ["backups"], queryFn: () => api.get<Backup[]>("/api/v1/backups"), enabled: owner });
  const refresh = () => void client.invalidateQueries({ queryKey: ["backups"] });
  const create = useMutation({ mutationFn: () => api.post("/api/v1/backups"), onSuccess: refresh, onError: (err) => setError(errorMessage(err)) });
  const remove = useMutation({ mutationFn: (name: string) => api.delete(`/api/v1/backups/${encodeURIComponent(name)}`), onSuccess: refresh });

  if (!owner) return <EmptyState title="Alleen voor de eigenaar">Back-ups beheren kan alleen de eigenaar van deze OAK-installatie.</EmptyState>;
  return (
    <>
      <PageHeader
        title="Back-ups"
        description="OAK maakt automatisch een back-up voor iedere databasemigratie. Hier maak je er zelf een en download je hem."
        actions={
          <Button variant="primary" loading={create.isPending} onClick={() => create.mutate()}>
            Back-up maken
          </Button>
        }
      />
      {error && (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      )}
      <div className="mb-5">
        <Alert tone="info" title="Terugzetten">
          Stop de container, vervang <code>/data/oak.db</code> door de back-up en start de container opnieuw. Een volledige back-up van de map
          <code> /data</code> bevat ook de geheime sleutel en opgeslagen exports. Zie docs/BACKUP_RESTORE.md.
        </Alert>
      </div>
      <Card title="Beschikbare back-ups">
        {list.isLoading ? (
          <Spinner />
        ) : !list.data?.length ? (
          <p className="text-sm text-muted">Nog geen back-ups.</p>
        ) : (
          <ul className="divide-y divide-line text-sm">
            {list.data.map((b) => (
              <li key={b.name} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>
                  <span className="font-mono text-xs">{b.name}</span>
                  <span className="ml-2 text-muted">
                    {dateTime(b.created_at)} · {bytes(b.size_bytes)}
                  </span>
                </span>
                <span className="flex gap-2">
                  <a href={`/api/v1/backups/${encodeURIComponent(b.name)}`} download>
                    <Button size="sm" icon={<Download size={14} />}>
                      Downloaden
                    </Button>
                  </a>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Trash2 size={14} />}
                    onClick={() => {
                      if (window.confirm(`Back-up ${b.name} verwijderen?`)) remove.mutate(b.name);
                    }}
                  >
                    Verwijderen
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
