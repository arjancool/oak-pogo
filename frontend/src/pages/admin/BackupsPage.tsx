import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Trash2 } from "lucide-react";
import { useState } from "react";
import { Trans, useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
  const client = useQueryClient();
  const { user } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const owner = user?.role === "owner";
  const list = useQuery({ queryKey: ["backups"], queryFn: () => api.get<Backup[]>("/api/v1/backups"), enabled: owner });
  const refresh = () => void client.invalidateQueries({ queryKey: ["backups"] });
  const create = useMutation({ mutationFn: () => api.post("/api/v1/backups"), onSuccess: refresh, onError: (err) => setError(errorMessage(err)) });
  const remove = useMutation({ mutationFn: (name: string) => api.delete(`/api/v1/backups/${encodeURIComponent(name)}`), onSuccess: refresh });

  if (!owner) return <EmptyState title={t("admin.backups.ownerOnlyTitle")}>{t("admin.backups.ownerOnlyText")}</EmptyState>;
  return (
    <>
      <PageHeader
        title={t("admin.backups.title")}
        description={t("admin.backups.description")}
        actions={
          <Button variant="primary" loading={create.isPending} onClick={() => create.mutate()}>
            {t("admin.backups.create")}
          </Button>
        }
      />
      {error && (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      )}
      <div className="mb-5">
        <Alert tone="info" title={t("admin.backups.restoreTitle")}>
          <Trans i18nKey="admin.backups.restoreText" components={{ code: <code /> }} />
        </Alert>
      </div>
      <Card title={t("admin.backups.available")}>
        {list.isLoading ? (
          <Spinner />
        ) : !list.data?.length ? (
          <p className="text-sm text-muted">{t("admin.backups.none")}</p>
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
                      {t("admin.backups.download")}
                    </Button>
                  </a>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Trash2 size={14} />}
                    onClick={() => {
                      if (window.confirm(t("admin.backups.deleteConfirm", { name: b.name }))) remove.mutate(b.name);
                    }}
                  >
                    {t("admin.backups.delete")}
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
