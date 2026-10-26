/** API response shapes without big identifiers. Pokémon payloads live in ./schemas.ts. */

import type { ServerText } from "./serverText";

export interface User {
  id: number;
  username: string;
  email: string | null;
  role: "owner" | "user";
  status: string;
  created_at: string;
  last_login_at: string | null;
  preferences: Record<string, unknown>;
}

export interface AuthStatus {
  setup_required: boolean;
  registration_open: boolean;
  authenticated: boolean;
  user: User | null;
  csrf_token: string | null;
}

export interface Webhook {
  active: boolean;
  token_identifier: string | null;
  url_masked: string | null;
  created_at: string | null;
  last_used_at: string | null;
}

export interface Account {
  id: number;
  nickname: string;
  source_nickname: string | null;
  trainer_level: number | null;
  experience: number | null;
  stardust: number | null;
  pokecoins: number | null;
  team: number | null;
  max_pokemon_storage: number | null;
  max_item_storage: number | null;
  last_successful_sync_at: string | null;
  last_export_time: string | null;
  last_import_attempt_at: string | null;
  sync_status: string;
  created_at: string;
  pokemon_count: number;
  linked: boolean;
  webhook: Webhook | null;
  diagnostics_until: string | null;
  completeness: { max_drop_fraction?: number; max_drop_absolute?: number };
}

export interface SyncRun {
  id: number;
  classification: string;
  source: string;
  export_time: string | null;
  applied_at: string;
  total_pokemon: number;
  eggs: number;
  new_count: number;
  changed_count: number;
  unchanged_count: number;
  missing_count: number;
  missing_unconfirmed_count: number;
  reappeared_count: number;
  items_changed: boolean;
  /** "data" holds the values in the message; warnings stored before OAK kept them have none. */
  warnings: { code: string; message: string; data?: Record<string, unknown> | null }[];
}

export interface ImportJob {
  id: number;
  trainer_account_id: number;
  source: string;
  status: string;
  stage: string | null;
  progress: number;
  classification: string | null;
  filename: string | null;
  payload_size: number;
  payload_available: boolean;
  export_time: string | null;
  received_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
  error_message: string | null;
  error_data: Record<string, unknown> | null;
  duplicate_of_id: number | null;
  retry_of_id: number | null;
  confirm_full: boolean;
  request_meta: Record<string, unknown> | null;
  schema_summary: Record<string, unknown> | null;
  sync_run: SyncRun | null;
  issue_counts: Record<string, number>;
  confirmable: boolean;
}

export interface ImportIssue {
  id: number;
  severity: string;
  code: string;
  message: string;
  data: Record<string, unknown> | null;
  path: string | null;
  source_pokemon_id: string | null;
}

export interface SyncStatus {
  account_id: number;
  state: "waiting" | "connected" | "processing" | "error" | "warning";
  message: ServerText;
  last_successful_sync_at: string | null;
  last_import_attempt_at: string | null;
  webhook_active: boolean;
  webhook_last_used_at: string | null;
  pending_imports: number;
  last_import: ImportJob | null;
  last_sync: SyncRun | null;
}

export interface Paged<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface Facets {
  species: { species_id: number; name: string | null; count: number }[];
  years: { year: number; count: number }[];
  families: string[];
  types: string[];
  tags: { tag_id: string; count: number; label: string | null; protects: boolean }[];
}

export interface Cost {
  stardust: number;
  candy: number;
  xl_candy: number;
  power_ups: number;
}

export interface MoveNeed {
  slot: string;
  current: string | null;
  target: string | null;
  availability: string | null;
  action: string;
  pool_size: number | null;
}

export interface LeagueTarget {
  league: string;
  target_key: string;
  target_name: string;
  is_evolution: boolean;
  evolution_candy: number | null;
  evolution_item: string | null;
  rank: number;
  percent: number;
  stat_product: number;
  best_cp: number;
  best_level: number;
  cp_now: number | null;
  readiness: string;
  readiness_reason: string;
  cost: Cost | null;
  species_rank: number | null;
  species_score: number | null;
  moveset: {
    moveset: string[];
    names: string[];
    source: string;
    elite_moves: string[];
    unavailable: string[];
    needs: MoveNeed[];
  } | null;
}

/** "current" is the Pokémon as it is; "purified" is a Shadow Pokémon after purification. */
export type Scenario = "current" | "purified";

export interface PurifyScenario {
  key: "purified";
  level: number;
  ivs: { attack: number; defense: number; stamina: number };
  cp: number | null;
  hp: number | null;
  cost: { stardust: number | null; candy: number | null };
  assumption: string | null;
  source: string | null;
}

export interface PokemonAnalysis {
  available: boolean;
  reason?: string;
  game_data_version?: number;
  scenario?: PurifyScenario | null;
  rules?: { max_level: number; include_best_buddy: boolean; elite_tm_available: boolean; ready_cp_fraction: number };
  method?: Record<string, string>;
  leagues?: Record<string, { cap: number | null; primary_target: string | null; targets: LeagueTarget[] }>;
  current_moves?: { key: string; name: string; availability: string }[];
  second_move_cost?: { stardust: number | null; candy: number | null } | null;
  form_resolution?: string | null;
}

export interface EvolutionPath {
  target_key: string;
  target_name: string;
  types: string[];
  steps: {
    from_key: string;
    to_key: string;
    candy: number | null;
    candy_purified: number | null;
    item: string | null;
    item_cost: number | null;
    lure: string | null;
    buddy_km: number | null;
    conditions: string[];
    quest: string | null;
    no_candy_cost_via_trade: boolean;
  }[];
  total_candy: number | null;
  cp_after: number | null;
  hp_after: number | null;
  leagues: Record<string, { rank: number | null; percent: number | null; readiness: string | null; over_cap: boolean; species_rank: number | null }>;
  elite_moves: string[];
  note: string | null;
}

export interface PowerUps {
  available: boolean;
  reason?: string;
  current?: { level: number; cp: number | null };
  scenario?: PurifyScenario | null;
  max_level?: number;
  modifiers?: { shadow: boolean; purified: boolean; lucky: boolean };
  note?: string;
  steps?: { level: number; cp: number | null; cost: Cost | null }[];
  candy_available?: number | null;
}

export interface HistoryEvent {
  id: number;
  type: string;
  sync_run_id: number;
  at: string;
  labels: string[];
  changes: Record<string, [unknown, unknown]>;
}

export interface GameDataVersion {
  id: number;
  status: string;
  origin: string;
  created_at: string;
  activated_at: string | null;
  summary: Record<string, unknown> | null;
  sources: { id: string; url: string; sha256?: string; retrieved_at?: string; upstream_timestamp?: string | null; bytes?: number }[];
  error: string | null;
  /** The errors in "error" one by one; null for versions from before OAK kept them. */
  errors?: ServerText[] | null;
}

export interface GameDataStatus {
  active: GameDataVersion | null;
  versions: GameDataVersion[];
  last_check: { at: string; error: string | null } | null;
  last_error: string | null;
  last_errors?: ServerText[] | null;
  update_pending: boolean;
  auto_update: boolean;
  interval_hours: number;
  dependent_analyses: ServerText[];
}

export interface AppSettings {
  sprite_source: "none" | "pokeapi" | "custom";
  sprite_url_template: string | null;
  sprite_notice: ServerText;
  timezone: string;
  base_url: string;
}

export interface Rules {
  [key: string]: boolean | number | null;
}
