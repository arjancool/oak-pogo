import clsx from "clsx";
import { CalendarClock, Heart, Hourglass, Shield, Sparkles } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { label, readinessLabels, statusDescriptions, statusLabels, typeColors, typeNames } from "../../lib/i18n";
import type { PokemonSummary } from "../../lib/schemas";
import { spriteUrl, useAppSettings } from "../../lib/settings";
import { Badge } from "../ui";

/**
 * Sprite when the owner enabled an external source, otherwise a generated badge. OAK ships no
 * Pokémon artwork (ADR-0020); a missing image never breaks the layout.
 */
export function PokemonSprite({ dex, shiny, types, size = 48 }: { dex: number; shiny?: boolean | null; types?: string[]; size?: number }) {
  const settings = useAppSettings();
  const [failed, setFailed] = useState(false);
  const url = spriteUrl(settings.data?.sprite_url_template, dex, Boolean(shiny));
  const color = typeColors[types?.[0] ?? ""] ?? "#64748b";
  if (url && !failed) {
    return (
      <img
        src={url}
        alt=""
        loading="lazy"
        width={size}
        height={size}
        onError={() => setFailed(true)}
        className="shrink-0 [image-rendering:pixelated]"
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <div
      aria-hidden
      className="flex shrink-0 items-center justify-center rounded-full font-mono font-semibold text-white/90"
      style={{
        width: size,
        height: size,
        fontSize: size / 3.6,
        background: `radial-gradient(circle at 30% 30%, ${color}, ${color}66 70%)`,
      }}
    >
      {String(dex).padStart(3, "0")}
    </div>
  );
}

export function TypeBadge({ type }: { type: string }) {
  return <Badge color={typeColors[type]}>{typeNames[type] ?? type}</Badge>;
}

export function pokemonName(p: Pick<PokemonSummary, "species_name" | "species_id" | "form_label">): string {
  const base = p.species_name ?? `#${p.species_id}`;
  return p.form_label ? `${base} (${p.form_label})` : base;
}

export function IvBars({ attack, defense, stamina }: { attack: number | null; defense: number | null; stamina: number | null }) {
  const rows: [string, number | null][] = [
    ["Atk", attack],
    ["Def", defense],
    ["HP", stamina],
  ];
  return (
    <div className="space-y-1">
      {rows.map(([name, value]) => (
        <div key={name} className="flex items-center gap-2 text-xs">
          <span className="w-7 text-muted">{name}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-3">
            <div
              className={clsx("h-full rounded-full", value === 15 ? "bg-red-400" : "bg-amber-400")}
              style={{ width: `${((value ?? 0) / 15) * 100}%` }}
            />
          </div>
          <span className="w-5 text-right tabular-nums">{value ?? "?"}</span>
        </div>
      ))}
    </div>
  );
}

export function IvPercent({ value }: { value: number | null }) {
  if (value === null) return <span className="text-muted">?</span>;
  const color = value === 100 ? "text-red-400" : value >= 90 ? "text-oak-400" : value >= 66 ? "text-amber-300" : "text-muted";
  return <span className={clsx("font-semibold tabular-nums", color)}>{value.toLocaleString("nl-NL")}%</span>;
}

const statusColors: Record<string, string> = {
  PROTECT: "#38bdf8",
  KEEP: "#34d399",
  BUILD: "#a78bfa",
  REVIEW: "#fbbf24",
  TRANSFER_CANDIDATE: "#f87171",
  UNKNOWN: "#94a3b8",
};

const SCORE_HIGH = 70;
const SCORE_MID = 40;

/** A 0–100 score as a small labelled bar. "onbekend" when the value could not be computed. */
export function ScoreMeter({ label: text, value, title }: { label: string; value: number | null | undefined; title?: string }) {
  const { t } = useTranslation();
  const known = value !== null && value !== undefined;
  const color = !known ? "#64748b" : value >= SCORE_HIGH ? "#34d399" : value >= SCORE_MID ? "#fbbf24" : "#f87171";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs" title={title}>
      <span className="text-muted">{text}</span>
      <span className="relative h-1.5 w-12 overflow-hidden rounded bg-surface-3" aria-hidden>
        <span className="absolute inset-y-0 left-0 rounded" style={{ width: `${known ? value : 0}%`, background: color }} />
      </span>
      <span className="font-semibold tabular-nums" style={{ color }}>
        {known ? value : t("common.unknown")}
      </span>
    </span>
  );
}

export function CleanupBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="text-xs text-muted">–</span>;
  return (
    <Badge color={statusColors[status]} title={statusDescriptions[status]}>
      {label(statusLabels, status)}
    </Badge>
  );
}

