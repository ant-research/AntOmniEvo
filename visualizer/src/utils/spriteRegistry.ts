/**
 * Sprite registry — maps tier ids to image paths under /public/sprites.
 *
 * When a tier's `enabled` flag is true, the renderer uses the image; when
 * false (or the image file is missing on disk), the renderer falls back to
 * the SVG component. Edit the `enabled` flags as you populate the sprite
 * folders.
 *
 * Paths are relative to /public so they're served verbatim by Vite. No
 * import or bundling required — drop a PNG in /public/sprites/lobsters/t6.png
 * and flip its flag here to make it live.
 */

import type { LobsterTierId } from './lobsterTier';
import type { GymTierId } from './gymTier';

export interface SpriteEntry {
  /** Set to false to keep using the SVG fallback for this tier. */
  enabled: boolean;
  /** Path served from /public (static/default). */
  src: string;
  /** Optional animated sprite for idle/pending state. */
  srcIdle?: string;
  /** Optional animated sprite for evolving/training state. */
  srcEvolving?: string;
  /** Render scale factor — sprites that were shrunk to fit the canvas get scaled up at display time. */
  scale?: number;
}

export const LOBSTER_SPRITES: Record<LobsterTierId, SpriteEntry> = {
  T0: { enabled: true, src: '/sprites/lobsters/t0.png', srcIdle: '/sprites/lobsters/t0_idle.png', srcEvolving: '/sprites/lobsters/t0_evolving.png' },
  T1: { enabled: true, src: '/sprites/lobsters/t1.png', srcIdle: '/sprites/lobsters/t1_idle.png', srcEvolving: '/sprites/lobsters/t1_evolving.png' },
  T2: { enabled: true, src: '/sprites/lobsters/t2.png', srcIdle: '/sprites/lobsters/t2_idle.png', srcEvolving: '/sprites/lobsters/t2_evolving.png' },
  T3: { enabled: true, src: '/sprites/lobsters/t3.png', srcIdle: '/sprites/lobsters/t3_idle.png', srcEvolving: '/sprites/lobsters/t3_evolving.png' },
  T4: { enabled: true, src: '/sprites/lobsters/t4.png', srcIdle: '/sprites/lobsters/t4_idle.png', srcEvolving: '/sprites/lobsters/t4_evolving.png', scale: 1.18 },
  T5: { enabled: true, src: '/sprites/lobsters/t5.png', srcIdle: '/sprites/lobsters/t5_idle.png', srcEvolving: '/sprites/lobsters/t5_evolving.png', scale: 1.12 },
  T6: { enabled: true, src: '/sprites/lobsters/t6.png', srcIdle: '/sprites/lobsters/t6_idle.png', srcEvolving: '/sprites/lobsters/t6_evolving.png', scale: 1.16 },
  T7: { enabled: true, src: '/sprites/lobsters/t7.png', srcIdle: '/sprites/lobsters/t7_idle.png', srcEvolving: '/sprites/lobsters/t7_evolving.png', scale: 1.08 },
  T8: { enabled: true, src: '/sprites/lobsters/t8.png', srcIdle: '/sprites/lobsters/t8_idle.png', srcEvolving: '/sprites/lobsters/t8_evolving.png', scale: 1.57 },
  T9: { enabled: true, src: '/sprites/lobsters/t9.png', srcIdle: '/sprites/lobsters/t9_idle.png', srcEvolving: '/sprites/lobsters/t9_evolving.png', scale: 1.85 },
};

export const GYM_SPRITES: Record<GymTierId, SpriteEntry> = {
  R0: { enabled: true, src: '/sprites/gyms/r0.png' },
  R1: { enabled: true, src: '/sprites/gyms/r1.png' },
  R2: { enabled: true, src: '/sprites/gyms/r2.png' },
  R3: { enabled: true, src: '/sprites/gyms/r3.png' },
  R4: { enabled: true, src: '/sprites/gyms/r4.png' },
  R5: { enabled: true, src: '/sprites/gyms/r5.png' },
};

export function lobsterSprite(tierId: LobsterTierId, state?: 'pending' | 'evolving' | 'unavailable'): SpriteEntry | null {
  const entry = LOBSTER_SPRITES[tierId];
  if (!entry?.enabled) return null;
  if (state === 'evolving' && entry.srcEvolving) {
    return { ...entry, src: entry.srcEvolving };
  }
  if ((state === 'pending' || state === 'unavailable') && entry.srcIdle) {
    return { ...entry, src: entry.srcIdle };
  }
  return entry;
}

export function gymSprite(tierId: GymTierId): SpriteEntry | null {
  const entry = GYM_SPRITES[tierId];
  return entry?.enabled ? entry : null;
}
