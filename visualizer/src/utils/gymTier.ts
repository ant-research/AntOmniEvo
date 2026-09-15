/**
 * Gym tier configuration (6 tiers).
 *
 * One room per 10% bucket of changePercent. Rooms with no occupants are
 * skipped at render time — there is no "empty room" placeholder.
 * See docs/lobster-gym-tier-design.md.
 */

export type GymTierId = 'R0' | 'R1' | 'R2' | 'R3' | 'R4' | 'R5';

export interface GymTier {
  id: GymTierId;
  /** Numeric rank used for sort order (R0 = lowest, R5 = highest). */
  rank: number;
  /** Display name. */
  name: string;
  /** Short tagline shown under the title. */
  tagline: string;
  /** Inclusive lower bound (pp). */
  minChange: number;
  /** Exclusive upper bound (pp). */
  maxChange: number;
  /** Single banner character displayed in the room header. */
  banner: string;
  /**
   * Theme tokens consumed by GymRoom CSS classes. The component renders
   * `gym-room-${id.toLowerCase()}` and the stylesheet owns the visual
   * details; the tokens here are mirrored for inline accents.
   */
  accentColor: string;
  /** Floor / décor secondary color. */
  floorColor: string;
};

/** Tiers in ascending order. Ranges are [min, max). */
export const GYM_TIERS: GymTier[] = [
  {
    id: 'R0', rank: 0,
    name: 'Damp Basement',
    tagline: 'still figuring it out',
    minChange: -Infinity, maxChange: 0,
    banner: '🕳️',
    accentColor: '#475569', floorColor: '#1f2937',
  },
  {
    id: 'R1', rank: 1,
    name: 'Community Corner',
    tagline: 'first reps',
    minChange: 0, maxChange: 10,
    banner: '🪵',
    accentColor: '#a3a3a3', floorColor: '#3f3f46',
  },
  {
    id: 'R2', rank: 2,
    name: 'Standard Gym',
    tagline: 'getting serious',
    minChange: 10, maxChange: 20,
    banner: '🏋️',
    accentColor: '#38bdf8', floorColor: '#075985',
  },
  {
    id: 'R3', rank: 3,
    name: 'Premium Club',
    tagline: 'membership only',
    minChange: 20, maxChange: 30,
    banner: '🥇',
    accentColor: '#34d399', floorColor: '#064e3b',
  },
  {
    id: 'R4', rank: 4,
    name: 'Golden Hall',
    tagline: 'iron royalty',
    minChange: 30, maxChange: 40,
    banner: '🏆',
    accentColor: '#fde047', floorColor: '#854d0e',
  },
  {
    id: 'R5', rank: 5,
    name: 'Champion Arena',
    tagline: 'legends only',
    minChange: 40, maxChange: Infinity,
    banner: '👑',
    accentColor: '#f0abfc', floorColor: '#581c87',
  },
];

/** Resolve a gym tier by change percentage. Always returns a tier. */
export function getGymTier(changePercent: number): GymTier {
  for (const tier of GYM_TIERS) {
    if (changePercent >= tier.minChange && changePercent < tier.maxChange) {
      return tier;
    }
  }
  return GYM_TIERS[GYM_TIERS.length - 1];
}
