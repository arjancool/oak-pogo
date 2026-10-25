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
import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";

import { useAccount } from "../../lib/account";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { relative } from "../../lib/format";
import type { SyncStatus } from "../../lib/types";
import { Select } from "../ui";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
}

const sections: { title: string; items: NavItem[] }[] = [
  {
    title: "Dashboard",
    items: [
      { to: "/", label: "Overzicht", icon: <LayoutDashboard className="h-4 w-4" /> },
      { to: "/history?kind=new", label: "Nieuwe Pokémon", icon: <Sparkles className="h-4 w-4" /> },
    ],
  },
  {
    title: "Pokémon",
    items: [
      { to: "/pokemon", label: "Pokémon Box", icon: <Boxes className="h-4 w-4" /> },
      { to: "/pokedex", label: "Pokédex", icon: <BookOpen className="h-4 w-4" /> },
      { to: "/compare", label: "Vergelijken", icon: <GitCompare className="h-4 w-4" /> },
      { to: "/cleanup", label: "Cleanup Manager", icon: <Brush className="h-4 w-4" /> },
      { to: "/planner", label: "Evolutieplanner", icon: <Wand2 className="h-4 w-4" /> },
      { to: "/events", label: "Komende events", icon: <CalendarDays className="h-4 w-4" /> },
    ],
  },
  {
    title: "Battles",
    items: [
      { to: "/battles/great", label: "Great League", icon: <Trophy className="h-4 w-4" /> },
      { to: "/battles/ultra", label: "Ultra League", icon: <Trophy className="h-4 w-4" /> },
      { to: "/battles/master", label: "Master League", icon: <Trophy className="h-4 w-4" /> },
      { to: "/battles/cups", label: "Cups", icon: <Medal className="h-4 w-4" /> },
      { to: "/battles/team-builder", label: "Team Builder", icon: <Users className="h-4 w-4" /> },
      { to: "/battles/rocket", label: "Team GO Rocket", icon: <Swords className="h-4 w-4" /> },
      { to: "/battles/raids", label: "Raids", icon: <Zap className="h-4 w-4" /> },
      { to: "/battles/max", label: "Max Battles", icon: <Activity className="h-4 w-4" /> },
      { to: "/battles/gyms", label: "Gymverdedigers", icon: <Shield className="h-4 w-4" /> },
    ],
  },
  {
    title: "Account",
    items: [
      { to: "/trainer", label: "Trainerstatistieken", icon: <BarChart3 className="h-4 w-4" /> },
      { to: "/items", label: "Item Bag", icon: <Backpack className="h-4 w-4" /> },
      { to: "/resources", label: "Stardust & Candy", icon: <Sparkles className="h-4 w-4" /> },
      { to: "/history", label: "Historie", icon: <History className="h-4 w-4" /> },
    ],
  },
  {
    title: "Beheer",
    items: [
      { to: "/admin/accounts", label: "Traineraccounts", icon: <Users className="h-4 w-4" /> },
      { to: "/admin/sync", label: "PGSharp Sync", icon: <RefreshCw className="h-4 w-4" /> },
      { to: "/admin/gamedata", label: "Game Data", icon: <Database className="h-4 w-4" /> },
      { to: "/admin/settings", label: "Instellingen", icon: <Cog className="h-4 w-4" /> },
      { to: "/admin/backups", label: "Back-ups", icon: <Archive className="h-4 w-4" /> },
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
const stateLabels: Record<string, string> = {
  connected: "Gesynchroniseerd",
  processing: "Verwerken…",
  warning: "Gedeeltelijk",
  error: "Fout",
  waiting: "Wacht op export",
};

function SyncPill() {
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
      title={data.message}
    >
      <span className={clsx("h-2 w-2 rounded-full", stateStyles[data.state])} />
      {stateLabels[data.state]}
      {data.last_successful_sync_at && <span className="opacity-70">· {relative(data.last_successful_sync_at)}</span>}
    </NavLink>
  );
}

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth();
  return (
    <nav className="space-y-5 px-3 py-4">
      {sections.map((section) => (
        <div key={section.title}>
          <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted">{section.title}</p>
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
                    {item.label}
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
          <span className="text-xs text-muted">Pokémon GO Manager</span>
        </div>
        <Navigation />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setOpen(false)}>
          <aside className="h-full w-72 overflow-y-auto border-r border-line bg-surface-2" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4">
              <span className="font-semibold">OAK</span>
              <button onClick={() => setOpen(false)} aria-label="Menu sluiten">
                <X className="h-5 w-5" />
              </button>
            </div>
            <Navigation onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-surface/90 px-4 py-2.5 backdrop-blur">
          <button className="lg:hidden" onClick={() => setOpen(true)} aria-label="Menu openen">
            <Menu className="h-5 w-5" />
          </button>
          {accounts.length > 0 ? (
            <Select
              aria-label="Traineraccount"
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
              Traineraccount aanmaken
            </button>
          )}
          <SyncPill />
          <div className="ml-auto flex items-center gap-3 text-sm">
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
              <LogOut className="h-4 w-4" /> Uitloggen
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
