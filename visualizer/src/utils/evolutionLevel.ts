/**
 * Evolution level — thin shim over lobsterTier.
 *
 * This module used to own its own 15-level ladder, but the gym view now uses
 * the 10-tier lobster ladder defined in `lobsterTier.ts` and we keep one
 * source of truth. Everything here resolves to the same LOBSTER_TIERS data.
 *
 * Old API surface (EVOLUTION_LEVELS, getLevelColor, etc.) is preserved so
 * existing callers (LegendTab, CandidateListCard, Dashboard) keep working
 * without changes beyond imports.
 */

import type { EvolutionLevel } from '../types';
import { LOBSTER_TIERS, getLobsterTier, type LobsterTier } from './lobsterTier';

/** Map a LobsterTier into the legacy EvolutionLevel shape. */
function toEvolutionLevel(tier: LobsterTier): EvolutionLevel {
  return {
    level: tier.level,
    minChange: tier.minChange,
    maxChange: tier.maxChange,
    color: tier.bodyColor,
    label: tier.name,
    emoji: tier.emoji,
  };
}

/** All 10 tiers, ordered weakest → strongest. */
export const EVOLUTION_LEVELS: EvolutionLevel[] = LOBSTER_TIERS.map(toEvolutionLevel);

/** Resolve evolution level for a given change percentage. */
export function getEvolutionLevel(changePercent: number): EvolutionLevel {
  return toEvolutionLevel(getLobsterTier(changePercent));
}

/** Absolute change in percentage points. */
export function calculateChangePercent(score: number, baseline: number): number {
  return (score - baseline) * 100;
}

function findTier(level: number): LobsterTier | undefined {
  return LOBSTER_TIERS.find(t => t.level === level);
}

/** Body color for a given level. Top tier returns a gold-violet gradient. */
export function getLevelColor(level: number): string {
  const tier = findTier(level);
  if (!tier) return '#888888';
  if (tier.id === 'T9') {
    return 'linear-gradient(135deg, #facc15, #c084fc, #facc15)';
  }
  return tier.bodyColor;
}

/** Solid hex color for a level. */
export function getLevelSolidColor(level: number): string {
  return findTier(level)?.bodyColor ?? '#888888';
}

/** Display name for a level. */
export function getLevelLabel(level: number): string {
  return findTier(level)?.name ?? 'Unknown';
}

/** Single-emoji icon for a level. */
export function getLevelEmoji(level: number): string {
  return findTier(level)?.emoji ?? '❓';
}

/** Linear size ratio for a level (mirrors the SVG sprite scale). */
export function getLevelSize(level: number): number {
  return findTier(level)?.scale ?? 1;
}

/** Compact rows for the legend tab. */
export function getLevelSummary(): { level: number; label: string; range: string; color: string }[] {
  return LOBSTER_TIERS.map(t => ({
    level: t.level,
    label: t.name,
    range:
      t.maxChange === Infinity
        ? `≥ +${t.minChange} pp`
        : t.minChange === -Infinity
          ? `< ${t.maxChange} pp`
          : `${t.minChange >= 0 ? '+' : ''}${t.minChange} ~ ${t.maxChange >= 0 ? '+' : ''}${t.maxChange} pp`,
    color: t.bodyColor,
  }));
}