const readinessColors: Record<string, string> = {
  direct: "#34d399",
  power_up: "#fbbf24",
  evolution: "#a78bfa",
  after_evolution: "#a78bfa",
  not_suitable: "#f87171",
  unknown: "#94a3b8",
};

export function ReadinessBadge({ readiness }: { readiness: string | null | undefined }) {
  if (!readiness) return <span className="text-xs text-muted">–</span>;
  return <Badge color={readinessColors[readiness]}>{label(readinessLabels, readiness)}</Badge>;
}

export function StatusBadges({ pokemon, compact }: { pokemon: PokemonSummary; compact?: boolean }) {
  const { t } = useTranslation();
  const badges: { key: string; text: string; color?: string; icon?: React.ReactNode }[] = [];
  if (pokemon.vintage_year !== null)
    badges.push({ key: "vintage", text: t("badges.vintage", { year: pokemon.vintage_year }), color: "#d97706", icon: <Hourglass className="h-3 w-3" /> });
  if (!pokemon.catch_date_known) badges.push({ key: "nodate", text: t("badges.noDate"), color: "#94a3b8", icon: <CalendarClock className="h-3 w-3" /> });
  if (pokemon.favorite) badges.push({ key: "fav", text: t("badges.favorite"), color: "#facc15", icon: <Heart className="h-3 w-3" /> });
  if (pokemon.shundo) badges.push({ key: "shundo", text: t("badges.shundo"), color: "#f472b6", icon: <Sparkles className="h-3 w-3" /> });
  else if (pokemon.shiny) badges.push({ key: "shiny", text: t("badges.shiny"), color: "#f472b6", icon: <Sparkles className="h-3 w-3" /> });
  if (pokemon.hundo && !pokemon.shundo) badges.push({ key: "hundo", text: t("badges.hundo"), color: "#ef4444" });
  if (pokemon.lucky) badges.push({ key: "lucky", text: t("badges.lucky"), color: "#eab308" });
  if (pokemon.shadow) badges.push({ key: "shadow", text: t("badges.shadow"), color: "#a855f7" });
  if (pokemon.purified) badges.push({ key: "purified", text: t("badges.purified"), color: "#e2e8f0" });
  if (pokemon.gigantamax) badges.push({ key: "gmax", text: t("badges.gigantamax"), color: "#f43f5e" });
  else if (pokemon.dynamax) badges.push({ key: "dmax", text: t("badges.dynamax"), color: "#e11d48" });
  if (pokemon.pokemon_class === "legendary") badges.push({ key: "leg", text: t("badges.legendary"), color: "#f59e0b" });
  if (pokemon.pokemon_class === "mythical") badges.push({ key: "myth", text: t("badges.mythical"), color: "#ec4899" });
  if (pokemon.pokemon_class === "ultra_beast") badges.push({ key: "ub", text: t("badges.ultraBeast"), color: "#06b6d4" });
  if (pokemon.costume) badges.push({ key: "costume", text: t("badges.costume"), color: "#14b8a6" });
  if (pokemon.location_card) badges.push({ key: "bg", text: t("badges.background"), color: "#22d3ee" });
  if (pokemon.traded) badges.push({ key: "traded", text: t("badges.traded") });
  if (pokemon.in_gym) badges.push({ key: "in_gym", text: t("badges.inGym"), color: "#38bdf8" });
  if (pokemon.metadata?.protected) badges.push({ key: "prot", text: t("badges.protected"), color: "#38bdf8", icon: <Shield className="h-3 w-3" /> });
  if (pokemon.is_new) badges.push({ key: "new", text: t("badges.new"), color: "#34d399" });
  if (pokemon.inventory_status === "not_in_inventory") badges.push({ key: "gone", text: t("badges.gone"), color: "#94a3b8" });
  const visible = compact ? badges.slice(0, 4) : badges;
  return (
    <div className="flex flex-wrap gap-1">
      {visible.map((badge) => (
        <Badge key={badge.key} color={badge.color}>
          {badge.icon}
          {badge.text}
        </Badge>
      ))}
      {compact && badges.length > visible.length && <Badge>+{badges.length - visible.length}</Badge>}
    </div>
  );
}

export function MoveLine({ pokemon }: { pokemon: PokemonSummary }) {
  return (
    <div className="text-xs">
      <span className="font-medium">{pokemon.fast_move?.name ?? "?"}</span>
      <span className="text-muted"> · {pokemon.charged_moves.map((m) => m.name).join(" / ") || "?"}</span>
    </div>
  );
}
