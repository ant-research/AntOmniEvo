import React from 'react';
import type { Accessory, LobsterTier } from '../../utils/lobsterTier';

/**
 * Side-view lobster sprite.
 *
 * Composition model:
 *   - one body silhouette built from <ellipse>/<path>, tinted by tier colors
 *   - accessory <g> groups layered on top in a fixed z-order
 *   - per-state CSS classes drive the per-frame animation (kept in Dashboard.css)
 *
 * The component is intentionally stateless — all visual variation comes from
 * the resolved tier object. State (`pending`/`evolving`) only flips a CSS
 * class on the root group so animation CSS can target it.
 */
export interface LobsterSVGProps {
  tier: LobsterTier;
  /** 'evolving' → train animation, 'pending' → idle breathing, 'unavailable' → static. */
  state: 'pending' | 'evolving' | 'unavailable';
  /** Rendered width in px. Height = width (square viewBox). */
  size?: number;
}

const VIEWBOX = 200;

/** z-order: accessories on top of body, aura behind body. */
const ACCESSORY_ORDER: Accessory[] = [
  'wraps', 'gloves', 'chain', 'vest', 'dumbbells', 'sweatband', 'crown', 'lightning', 'wings',
];

export const LobsterSVG: React.FC<LobsterSVGProps> = ({ tier, state, size = 120 }) => {
  const accSet = new Set(tier.accessories);
  const visibleAccessories = ACCESSORY_ORDER.filter(a => accSet.has(a));
  const stateClass = `lobster-svg state-${state}`;
  const poseClass = `pose-${tier.pose}`;

  return (
    <svg
      className={`${stateClass} ${poseClass}`}
      width={size}
      height={size}
      viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`}
      style={{ overflow: 'visible' }}
    >
      <defs>
        <linearGradient id={`body-grad-${tier.id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={tier.bodyColor} />
          <stop offset="100%" stopColor={tier.outlineColor} />
        </linearGradient>
        <radialGradient id={`belly-grad-${tier.id}`}>
          <stop offset="0%" stopColor={tier.bellyColor} />
          <stop offset="100%" stopColor={tier.bodyColor} />
        </radialGradient>
        <radialGradient id={`aura-grad-${tier.id}`}>
          <stop offset="0%" stopColor={auraColor(tier.aura)} stopOpacity="0.6" />
          <stop offset="70%" stopColor={auraColor(tier.aura)} stopOpacity="0.1" />
          <stop offset="100%" stopColor={auraColor(tier.aura)} stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Aura behind everything */}
      {tier.aura !== 'none' && (
        <circle
          className={`lobster-aura aura-${tier.aura}`}
          cx={VIEWBOX / 2}
          cy={VIEWBOX / 2}
          r={VIEWBOX * 0.55}
          fill={`url(#aura-grad-${tier.id})`}
        />
      )}

      {/* Particle ring for T9 cosmic. */}
      {tier.aura === 'cosmic' && <CosmicRing color={tier.bodyColor} />}

      {/* The body group is the one that animates. */}
      <g className="lobster-body-group">
        {/* Tail fan */}
        <path
          d="M 50 110 Q 20 95 25 130 Q 35 145 55 135 Z"
          fill={`url(#body-grad-${tier.id})`}
          stroke={tier.outlineColor}
          strokeWidth="2"
        />
        {/* Tail segments */}
        <path
          d="M 55 100 Q 70 95 80 105 L 85 130 Q 70 140 55 130 Z"
          fill={`url(#body-grad-${tier.id})`}
          stroke={tier.outlineColor}
          strokeWidth="2"
        />
        <path
          d="M 75 95 Q 95 90 105 100 L 110 128 Q 90 138 75 128 Z"
          fill={`url(#body-grad-${tier.id})`}
          stroke={tier.outlineColor}
          strokeWidth="2"
        />

        {/* Main body shell */}
        <ellipse
          cx="120"
          cy="105"
          rx="42"
          ry="32"
          fill={`url(#body-grad-${tier.id})`}
          stroke={tier.outlineColor}
          strokeWidth="2.5"
        />
        {/* Belly highlight */}
        <ellipse
          cx="120"
          cy="118"
          rx="32"
          ry="14"
          fill={`url(#belly-grad-${tier.id})`}
          opacity="0.7"
        />

        {/* Antennae */}
        <path
          d="M 148 88 Q 165 60 175 50"
          fill="none"
          stroke={tier.outlineColor}
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M 152 90 Q 175 75 188 70"
          fill="none"
          stroke={tier.outlineColor}
          strokeWidth="2"
          strokeLinecap="round"
        />

        {/* Eye stalks + eyes */}
        <line x1="142" y1="92" x2="148" y2="78" stroke={tier.outlineColor} strokeWidth="2" />
        <circle cx="149" cy="76" r="5" fill="#fff" stroke={tier.outlineColor} strokeWidth="1.5" />
        <circle cx="150" cy="76" r="2.5" fill="#0f172a" />
        <line x1="135" y1="93" x2="138" y2="78" stroke={tier.outlineColor} strokeWidth="2" />
        <circle cx="139" cy="76" r="5" fill="#fff" stroke={tier.outlineColor} strokeWidth="1.5" />
        <circle cx="140" cy="76" r="2.5" fill="#0f172a" />

        {/* Front legs */}
        <line x1="105" y1="130" x2="100" y2="155" stroke={tier.outlineColor} strokeWidth="3" strokeLinecap="round" />
        <line x1="120" y1="135" x2="120" y2="160" stroke={tier.outlineColor} strokeWidth="3" strokeLinecap="round" />
        <line x1="135" y1="135" x2="140" y2="158" stroke={tier.outlineColor} strokeWidth="3" strokeLinecap="round" />

        {/* Left claw (held back) */}
        <g className="lobster-claw lobster-claw-left">
          <line x1="100" y1="110" x2="75" y2="80" stroke={tier.outlineColor} strokeWidth="4" strokeLinecap="round" />
          <Claw cx={70} cy={75} fill={`url(#body-grad-${tier.id})`} outline={tier.outlineColor} />
        </g>

        {/* Right claw (held forward) — this is the one we put dumbbells/gloves on. */}
        <g className="lobster-claw lobster-claw-right">
          <line x1="155" y1="115" x2="180" y2="130" stroke={tier.outlineColor} strokeWidth="4" strokeLinecap="round" />
          <Claw cx={185} cy={132} fill={`url(#body-grad-${tier.id})`} outline={tier.outlineColor} />
          {/* Accessories that attach to the right claw render inside this group */}
          {visibleAccessories.includes('gloves') && <Gloves cx={185} cy={132} />}
          {visibleAccessories.includes('wraps') && <Wraps x={170} y={120} />}
          {visibleAccessories.includes('dumbbells') && <Dumbbell cx={185} cy={150} color={tier.outlineColor} />}
        </g>

        {/* Body-attached accessories */}
        {visibleAccessories.includes('vest') && <Vest body={tier.bellyColor} outline={tier.outlineColor} />}
        {visibleAccessories.includes('chain') && <Chain />}
        {visibleAccessories.includes('sweatband') && <Sweatband />}
        {visibleAccessories.includes('crown') && <Crown />}
        {visibleAccessories.includes('lightning') && <ShoulderLightning />}
        {visibleAccessories.includes('wings') && <Wings color={tier.bodyColor} />}
      </g>

      {/* Sweat drops only when training */}
      {state === 'evolving' && <SweatDrops />}
    </svg>
  );
};

