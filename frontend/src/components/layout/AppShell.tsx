import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Activity,
  Archive,
  BarChart3,
  Backpack,
  BookOpen,
  Boxes,
  Brush,
  CalendarDays,
  Cog,
  Database,
  GitCompare,
  History,
  LayoutDashboard,
  LogOut,
  Medal,
  Menu,
  RefreshCw,
  Shield,
  Sparkles,
  Swords,
  Trophy,
  Users,
  Wand2,
  X,
  Zap,
} from "lucide-react";
import type { ParseKeys } from "i18next";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate } from "react-router";

import { useAccount } from "../../lib/account";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { relative } from "../../lib/format";
import { serverText } from "../../lib/serverText";
import type { SyncStatus } from "../../lib/types";
import { LanguageSelect } from "../LanguageSelect";
import { Select } from "../ui";

interface NavItem {
  to: string;
  label: ParseKeys;
  icon: ReactNode;
}

const sections: { title: ParseKeys; items: NavItem[] }[] = [
  {
    title: "nav.sections.dashboard",
    items: [
      { to: "/", label: "nav.overview", icon: <LayoutDashboard className="h-4 w-4" /> },
      { to: "/history?kind=new", label: "nav.newPokemon", icon: <Sparkles className="h-4 w-4" /> },
    ],
  },
  {
    title: "nav.sections.pokemon",
    items: [
      { to: "/pokemon", label: "nav.box", icon: <Boxes className="h-4 w-4" /> },
      { to: "/pokedex", label: "nav.pokedex", icon: <BookOpen className="h-4 w-4" /> },
      { to: "/compare", label: "nav.compare", icon: <GitCompare className="h-4 w-4" /> },
      { to: "/cleanup", label: "nav.cleanup", icon: <Brush className="h-4 w-4" /> },
      { to: "/planner", label: "nav.planner", icon: <Wand2 className="h-4 w-4" /> },
      { to: "/events", label: "nav.events", icon: <CalendarDays className="h-4 w-4" /> },
    ],
  },
  {
    title: "nav.sections.battles",
    items: [
      { to: "/battles/great", label: "nav.great", icon: <Trophy className="h-4 w-4" /> },
      { to: "/battles/ultra", label: "nav.ultra", icon: <Trophy className="h-4 w-4" /> },
      { to: "/battles/master", label: "nav.master", icon: <Trophy className="h-4 w-4" /> },
      { to: "/battles/cups", label: "nav.cups", icon: <Medal className="h-4 w-4" /> },
      { to: "/battles/team-builder", label: "nav.teamBuilder", icon: <Users className="h-4 w-4" /> },
      { to: "/battles/rocket", label: "nav.rocket", icon: <Swords className="h-4 w-4" /> },
      { to: "/battles/raids", label: "nav.raids", icon: <Zap className="h-4 w-4" /> },
      { to: "/battles/max", label: "nav.max", icon: <Activity className="h-4 w-4" /> },
      { to: "/battles/gyms", label: "nav.gyms", icon: <Shield className="h-4 w-4" /> },
    ],
  },
  {
    title: "nav.sections.account",
    items: [
      { to: "/trainer", label: "nav.trainer", icon: <BarChart3 className="h-4 w-4" /> },
      { to: "/items", label: "nav.items", icon: <Backpack className="h-4 w-4" /> },
      { to: "/resources", label: "nav.resources", icon: <Sparkles className="h-4 w-4" /> },
      { to: "/history", label: "nav.history", icon: <History className="h-4 w-4" /> },
    ],
  },
  {
    title: "nav.sections.admin",
    items: [
      { to: "/admin/accounts", label: "nav.accounts", icon: <Users className="h-4 w-4" /> },
      { to: "/admin/sync", label: "nav.sync", icon: <RefreshCw className="h-4 w-4" /> },
      { to: "/admin/gamedata", label: "nav.gamedata", icon: <Database className="h-4 w-4" /> },
      { to: "/admin/settings", label: "nav.settings", icon: <Cog className="h-4 w-4" /> },
      { to: "/admin/backups", label: "nav.backups", icon: <Archive className="h-4 w-4" /> },
    ],
  },
];

