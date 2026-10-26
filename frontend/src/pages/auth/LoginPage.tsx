import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router";

import { LanguageSelect } from "../../components/LanguageSelect";
import { Alert, Button, Field, Input } from "../../components/ui";
import { errorMessage } from "../../lib/api";
import { useAuth } from "../../lib/auth";

export function LoginPage({ mode }: { mode: "login" | "setup" }) {
  const { t } = useTranslation();
  const { status, login, setup, loading } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  if (!loading && status?.authenticated) return <Navigate to="/" replace />;
  if (!loading && mode === "login" && status?.setup_required) return <Navigate to="/setup" replace />;
  if (!loading && mode === "setup" && status && !status.setup_required) return <Navigate to="/login" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (mode === "setup" && password !== confirm) {
      setError(t("login.mismatch"));
      return;
    }
    setBusy(true);
    try {
      if (mode === "setup") await setup(username, password);
      else await login(username, password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from && from !== "/login" ? from : "/", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl border border-line bg-surface p-6 shadow-xl">
        <div className="flex items-center gap-3">
          <img src="/oak.svg" alt="" className="h-10 w-10" />
          <div>
            <h1 className="text-lg font-semibold">OAK</h1>
            <p className="text-xs text-muted">{t("app.tagline")}</p>
          </div>
          <LanguageSelect className="ml-auto w-32" />
        </div>
        {mode === "setup" && (
          <Alert tone="info" title={t("login.firstUse")}>
            {t("login.firstUseText")}
          </Alert>
        )}
        {error && <Alert tone="error">{error}</Alert>}
        <Field label={t("login.username")}>
          <Input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
        </Field>
        <Field label={t("login.password")} hint={mode === "setup" ? t("login.passwordHint") : undefined}>
          <Input
            type="password"
            autoComplete={mode === "setup" ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        {mode === "setup" && (
          <Field label={t("login.repeatPassword")}>
            <Input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
          </Field>
        )}
        <Button type="submit" variant="primary" className="w-full" loading={busy}>
          {mode === "setup" ? t("login.createOwner") : t("login.submit")}
        </Button>
      </form>
    </div>
  );
}