// ───────── helpers ─────────

function auraColor(aura: LobsterTier['aura']): string {
  switch (aura) {
    case 'sparks': return '#fbbf24';
    case 'fire': return '#f97316';
    case 'golden': return '#fde047';
    case 'electric': return '#d946ef';
    case 'cosmic': return '#c084fc';
    default: return '#ffffff';
  }
}

interface ClawProps { cx: number; cy: number; fill: string; outline: string }
const Claw: React.FC<ClawProps> = ({ cx, cy, fill, outline }) => (
  <g>
    <path
      d={`M ${cx - 10} ${cy + 8} Q ${cx - 18} ${cy - 12} ${cx + 4} ${cy - 14} Q ${cx + 10} ${cy - 2} ${cx + 6} ${cy + 6} Z`}
      fill={fill}
      stroke={outline}
      strokeWidth="2"
    />
    <path
      d={`M ${cx - 4} ${cy + 12} Q ${cx - 14} ${cy + 4} ${cx + 2} ${cy - 6} Q ${cx + 10} ${cy + 4} ${cx + 4} ${cy + 14} Z`}
      fill={fill}
      stroke={outline}
      strokeWidth="2"
    />
  </g>
);

const Sweatband: React.FC = () => (
  <g>
    <rect x="100" y="68" width="42" height="9" rx="3" fill="#3b82f6" stroke="#1e3a8a" strokeWidth="1.5" />
    <line x1="105" y1="72" x2="139" y2="72" stroke="#fff" strokeWidth="1.5" opacity="0.7" />
  </g>
);

