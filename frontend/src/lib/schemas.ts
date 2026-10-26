/** Zod schemas for API payloads that carry identifiers. Big IDs must be decimal strings. */
import { z } from "zod";

export const bigId = z.string().regex(/^\d{1,20}$/, "64-bits ID moet als tekst binnenkomen");

const move = z.object({
  id: z.number().nullable(),
  key: z.string().nullable(),
  name: z.string(),
  type: z.string().nullable(),
  kind: z.string().nullable(),
});

const metadata = z.object({
  protected: z.boolean(),
  protection_reason: z.string().nullable(),
  notes: z.string().nullable(),
  tags: z.array(z.string()),
  planned_action: z.string().nullable(),
  planned_league: z.string().nullable(),
  priority: z.number().nullable(),
  review_status: z.string(),
  override_status: z.string().nullable(),
  last_reviewed_at: z.string().nullable(),
  updated_at: z.string(),
});

const leagueSummary = z.object({ rank: z.number().nullable().optional(), percent: z.number().nullable().optional() });

export const pokemonSummary = z.object({
  id: z.number(),
  source_pokemon_id: bigId,
  species_id: z.number(),
  species_name: z.string().nullable(),
  form_label: z.string().nullable(),
  form_name: z.string().nullable(),
  form_key: z.string().nullable(),
  form_resolution: z.string().nullable(),
  costume_id: z.number().nullable(),
  gender: z.number().nullable(),
  nickname: z.string().nullable(),
  cp: z.number().nullable(),
  hp: z.number().nullable(),
  max_hp: z.number().nullable(),
  level: z.number().nullable(),
  iv_attack: z.number().nullable(),
  iv_defense: z.number().nullable(),
  iv_stamina: z.number().nullable(),
  iv_percent: z.number().nullable(),
  types: z.array(z.string()),
  pokemon_class: z.string().nullable(),
  family_id: z.string().nullable(),
  shiny: z.boolean().nullable(),
  lucky: z.boolean().nullable(),
  favorite: z.boolean().nullable(),
  shadow: z.boolean().nullable(),
  purified: z.boolean().nullable(),
  dynamax: z.boolean().nullable(),
  gigantamax: z.boolean().nullable(),
  costume: z.boolean().nullable(),
  location_card: z.number().nullable(),
  traded: z.boolean(),
  hatched_from_egg: z.boolean().nullable(),
  in_gym: z.boolean().nullable(),
  hundo: z.boolean(),
  shundo: z.boolean(),
  caught_at: z.string().nullable(),
  caught_year: z.number().nullable(),
  vintage_year: z.number().nullable(),
  catch_date_known: z.boolean(),
  inventory_status: z.string(),
  first_seen_at: z.string(),
  last_changed_at: z.string(),
  disappeared_at: z.string().nullable(),
  fast_move: move.nullable(),
  charged_moves: z.array(move),
  second_move_unlocked: z.boolean().nullable(),
  max_moves: z.array(z.object({ type: z.string(), level: z.number() })),
  tag_ids: z.array(bigId),
  tag_labels: z.array(z.string()),
  metadata: metadata.nullable(),
  cleanup: z
    .object({
      status: z.string(),
      priority: z.number(),
      confidence: z.string(),
      protection: z.array(z.string()),
      summary: z.string().nullable(),
      battle_score: z.number().nullable(),
      keep_score: z.number().nullable(),
    })
    .nullable(),
  pvp: z.object({ great: leagueSummary, ultra: leagueSummary, master: leagueSummary }),
  is_new: z.boolean(),
});
export type PokemonSummary = z.infer<typeof pokemonSummary>;
export type Move = z.infer<typeof move>;
export type Metadata = z.infer<typeof metadata>;

export const pokemonPage = z.object({
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  items: z.array(pokemonSummary),
  game_data_version: z.number().nullable(),
});
export type PokemonPage = z.infer<typeof pokemonPage>;

const reason = z.object({ code: z.string(), text: z.string(), data: z.record(z.string(), z.unknown()).optional() });
export type Reason = z.infer<typeof reason>;

