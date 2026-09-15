/**
 * Lobster tier configuration (10 tiers).
 *
 * Tier is a pure function of changePercent (avg_score - baseline) * 100.
 * One input → one tier → one sprite. See docs/lobster-gym-tier-design.md.
 */

export type LobsterTierId =
  | 'T0' | 'T1' | 'T2' | 'T3' | 'T4'
  | 'T5' | 'T6' | 'T7' | 'T8' | 'T9';

export type Accessory =
  | 'sweatband'
  | 'dumbbells'
  | 'wraps'
  | 'chain'
  | 'gloves'
  | 'vest'
  | 'crown'
  | 'lightning'
  | 'wings';

export type PosePreset = 'idle' | 'stand' | 'curl' | 'bench' | 'flex' | 'shout' | 'roar';

export interface LobsterTier {
  /** Tier id, T0 (weakest) → T9 (dragon-form). */
  id: LobsterTierId;
  /** Numeric tier for ordering / size scaling. */
  level: number;
  /** Display name. */
  name: string;
  /** Short single-emoji icon used in legends / badges. */
  emoji: string;
  /** Inclusive lower bound (percentage points). */
  minChange: number;
  /** Exclusive upper bound (percentage points). */
  maxChange: number;
  /** Linear size scale applied to the SVG; T0 ≈ 0.7, T9 ≈ 2.2. */
  scale: number;
  /** Body / shell main color. */
  bodyColor: string;
  /** Belly / softer accent. */
  bellyColor: string;
  /** Claw outline. */
  outlineColor: string;
  /** Cumulative — includes lower-tier accessories. */
  accessories: Accessory[];
  /** Pose preset used by the SVG component to pick the body silhouette. */
  pose: PosePreset;
  /** Optional aura effect rendered behind the lobster. */
  aura: 'none' | 'sparks' | 'fire' | 'golden' | 'electric' | 'cosmic';
}

/**
 * Tiers in ascending order. Ranges are [min, max).
 *
 * Accessories are cumulative — each tier's list contains every accessory
 * from the tiers below it, so the SVG component can just render the array
 * without checking history.
 */
export const LOBSTER_TIERS: LobsterTier[] = [
  {
    id: 'T0', level: 0, name: 'Weakling', emoji: '😵',
    minChange: -Infinity, maxChange: 0,
    scale: 0.70,
    bodyColor: '#6b7280', bellyColor: '#9ca3af', outlineColor: '#374151',
    accessories: [],
    pose: 'idle', aura: 'none',
  },
  {
    id: 'T1', level: 1, name: 'Rookie', emoji: '🙂',
    minChange: 0, maxChange: 5,
    scale: 0.85,
    bodyColor: '#fb7185', bellyColor: '#fecdd3', outlineColor: '#9f1239',
    accessories: ['sweatband'],
    pose: 'stand', aura: 'none',
  },
  {
    id: 'T2', level: 2, name: 'Trainee', emoji: '💪',
    minChange: 5, maxChange: 10,
    scale: 1.00,
    bodyColor: '#f97316', bellyColor: '#fed7aa', outlineColor: '#9a3412',
    accessories: ['sweatband', 'dumbbells'],
    pose: 'curl', aura: 'none',
  },
  {
    id: 'T3', level: 3, name: 'Toned', emoji: '😎',
    minChange: 10, maxChange: 15,
    scale: 1.15,
    bodyColor: '#ef4444', bellyColor: '#fca5a5', outlineColor: '#991b1b',
    accessories: ['sweatband', 'dumbbells', 'wraps'],
    pose: 'bench', aura: 'none',
  },
  {
    id: 'T4', level: 4, name: 'Muscular', emoji: '🔥',
    minChange: 15, maxChange: 20,
    scale: 1.30,
    bodyColor: '#be123c', bellyColor: '#fb7185', outlineColor: '#500724',
    accessories: ['sweatband', 'dumbbells', 'wraps', 'chain'],
    pose: 'flex', aura: 'sparks',
  },
  {
    id: 'T5', level: 5, name: 'Brawler', emoji: '🥊',
    minChange: 20, maxChange: 25,
    scale: 1.45,
    bodyColor: '#831843', bellyColor: '#be185d', outlineColor: '#4c0519',
    accessories: ['sweatband', 'dumbbells', 'wraps', 'chain', 'gloves'],
    pose: 'shout', aura: 'sparks',
  },
  {
    id: 'T6', level: 6, name: 'Titan', emoji: '🛡️',
    minChange: 25, maxChange: 30,
    scale: 1.65,
    bodyColor: '#7c2d12', bellyColor: '#c2410c', outlineColor: '#1c1917',
    accessories: ['sweatband', 'dumbbells', 'wraps', 'chain', 'gloves', 'vest'],
    pose: 'roar', aura: 'fire',
  },
  {
    id: 'T7', level: 7, name: 'King', emoji: '👑',
    minChange: 30, maxChange: 35,
    scale: 1.85,
    bodyColor: '#a16207', bellyColor: '#fbbf24', outlineColor: '#422006',
    accessories: ['sweatband', 'dumbbells', 'wraps', 'chain', 'gloves', 'vest', 'crown'],
    pose: 'roar', aura: 'golden',
  },
  {
    id: 'T8', level: 8, name: 'Ascendant', emoji: '⚡',
    minChange: 35, maxChange: 40,
    scale: 2.05,
    bodyColor: '#581c87', bellyColor: '#fbbf24', outlineColor: '#1e0838',
    accessories: ['sweatband', 'dumbbells', 'wraps', 'chain', 'gloves', 'vest', 'crown', 'lightning'],
    pose: 'roar', aura: 'electric',
  },
  {
    id: 'T9', level: 9, name: 'Dragon Lord', emoji: '🐉',
    minChange: 40, maxChange: Infinity,
    scale: 2.25,
    bodyColor: '#facc15', bellyColor: '#fef9c3', outlineColor: '#581c87',
    accessories: ['sweatband', 'dumbbells', 'wraps', 'chain', 'gloves', 'vest', 'crown', 'lightning', 'wings'],
    pose: 'roar', aura: 'cosmic',
  },
];

/** Resolve a tier by change percentage. Always returns a tier (T9 for >=40). */
export function getLobsterTier(changePercent: number): LobsterTier {
  for (const tier of LOBSTER_TIERS) {
    if (changePercent >= tier.minChange && changePercent < tier.maxChange) {
      return tier;
    }
  }
  return LOBSTER_TIERS[LOBSTER_TIERS.length - 1];
}
