import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";

import { AppShell } from "./components/layout/AppShell";
import { Spinner } from "./components/ui";
import { AccountProvider } from "./lib/account";
import { useAuth } from "./lib/auth";
import { AccountsPage } from "./pages/admin/AccountsPage";
import { BackupsPage } from "./pages/admin/BackupsPage";
import { GameDataPage } from "./pages/admin/GameDataPage";
import { SettingsPage } from "./pages/admin/SettingsPage";
import { SyncPage } from "./pages/admin/SyncPage";
import { HistoryPage } from "./pages/account/HistoryPage";
import { ItemsPage } from "./pages/account/ItemsPage";
import { ResourcesPage } from "./pages/account/ResourcesPage";
import { TrainerPage } from "./pages/account/TrainerPage";
import { LoginPage } from "./pages/auth/LoginPage";
import { LeaguePage } from "./pages/battles/LeaguePage";
import { GymPage } from "./pages/battles/GymPage";
import { MaxBattlePage } from "./pages/battles/MaxBattlePage";
import { RaidPage } from "./pages/battles/RaidPage";
import { RocketPage } from "./pages/battles/RocketPage";
import { TeamBuilderPage } from "./pages/battles/TeamBuilderPage";
import { CleanupPage } from "./pages/cleanup/CleanupPage";
import { DashboardPage } from "./pages/dashboard/DashboardPage";
import { EventsPage } from "./pages/events/EventsPage";
import { BoxPage } from "./pages/pokemon/BoxPage";
import { ComparePage } from "./pages/pokemon/ComparePage";
import { DetailPage } from "./pages/pokemon/DetailPage";
import { PlannerPage } from "./pages/pokemon/PlannerPage";
import { PokedexPage } from "./pages/pokedex/PokedexPage";

function RequireAuth({ children }: { children: ReactNode }) {
  const { status, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner />;
  if (status?.setup_required) return <Navigate to="/setup" replace />;
  if (!status?.authenticated) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

function NotFound() {
  return <p className="text-muted">Deze pagina bestaat niet.</p>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage mode="login" />} />
      <Route path="/setup" element={<LoginPage mode="setup" />} />
      <Route
        element={
          <RequireAuth>
            <AccountProvider>
              <AppShell />
            </AccountProvider>
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="pokemon" element={<BoxPage />} />
        <Route path="pokemon/:id" element={<DetailPage />} />
        <Route path="pokedex" element={<PokedexPage />} />
        <Route path="pokedex/:dex" element={<PokedexPage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="cleanup" element={<CleanupPage />} />
        <Route path="planner" element={<PlannerPage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="battles/team-builder" element={<TeamBuilderPage />} />
        <Route path="battles/raids" element={<RaidPage />} />
        <Route path="battles/rocket" element={<RocketPage />} />
        <Route path="battles/max" element={<MaxBattlePage />} />
        <Route path="battles/gyms" element={<GymPage />} />
        <Route path="battles/:league" element={<LeaguePage />} />
        <Route path="trainer" element={<TrainerPage />} />
        <Route path="items" element={<ItemsPage />} />
        <Route path="resources" element={<ResourcesPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="admin/accounts" element={<AccountsPage />} />
        <Route path="admin/sync" element={<SyncPage />} />
        <Route path="admin/gamedata" element={<GameDataPage />} />
        <Route path="admin/settings" element={<SettingsPage />} />
        <Route path="admin/backups" element={<BackupsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