/** One part of a battle or keep score. Battle parts are values from 0 to 100, keep parts points. */
const scorePart = z.object({ code: z.string(), text: z.string(), value: z.number(), data: z.record(z.string(), z.unknown()).optional() });
export type ScorePart = z.infer<typeof scorePart>;

export const scores = z.object({
  battle: z.object({ score: z.number().nullable(), basis: z.string().nullable(), parts: z.array(scorePart) }).optional(),
  keep: z
    .object({
      score: z.number().nullable(),
      parts: z.array(scorePart),
      keep_threshold: z.number(),
      review_threshold: z.number(),
    })
    .optional(),
  position: z.object({ rank: z.number(), of: z.number() }).nullable().optional(),
});
export type Scores = z.infer<typeof scores>;

/** Another copy of the same species, form and Shadow status. */
const similar = z.object({
  pokemon_id: z.number(),
  name: z.string(),
  cp: z.number().nullable(),
  iv_percent: z.number().nullable(),
  status: z.string(),
  battle_score: z.number().nullable().optional(),
  keep_score: z.number().nullable().optional(),
  caught_year: z.number().nullable().optional(),
  favorite: z.boolean().optional(),
  better: z.boolean().optional(),
});
export type Similar = z.infer<typeof similar>;

export const pokemonDetail = pokemonSummary.extend({
  details: z.record(z.string(), z.unknown()),
  recommendation: z
    .object({
      status: z.string(),
      priority: z.number(),
      confidence: z.string(),
      battle_score: z.number().nullable(),
      keep_score: z.number().nullable(),
      scores: scores,
      protection_reasons: z.array(reason),
      reasons: z.array(reason),
      roles: z.array(z.record(z.string(), z.unknown())),
      alternatives: z.array(similar),
      warnings: z.array(reason),
      computed_at: z.string(),
    })
    .nullable(),
  planned_actions: z.array(z.object({ list: z.string(), action: z.string(), status: z.string() })),
});
export type PokemonDetail = z.infer<typeof pokemonDetail>;

export const cleanupItem = z.object({
  pokemon: pokemonSummary,
  status: z.string(),
  priority: z.number(),
  confidence: z.string(),
  battle_score: z.number().nullable(),
  keep_score: z.number().nullable(),
  scores: scores,
  protection_reasons: z.array(reason),
  reasons: z.array(reason),
  roles: z.array(z.record(z.string(), z.unknown())),
  alternatives: z.array(similar),
  warnings: z.array(reason),
  group_key: z.string().nullable(),
  in_action_list: z.boolean(),
});
export type CleanupItem = z.infer<typeof cleanupItem>;

export const cleanupPage = z.object({
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  items: z.array(cleanupItem),
  analysis: z.object({
    run_id: z.number().nullable(),
    computed_at: z.string().nullable(),
    engine_version: z.string(),
    game_data_version: z.number().nullable(),
    rules_hash: z.string().nullable(),
    stale: z.boolean(),
    pending: z.boolean(),
    counts: z.record(z.string(), z.number()),
  }),
});
export type CleanupPage = z.infer<typeof cleanupPage>;

/** Pokémon the user must confirm one by one before they go on a transfer list (ADR-0019). */
export const confirmationItem = z.object({
  pokemon_id: z.number(),
  name: z.string(),
  cp: z.number().nullable(),
  caught_year: z.number().nullable(),
  kinds: z.array(z.string()),
  message: z.string(),
  // What changed since an earlier confirmation of the same Pokémon.
  new_reasons: z.array(z.string()).default([]),
});
export type ConfirmationItem = z.infer<typeof confirmationItem>;

export const actionList = z.object({
  list_name: z.string(),
  count: z.number(),
  items: z.array(
    z.object({
      pokemon: pokemonSummary,
      action: z.string(),
      status: z.string(),
      reason: z.string().nullable(),
      protection: z.array(z.string()),
      still_in_inventory: z.boolean(),
      // Checked again on every read: a protection that appeared later holds the item back.
      blocked: z.string().nullable(),
      needs_confirmation: confirmationItem.nullable(),
      executable: z.boolean(),
    }),
  ),
  search_hint: z.object({
    note: z.string(),
    safety_suffix: z.string(),
    queries: z.array(z.object({ species_id: z.number(), query: z.string() })),
  }),
});
export type ActionList = z.infer<typeof actionList>;