interface DumbbellProps { cx: number; cy: number; color: string }
const Dumbbell: React.FC<DumbbellProps> = ({ cx, cy, color }) => (
  <g className="dumbbell-prop">
    <rect x={cx - 14} y={cy - 4} width="28" height="8" rx="2" fill="#1f2937" />
    <rect x={cx - 20} y={cy - 9} width="10" height="18" rx="2" fill="#0f172a" stroke={color} strokeWidth="1" />
    <rect x={cx + 10} y={cy - 9} width="10" height="18" rx="2" fill="#0f172a" stroke={color} strokeWidth="1" />
  </g>
);

interface WrapsProps { x: number; y: number }
const Wraps: React.FC<WrapsProps> = ({ x, y }) => (
  <g>
    {[0, 5, 10].map(d => (
      <line key={d} x1={x} y1={y + d} x2={x + 14} y2={y + d + 4} stroke="#fbbf24" strokeWidth="2" />
    ))}
  </g>
);

interface GlovesProps { cx: number; cy: number }
const Gloves: React.FC<GlovesProps> = ({ cx, cy }) => (
  <g>
    <circle cx={cx} cy={cy} r="14" fill="#dc2626" stroke="#7f1d1d" strokeWidth="2" />
    <path d={`M ${cx - 8} ${cy + 2} Q ${cx} ${cy + 10} ${cx + 8} ${cy + 2}`} fill="none" stroke="#7f1d1d" strokeWidth="1.5" />
  </g>
);

interface VestProps { body: string; outline: string }
const Vest: React.FC<VestProps> = ({ outline }) => (
  <g>
    <path
      d="M 92 95 L 148 95 L 152 135 L 88 135 Z"
      fill="#1f2937"
      stroke={outline}
      strokeWidth="2"
      opacity="0.85"
    />
    <line x1="120" y1="95" x2="120" y2="135" stroke="#fbbf24" strokeWidth="1.5" />
  </g>
);

const Chain: React.FC = () => (
  <g>
    {Array.from({ length: 8 }).map((_, i) => (
      <circle
        key={i}
        cx={100 + i * 6}
        cy={130 - Math.sin(i * 0.6) * 3}
        r="2.5"
        fill="#fbbf24"
        stroke="#92400e"
        strokeWidth="0.5"
      />
    ))}
  </g>
);

const Crown: React.FC = () => (
  <g>
    <path
      d="M 102 65 L 110 50 L 120 60 L 130 48 L 140 60 L 145 50 L 142 70 L 105 70 Z"
      fill="#fbbf24"
      stroke="#78350f"
      strokeWidth="1.5"
    />
    <circle cx="120" cy="58" r="3" fill="#ef4444" stroke="#78350f" strokeWidth="0.5" />
    <circle cx="110" cy="60" r="2" fill="#3b82f6" />
    <circle cx="135" cy="58" r="2" fill="#22c55e" />
  </g>
);

const ShoulderLightning: React.FC = () => (
  <g className="shoulder-lightning">
    <path d="M 90 82 L 80 100 L 88 100 L 78 118" fill="none" stroke="#fde047" strokeWidth="2.5" strokeLinecap="round" />
    <path d="M 150 82 L 160 100 L 152 100 L 162 118" fill="none" stroke="#fde047" strokeWidth="2.5" strokeLinecap="round" />
  </g>
);

interface WingsProps { color: string }
const Wings: React.FC<WingsProps> = ({ color }) => (
  <g className="dragon-wings">
    <path
      d="M 90 90 Q 45 50 35 90 Q 50 110 90 110 Z"
      fill={color}
      stroke="#581c87"
      strokeWidth="2"
      opacity="0.85"
    />
    <path
      d="M 150 90 Q 195 50 205 90 Q 190 110 150 110 Z"
      fill={color}
      stroke="#581c87"
      strokeWidth="2"
      opacity="0.85"
    />
  </g>
);

const SweatDrops: React.FC = () => (
  <g className="sweat-drops">
    <circle cx="155" cy="60" r="3" fill="#7dd3fc" />
    <circle cx="170" cy="75" r="2.5" fill="#7dd3fc" />
    <circle cx="92" cy="65" r="2.5" fill="#7dd3fc" />
  </g>
);

interface CosmicRingProps { color: string }
const CosmicRing: React.FC<CosmicRingProps> = ({ color }) => (
  <g className="cosmic-ring">
    {Array.from({ length: 12 }).map((_, i) => {
      const angle = (i * Math.PI * 2) / 12;
      const r = 95;
      return (
        <circle
          key={i}
          cx={VIEWBOX / 2 + Math.cos(angle) * r}
          cy={VIEWBOX / 2 + Math.sin(angle) * r}
          r="2.5"
          fill={color}
          opacity="0.8"
        />
      );
    })}
  </g>
);