const stateStyles: Record<string, string> = {
  connected: "bg-oak-500",
  processing: "bg-sky-400 animate-pulse",
  warning: "bg-amber-400",
  error: "bg-red-500",
  waiting: "bg-slate-500",
};
const stateLabels: Record<SyncStatus["state"], ParseKeys> = {
  connected: "shell.sync.connected",
  processing: "shell.sync.processing",
  warning: "shell.sync.warning",
  error: "shell.sync.error",
  waiting: "shell.sync.waiting",
};

function SyncPill() {
  const { t } = useTranslation();
  const { accountId } = useAccount();
  const status = useQuery({
    queryKey: ["sync-status", accountId],
    queryFn: () => api.get<SyncStatus>("/api/v1/sync/status", { account_id: accountId }),
    enabled: accountId !== null,
    refetchInterval: (query) => (query.state.data?.state === "processing" ? 2_000 : 30_000),
  });
  const data = status.data;
  if (!data) return null;
  return (
    <NavLink
      to="/admin/sync"
      className="hidden items-center gap-2 rounded-full border border-line px-3 py-1 text-xs text-muted hover:text-ink sm:flex"
      title={serverText("sync", data.message)}
    >
      <span className={clsx("h-2 w-2 rounded-full", stateStyles[data.state])} />
      {t(stateLabels[data.state])}
      {data.last_successful_sync_at && <span className="opacity-70">· {relative(data.last_successful_sync_at)}</span>}
    </NavLink>
  );
}

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  return (
    <nav className="space-y-5 px-3 py-4">
      {sections.map((section) => (
        <div key={section.title}>
          <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted">{t(section.title)}</p>
          <ul className="space-y-0.5">
            {section.items
              .filter((item) => user?.role === "owner" || !["/admin/gamedata", "/admin/backups"].includes(item.to))
              .map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === "/"}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      clsx(
                        "flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-sm",
                        isActive ? "bg-oak-500/15 text-oak-300" : "text-muted hover:bg-surface-3 hover:text-ink",
                      )
                    }
                  >
                    {item.icon}
                    {t(item.label)}
                  </NavLink>
                </li>
              ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function AppShell() {
  const { t, i18n } = useTranslation();
  const { user, logout } = useAuth();
  const { accounts, accountId, setAccountId } = useAccount();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="flex min-h-full">
      <aside className="no-print sticky top-0 hidden h-screen w-60 shrink-0 overflow-y-auto border-r border-line bg-surface-2 lg:block">
        <div className="flex items-center gap-2 px-6 py-4">
          <img src="/oak.svg" alt="" className="h-7 w-7" />
          <span className="font-semibold">OAK</span>
          <span className="text-xs text-muted">{t("app.tagline")}</span>
        </div>
        <Navigation />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setOpen(false)}>
          <aside className="h-full w-72 overflow-y-auto border-r border-line bg-surface-2" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4">
              <span className="font-semibold">OAK</span>
              <button onClick={() => setOpen(false)} aria-label={t("shell.closeMenu")}>
                <X className="h-5 w-5" />
              </button>
            </div>
            <Navigation onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-surface/90 px-4 py-2.5 backdrop-blur">
          <button className="lg:hidden" onClick={() => setOpen(true)} aria-label={t("shell.openMenu")}>
            <Menu className="h-5 w-5" />
          </button>
          {accounts.length > 0 ? (
            <Select
              aria-label={t("shell.trainerAccount")}
              value={accountId ?? ""}
              onChange={(event) => setAccountId(Number(event.target.value))}
              className="max-w-48"
            >
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.nickname}
                </option>
              ))}
            </Select>
          ) : (
            <button className="text-sm text-oak-400" onClick={() => navigate("/admin/accounts")}>
              {t("shell.createTrainerAccount")}
            </button>
          )}
          <SyncPill />
          <div className="ml-auto flex items-center gap-3 text-sm">
            <LanguageSelect className="w-32" />
            <span className="hidden items-center gap-1 text-muted sm:flex">
              <Shield className="h-4 w-4" />
              {user?.username}
            </span>
            <button
              className="flex items-center gap-1 text-muted hover:text-ink"
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
            >
              <LogOut className="h-4 w-4" /> {t("shell.logout")}
            </button>
          </div>
        </header>
        {/* A new language renders the page again, also parts that read labels outside React. */}
        <main key={i18n.language} className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