export const actionListUpdate = actionList.extend({
  skipped: z.array(z.object({ pokemon_id: z.number(), reason: z.string() })),
  needs_confirmation: z.array(confirmationItem),
});
export type ActionListUpdate = z.infer<typeof actionListUpdate>;

const pokedexStep = z.object({
  from_key: z.string(),
  to_key: z.string(),
  to_name: z.string(),
  candy: z.number().nullable(),
  candy_purified: z.number().nullable(),
  item: z.string().nullable(),
  item_name: z.string().nullable(),
  item_cost: z.number().nullable(),
  item_have: z.number().nullable().optional(),
  lure: z.string().nullable(),
  lure_name: z.string().nullable(),
  buddy_km: z.number().nullable(),
  conditions: z.array(z.string()),
  quest: z.string().nullable(),
  no_candy_cost_via_trade: z.boolean(),
});

const pokedexMove = z.object({ key: z.string(), name: z.string(), type: z.string().nullable(), elite: z.boolean(), legacy: z.boolean() });

export const pokedexSearch = z.object({
  game_data_version: z.number(),
  results: z.array(z.object({ dex: z.number(), name: z.string(), types: z.array(z.string()) })),
});

export const pokedexSpecies = z.object({
  game_data_version: z.number(),
  dex: z.number(),
  name: z.string(),
  forms: z.array(z.object({ key: z.string(), name: z.string() })),
  form: z.object({
    key: z.string(),
    name: z.string(),
    label: z.string().nullable(),
    types: z.array(z.string()),
    stats: z.object({ atk: z.number().nullable(), def: z.number().nullable(), sta: z.number().nullable() }).nullable(),
    class: z.string().nullable(),
    family: z.string().nullable(),
    deployable: z.boolean().nullable(),
    tradable: z.boolean().nullable(),
    transferable: z.boolean().nullable(),
    buddy_km: z.number().nullable(),
    third_move: z.object({ stardust: z.number().nullable().optional(), candy: z.number().nullable().optional() }).nullable(),
    shadow: z.object({ purify_stardust: z.number().nullable(), purify_candy: z.number().nullable() }).nullable(),
    mega: z.array(z.string()),
  }),
  moves: z.object({ fast: z.array(pokedexMove), charged: z.array(pokedexMove) }),
  cp_table: z.array(z.object({ level: z.number(), label: reason, cp: z.number() })),
  leagues: z.array(
    z.object({
      league: z.string(),
      name: z.string(),
      max_cp: z.number().nullable(),
      species_rank: z.number().nullable(),
      shadow_rank: z.number().nullable(),
      moveset: z.array(z.string()),
    }),
  ),
  gym: z.object({ rank: z.number(), target_key: z.string(), target_name: z.string(), is_evolution: z.boolean() }).nullable(),
  evolves_from: z.array(z.object({ key: z.string(), dex: z.number(), name: z.string() })),
  evolves_to: z.array(pokedexStep.extend({ dex: z.number() })),
  collection: z
    .object({
      account_id: z.number(),
      owned_total: z.number(),
      owned: z.array(pokemonSummary.extend({ same_form: z.boolean() })),
      candidate_total: z.number(),
      candidates: z.array(
        z.object({
          pokemon: pokemonSummary,
          steps: z.array(pokedexStep),
          total_candy: z.number().nullable(),
          cp_after: z.number().nullable(),
          hp_after: z.number().nullable(),
        }),
      ),
      candy: z.object({ family: z.string().nullable(), quantity: z.number().nullable() }),
      items_known: z.boolean(),
    })
    .nullable(),
});
export type PokedexSpecies = z.infer<typeof pokedexSpecies>;
export type PokedexStep = z.infer<typeof pokedexStep>;
