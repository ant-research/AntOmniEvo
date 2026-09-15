import React from 'react';
import type { GymTier } from '../../utils/gymTier';

/**
 * SVG backdrop drawn behind the lobster stage for a single gym room.
 *
 * Each tier owns a hand-composed backdrop with:
 *   - a layered wall (top gradient + texture + horizon glow)
 *   - ceiling fixtures (lights, beams, vents)
 *   - mid-wall decor (mirrors, machines, banners, columns)
 *   - a perspective floor (3-stop gradient + perspective lines + skirting board)
 *   - per-tier accent details
 *
 * Sized to fill its parent with preserveAspectRatio="none". Parent controls
 * width/height via CSS; the SVG stretches edge-to-edge.
 */
export interface GymBackdropProps {
  tier: GymTier;
}

const VW = 1200;
const VH = 420;
const HORIZON_Y = VH * 0.62;

export const GymBackdrop: React.FC<GymBackdropProps> = ({ tier }) => (
  <svg
    className={`gym-backdrop gym-backdrop-${tier.id.toLowerCase()}`}
    viewBox={`0 0 ${VW} ${VH}`}
    preserveAspectRatio="xMidYMid slice"
    aria-hidden
  >
    <defs>
      <GradientDefs id={tier.id} />
      <pattern id={`wall-tex-${tier.id}`} x="0" y="0" width="56" height="56" patternUnits="userSpaceOnUse">
        <WallTexture tierId={tier.id} />
      </pattern>
      <filter id={`soft-${tier.id}`}>
        <feGaussianBlur stdDeviation="2" />
      </filter>
      <filter id={`glow-${tier.id}`} x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="6" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>

    {/* Wall — base + texture + horizon glow */}
    <rect x="0" y="0" width={VW} height={HORIZON_Y + 8} fill={`url(#wall-grad-${tier.id})`} />
    <rect x="0" y="0" width={VW} height={HORIZON_Y + 8} fill={`url(#wall-tex-${tier.id})`} opacity="0.5" />
    <rect x="0" y={HORIZON_Y - 80} width={VW} height="80" fill={`url(#horizon-grad-${tier.id})`} />

    {/* Floor — perspective gradient */}
    <rect x="0" y={HORIZON_Y} width={VW} height={VH - HORIZON_Y} fill={`url(#floor-grad-${tier.id})`} />
    <FloorPerspective tier={tier} />

    {/* Per-tier decor */}
    {tier.id === 'R0' && <BasementDecor tier={tier} />}
    {tier.id === 'R1' && <CommunityDecor tier={tier} />}
    {tier.id === 'R2' && <StandardDecor tier={tier} />}
    {tier.id === 'R3' && <PremiumDecor tier={tier} />}
    {tier.id === 'R4' && <GoldenDecor tier={tier} />}
    {tier.id === 'R5' && <ArenaDecor tier={tier} />}

    {/* Skirting board / floor seam shadow */}
    <rect x="0" y={HORIZON_Y - 2} width={VW} height="4" fill="rgba(0,0,0,0.5)" />
    <rect x="0" y={HORIZON_Y + 4} width={VW} height="12" fill={`url(#skirt-grad-${tier.id})`} />

    {/* Bottom vignette so the lobster cards have visual ground to sit on */}
    <rect x="0" y={VH - 60} width={VW} height="60" fill={`url(#vignette-${tier.id})`} />
  </svg>
);

// ───────── palettes ─────────

interface PaletteEntry {
  wallTop: string;
  wallBot: string;
  horizon: string;
  floorNear: string;
  floorFar: string;
  skirt: string;
  vignette: string;
}

const PAL: Record<GymTier['id'], PaletteEntry> = {
  R0: {
    wallTop: '#1f2937', wallBot: '#0f172a', horizon: '#000',
    floorNear: '#0a0c10', floorFar: '#1c2430', skirt: '#000',
    vignette: 'rgba(0,0,0,0.55)',
  },
  R1: {
    wallTop: '#3f3f46', wallBot: '#27272a', horizon: '#d4a373',
    floorNear: '#3f2a1d', floorFar: '#5c4029', skirt: '#1f1410',
    vignette: 'rgba(0,0,0,0.45)',
  },
  R2: {
    wallTop: '#0c1f33', wallBot: '#04101f', horizon: '#38bdf8',
    floorNear: '#020617', floorFar: '#082f49', skirt: '#020617',
    vignette: 'rgba(2,6,23,0.6)',
  },
  R3: {
    wallTop: '#0a2e26', wallBot: '#022c22', horizon: '#34d399',
    floorNear: '#1c1209', floorFar: '#3f2a18', skirt: '#0c0703',
    vignette: 'rgba(0,0,0,0.55)',
  },
  R4: {
    wallTop: '#1c1402', wallBot: '#0a0700', horizon: '#fde047',
    floorNear: '#150e02', floorFar: '#3a2906', skirt: '#0a0700',
    vignette: 'rgba(10,7,0,0.6)',
  },
  R5: {
    wallTop: '#1e0838', wallBot: '#0a0316', horizon: '#f0abfc',
    floorNear: '#08010f', floorFar: '#2a0a4a', skirt: '#000',
    vignette: 'rgba(0,0,0,0.65)',
  },
};

const GradientDefs: React.FC<{ id: GymTier['id'] }> = ({ id }) => {
  const p = PAL[id];
  return (
    <>
      <linearGradient id={`wall-grad-${id}`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={p.wallTop} />
        <stop offset="100%" stopColor={p.wallBot} />
      </linearGradient>
      <radialGradient id={`horizon-grad-${id}`} cx="50%" cy="100%" r="70%">
        <stop offset="0%" stopColor={p.horizon} stopOpacity="0.45" />
        <stop offset="100%" stopColor={p.horizon} stopOpacity="0" />
      </radialGradient>
      <linearGradient id={`floor-grad-${id}`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={p.floorFar} />
        <stop offset="100%" stopColor={p.floorNear} />
      </linearGradient>
      <linearGradient id={`skirt-grad-${id}`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={p.skirt} stopOpacity="0.9" />
        <stop offset="100%" stopColor={p.skirt} stopOpacity="0" />
      </linearGradient>
      <linearGradient id={`vignette-${id}`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={p.vignette} stopOpacity="0" />
        <stop offset="100%" stopColor={p.vignette} stopOpacity="0.85" />
      </linearGradient>
    </>
  );
};

const WallTexture: React.FC<{ tierId: GymTier['id'] }> = ({ tierId }) => {
  switch (tierId) {
    case 'R0':
      // peeling, water-damaged plaster
      return (
        <>
          <rect width="56" height="56" fill="transparent" />
          <path d="M 6 14 Q 18 6 28 16 T 50 22" stroke="#0c0a09" strokeWidth="0.6" fill="none" opacity="0.55" />
          <path d="M 2 38 L 14 46 L 22 36" stroke="#0c0a09" strokeWidth="0.5" fill="none" opacity="0.5" />
          <circle cx="40" cy="40" r="3" fill="#000" opacity="0.25" />
        </>
      );
    case 'R1':
      // subtle vertical paneling
      return (
        <>
          <rect width="56" height="56" fill="transparent" />
          <line x1="14" y1="0" x2="14" y2="56" stroke="#000" strokeWidth="0.3" opacity="0.35" />
          <line x1="42" y1="0" x2="42" y2="56" stroke="#000" strokeWidth="0.3" opacity="0.35" />
          <line x1="14" y1="0" x2="14" y2="56" stroke="#fff" strokeWidth="0.3" opacity="0.05" transform="translate(1)" />
        </>
      );
    case 'R2':
      // brushed metal / grid panels
      return (
        <>
          <rect width="56" height="56" fill="transparent" />
          <rect x="2" y="2" width="52" height="52" fill="none" stroke="#38bdf8" strokeWidth="0.4" opacity="0.18" />
          <line x1="0" y1="28" x2="56" y2="28" stroke="#38bdf8" strokeWidth="0.3" opacity="0.1" />
          <line x1="28" y1="0" x2="28" y2="56" stroke="#38bdf8" strokeWidth="0.3" opacity="0.1" />
        </>
      );
    case 'R3':
      // marble veins
      return (
        <>
          <rect width="56" height="56" fill="transparent" />
          <path d="M 0 10 Q 14 18 28 12 T 56 16" stroke="#34d399" strokeWidth="0.4" fill="none" opacity="0.25" />
          <path d="M 0 40 Q 18 32 32 42 T 56 38" stroke="#34d399" strokeWidth="0.4" fill="none" opacity="0.2" />
        </>
      );
    case 'R4':
      // baroque damask
      return (
        <>
          <rect width="56" height="56" fill="transparent" />
          <circle cx="28" cy="28" r="10" fill="none" stroke="#fde047" strokeWidth="0.4" opacity="0.22" />
          <path d="M 28 16 Q 36 28 28 40 Q 20 28 28 16 Z" fill="none" stroke="#fde047" strokeWidth="0.3" opacity="0.2" />
          <circle cx="0" cy="0" r="2" fill="#fde047" opacity="0.15" />
          <circle cx="56" cy="56" r="2" fill="#fde047" opacity="0.15" />
        </>
      );
    case 'R5':
      // nebulous starfield
      return (
        <>
          <rect width="56" height="56" fill="transparent" />
          <circle cx="8" cy="14" r="0.8" fill="#fff" opacity="0.5" />
          <circle cx="40" cy="22" r="1.2" fill="#f0abfc" opacity="0.6" />
          <circle cx="22" cy="44" r="0.6" fill="#fff" opacity="0.45" />
          <circle cx="50" cy="50" r="0.8" fill="#fde047" opacity="0.4" />
        </>
      );
  }
};

const FloorPerspective: React.FC<{ tier: GymTier }> = ({ tier }) => {
  // Vanishing point center, faint receding lines that imply depth.
  const lines = [-540, -360, -200, -80, 80, 200, 360, 540];
  const color = tier.id === 'R5' ? '#f0abfc' : tier.id === 'R4' ? '#fde047' : tier.id === 'R3' ? '#34d399' : tier.id === 'R2' ? '#38bdf8' : '#ffffff';
  return (
    <g opacity={tier.id === 'R0' ? 0.08 : 0.16}>
      {lines.map(off => (
        <line
          key={off}
          x1={VW / 2}
          y1={HORIZON_Y}
          x2={VW / 2 + off}
          y2={VH}
          stroke={color}
          strokeWidth="0.5"
        />
      ))}
    </g>
  );
};

// ───────── decor pieces ─────────

interface DecorProps { tier: GymTier }

const BasementDecor: React.FC<DecorProps> = ({ tier }) => (
  <g>
    {/* exposed pipes along ceiling (multiple parallel) */}
    <rect x="0" y="8" width={VW} height="12" fill="#3f3f46" />
    <rect x="0" y="8" width={VW} height="2" fill="#71717a" />
    <rect x="0" y="18" width={VW} height="2" fill="#000" opacity="0.7" />
    <rect x="0" y="28" width={VW} height="6" fill="#2a2825" />
    <rect x="0" y="42" width={VW} height="4" fill="#1c1917" />
    {/* pipe joints */}
    {[120, 360, 600, 840, 1080].map(x => (
      <rect key={x} x={x - 8} y="4" width="16" height="22" fill="#52525b" />
    ))}
    {/* concrete pillars with cracks */}
    {[150, 450, 750, 1050].map(x => (
      <g key={x}>
        <rect x={x - 32} y="46" width="64" height={HORIZON_Y - 46} fill="#1c1f26" />
        <rect x={x - 34} y="46" width="68" height="12" fill="#0a0c10" />
        <rect x={x - 34} y={HORIZON_Y - 22} width="68" height="22" fill="#0a0c10" />
        <line x1={x - 26} y1="60" x2={x - 26} y2={HORIZON_Y - 26} stroke="#000" strokeWidth="1.5" opacity="0.5" />
        <line x1={x + 26} y1="60" x2={x + 26} y2={HORIZON_Y - 26} stroke="#000" strokeWidth="1.5" opacity="0.5" />
        {/* crack */}
        <path d={`M ${x} 70 L ${x - 10} 130 L ${x + 4} 180 L ${x - 8} 240`} stroke="#000" strokeWidth="0.8" fill="none" opacity="0.55" />
      </g>
    ))}
    {/* two hanging bare bulbs */}
    {[VW * 0.32, VW * 0.68].map((cx, i) => (
      <g key={i}>
        <line x1={cx} y1="46" x2={cx} y2="120" stroke="#52525b" strokeWidth="1.5" />
        <circle cx={cx} cy="132" r="14" fill="#fef3c7" opacity="0.9" filter={`url(#glow-${tier.id})`} />
        <circle cx={cx} cy="132" r="6" fill="#fff" />
        <ellipse cx={cx} cy="230" rx="200" ry="100" fill="#fef3c7" opacity="0.06" />
      </g>
    ))}
    {/* dumbbell, plates and rusted barbell on the floor */}
    <line x1="280" y1={VH - 70} x2="560" y2={VH - 70} stroke="#451a03" strokeWidth="5" />
    <circle cx="280" cy={VH - 68} r="32" fill="#3f3f46" stroke="#1c1917" strokeWidth="2" />
    <circle cx="560" cy={VH - 68} r="32" fill="#3f3f46" stroke="#1c1917" strokeWidth="2" />
    <circle cx="280" cy={VH - 68} r="6" fill="#000" />
    <circle cx="560" cy={VH - 68} r="6" fill="#000" />
    {/* scattered dumbbells */}
    {[[760, VH - 30], [820, VH - 28], [950, VH - 26]].map(([x, y]) => (
      <g key={`${x}-${y}`}>
        <rect x={x - 14} y={y - 4} width="28" height="8" rx="2" fill="#27272a" />
        <circle cx={x - 14} cy={y} r="9" fill="#3f3f46" />
        <circle cx={x + 14} cy={y} r="9" fill="#3f3f46" />
      </g>
    ))}
    {/* trash bag in corner */}
    <ellipse cx={VW - 120} cy={VH - 40} rx="38" ry="32" fill="#0a0a0a" />
    <path d={`M ${VW - 140} ${VH - 60} L ${VW - 100} ${VH - 60} L ${VW - 96} ${VH - 50} L ${VW - 144} ${VH - 50} Z`} fill="#27272a" />
    {/* water stains + mold patches on wall */}
    <ellipse cx="300" cy="80" rx="70" ry="18" fill="#000" opacity="0.35" />
    <ellipse cx="900" cy="120" rx="56" ry="14" fill="#000" opacity="0.3" />
    <ellipse cx="650" cy="60" rx="40" ry="10" fill="#000" opacity="0.3" />
    <ellipse cx="200" cy="200" rx="36" ry="56" fill="#000" opacity="0.18" />
    <ellipse cx="980" cy="220" rx="28" ry="44" fill="#000" opacity="0.18" />
    {/* graffiti scratches */}
    <path d="M 480 180 L 540 170 L 600 188 L 660 174" stroke="#dc2626" strokeWidth="1" fill="none" opacity="0.35" />
  </g>
);

const CommunityDecor: React.FC<DecorProps> = ({ tier }) => (
  <g>
    {/* drop ceiling with track lights */}
    <rect x="0" y="0" width={VW} height="16" fill="#1c1410" />
    <rect x="0" y="12" width={VW} height="4" fill="#3f3f46" />
    {[100, 350, 600, 850, 1100].map(cx => (
      <g key={cx}>
        <rect x={cx - 12} y="16" width="24" height="14" fill="#52525b" />
        <circle cx={cx} cy="30" r="7" fill="#fef3c7" filter={`url(#glow-${tier.id})`} />
        <polygon points={`${cx - 80},${HORIZON_Y - 20} ${cx + 80},${HORIZON_Y - 20} ${cx + 16},30 ${cx - 16},30`} fill="#fde68a" opacity="0.07" />
      </g>
    ))}
    {/* full-wall mirror band with floor reflection */}
    <rect x="80" y="60" width="460" height="220" fill="#cbd5e1" opacity="0.14" stroke="#71717a" strokeWidth="2" />
    <rect x="80" y="60" width="460" height="220" fill="url(#mirror-shine)" opacity="0.5" />
    <linearGradient id="mirror-shine" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stopColor="#fff" stopOpacity="0" />
      <stop offset="30%" stopColor="#fff" stopOpacity="0.15" />
      <stop offset="50%" stopColor="#fff" stopOpacity="0" />
    </linearGradient>
    <rect x="80" y="56" width="460" height="6" fill="#fbbf24" opacity="0.5" />
    {/* motivational poster */}
    <rect x="600" y="80" width="160" height="200" fill="#dc2626" stroke="#000" strokeWidth="1.5" />
    <text x="680" y="170" textAnchor="middle" fontFamily="ui-sans-serif, sans-serif" fontWeight="900" fontSize="40" fill="#fff">
      LIFT
    </text>
    <text x="680" y="215" textAnchor="middle" fontFamily="ui-sans-serif, sans-serif" fontWeight="900" fontSize="40" fill="#fff">
      HARD
    </text>
    {/* dumbbell rack with full set */}
    <g transform="translate(800, 200)">
      <rect x="0" y="0" width="320" height="80" fill="#27272a" stroke="#52525b" strokeWidth="1.5" />
      <rect x="0" y="0" width="320" height="6" fill="#3f3f46" />
      {Array.from({ length: 7 }).map((_, i) => {
        const x = 16 + i * 42;
        const sz = 4 + i;
        return (
          <g key={i}>
            <rect x={x} y={32} width="30" height="8" fill="#1f2937" />
            <circle cx={x} cy={36} r={sz + 4} fill="#0f172a" />
            <circle cx={x + 30} cy={36} r={sz + 4} fill="#0f172a" />
          </g>
        );
      })}
    </g>
    {/* small plant in corner */}
    <g transform={`translate(${VW - 110}, ${HORIZON_Y - 80})`}>
      <rect x="-22" y="40" width="44" height="40" fill="#451a03" />
      <ellipse cx="0" cy="30" rx="34" ry="20" fill="#14532d" />
      <ellipse cx="-14" cy="14" rx="22" ry="14" fill="#166534" />
      <ellipse cx="14" cy="20" rx="20" ry="12" fill="#16a34a" />
    </g>
    {/* wood plank seams */}
    {Array.from({ length: 14 }).map((_, i) => {
      const x = i * 90;
      return <line key={i} x1={x} y1={HORIZON_Y + 16} x2={x - 90} y2={VH} stroke="#1c1010" strokeWidth="1" opacity="0.55" />;
    })}
  </g>
);

const StandardDecor: React.FC<DecorProps> = ({ tier }) => (
  <g>
    {/* LED ceiling strips (two parallel) */}
    <rect x="0" y="0" width={VW} height="18" fill="#0c1f33" />
    <rect x="0" y="10" width={VW} height="3" fill="#38bdf8" opacity="1" filter={`url(#glow-${tier.id})`} />
    <rect x="0" y="32" width={VW} height="2" fill="#38bdf8" opacity="0.65" />
    {/* wall panels with cyan glow */}
    {[60, 280, 500, 720, 940, 1060].map(x => (
      <g key={x}>
        <rect x={x} y="70" width="160" height="240" fill="none" stroke="#38bdf8" strokeWidth="1" opacity="0.4" />
        <rect x={x + 6} y="76" width="148" height="228" fill="#0c1f33" opacity="0.45" />
        <line x1={x + 80} y1="86" x2={x + 80} y2="296" stroke="#38bdf8" strokeWidth="0.4" opacity="0.3" />
        <rect x={x + 8} y="78" width="144" height="4" fill="#38bdf8" opacity="0.6" />
      </g>
    ))}
    {/* digital wall clock */}
    <g transform="translate(560, 100)">
      <rect x="-50" y="-22" width="100" height="44" fill="#000" stroke="#38bdf8" strokeWidth="1.5" rx="4" />
      <text x="0" y="6" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="22" fill="#38bdf8">
        14:32
      </text>
    </g>
    {/* treadmill */}
    <g transform="translate(60, 0)">
      <rect x="0" y={HORIZON_Y - 80} width="220" height="80" fill="#0f172a" stroke="#38bdf8" strokeWidth="1.5" rx="6" />
      <rect x="20" y={HORIZON_Y - 150} width="180" height="60" fill="#1e293b" stroke="#38bdf8" strokeWidth="1.2" rx="3" />
      <rect x="50" y={HORIZON_Y - 140} width="120" height="22" fill="#000" stroke="#38bdf8" strokeWidth="0.5" />
      <text x="110" y={HORIZON_Y - 124} textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="11" fill="#38bdf8">
        8.5 km/h
      </text>
      <line x1="110" y1={HORIZON_Y - 90} x2="110" y2={HORIZON_Y - 80} stroke="#38bdf8" strokeWidth="2" />
    </g>
    {/* spin bike */}
    <g transform="translate(360, 0)">
      <circle cx="0" cy={HORIZON_Y - 40} r="40" fill="none" stroke="#38bdf8" strokeWidth="3" />
      <circle cx="0" cy={HORIZON_Y - 40} r="6" fill="#38bdf8" />
      <line x1="0" y1={HORIZON_Y - 80} x2="50" y2={HORIZON_Y - 140} stroke="#52525b" strokeWidth="6" />
      <rect x="38" y={HORIZON_Y - 154} width="40" height="10" fill="#52525b" />
      <line x1="0" y1={HORIZON_Y - 40} x2="-40" y2={HORIZON_Y - 30} stroke="#52525b" strokeWidth="4" />
    </g>
    {/* cable machine */}
    <g transform="translate(880, 0)">
      <line x1="60" y1="80" x2="60" y2={HORIZON_Y} stroke="#3f3f46" strokeWidth="8" />
      <line x1="240" y1="80" x2="240" y2={HORIZON_Y} stroke="#3f3f46" strokeWidth="8" />
      <line x1="60" y1="80" x2="240" y2="80" stroke="#3f3f46" strokeWidth="6" />
      <line x1="100" y1="80" x2="100" y2="200" stroke="#38bdf8" strokeWidth="1.5" />
      <rect x="92" y="200" width="16" height="80" fill="#0f172a" stroke="#38bdf8" strokeWidth="1" />
    </g>
    {/* mats and water bottles */}
    {[100, 280, 460, 640].map(x => (
      <rect key={x} x={x} y={VH - 32} width="140" height="16" fill="#38bdf8" opacity="0.4" rx="4" />
    ))}
    {[900, 950].map(cx => (
      <g key={cx}>
        <rect x={cx - 6} y={VH - 50} width="12" height="36" fill="#22d3ee" opacity="0.8" rx="3" />
        <rect x={cx - 8} y={VH - 56} width="16" height="8" fill="#0891b2" />
      </g>
    ))}
  </g>
);

const PremiumDecor: React.FC<DecorProps> = ({ tier }) => (
  <g>
    {/* coffered ceiling with emerald accent */}
    <rect x="0" y="0" width={VW} height="36" fill="#0a1f1a" />
    <rect x="0" y="30" width={VW} height="6" fill="#34d399" opacity="0.85" filter={`url(#glow-${tier.id})`} />
    {/* recessed lights */}
    {[80, 280, 480, 680, 880, 1080].map(cx => (
      <g key={cx}>
        <circle cx={cx} cy="36" r="9" fill="#34d399" filter={`url(#glow-${tier.id})`} />
        <circle cx={cx} cy="36" r="4" fill="#fff" />
        <polygon points={`${cx - 50},36 ${cx + 50},36 ${cx + 140},${HORIZON_Y - 16} ${cx - 140},${HORIZON_Y - 16}`} fill="#fde68a" opacity="0.05" />
      </g>
    ))}
    {/* large framed mirror left wall */}
    <rect x="50" y="80" width="280" height="220" fill="#cbd5e1" opacity="0.08" stroke="#34d399" strokeWidth="2" />
    <rect x="46" y="76" width="288" height="8" fill="#34d399" />
    <rect x="46" y="296" width="288" height="8" fill="#34d399" />
    {/* technogym-style cable pulldown machine */}
    <g transform="translate(380, 0)">
      <line x1="20" y1="40" x2="20" y2={HORIZON_Y - 6} stroke="#3f3f46" strokeWidth="10" />
      <line x1="20" y1="80" x2="170" y2="80" stroke="#3f3f46" strokeWidth="6" />
      <line x1="160" y1="80" x2="160" y2="200" stroke="#fde047" strokeWidth="1.5" />
      <rect x="148" y="200" width="24" height="90" fill="#fde047" />
      <rect x="146" y="290" width="28" height="8" fill="#854d0e" />
      {/* operator seat */}
      <rect x="60" y="240" width="80" height="14" fill="#27272a" />
      <rect x="60" y="254" width="80" height="36" fill="#27272a" />
      <line x1="100" y1="290" x2="100" y2={HORIZON_Y - 6} stroke="#52525b" strokeWidth="6" />
    </g>
    {/* squat rack center with weight stack */}
    <g transform="translate(620, 0)">
      <line x1="0" y1="40" x2="0" y2={HORIZON_Y - 6} stroke="#52525b" strokeWidth="8" />
      <line x1="160" y1="40" x2="160" y2={HORIZON_Y - 6} stroke="#52525b" strokeWidth="8" />
      <line x1="-20" y1="120" x2="180" y2="120" stroke="#27272a" strokeWidth="6" />
      <rect x="-32" y="112" width="22" height="20" fill="#0f172a" />
      <rect x="170" y="112" width="22" height="20" fill="#0f172a" />
      {/* weight plates */}
      {[-32, 192].map((x, i) => (
        <g key={i}>
          <circle cx={x} cy="122" r="28" fill="#34d399" />
          <circle cx={x} cy="122" r="20" fill="#10b981" />
          <circle cx={x} cy="122" r="6" fill="#000" />
        </g>
      ))}
      {/* safety bars */}
      <line x1="-10" y1="220" x2="170" y2="220" stroke="#52525b" strokeWidth="4" />
    </g>
    {/* bench press with bar right */}
    <g transform="translate(880, 0)">
      <rect x="0" y={HORIZON_Y - 110} width="280" height="22" fill="#27272a" rx="4" />
      <line x1="40" y1={HORIZON_Y - 88} x2="40" y2={HORIZON_Y - 10} stroke="#52525b" strokeWidth="6" />
      <line x1="240" y1={HORIZON_Y - 88} x2="240" y2={HORIZON_Y - 10} stroke="#52525b" strokeWidth="6" />
      {/* uprights with barbell */}
      <line x1="20" y1={HORIZON_Y - 200} x2="20" y2={HORIZON_Y - 100} stroke="#52525b" strokeWidth="6" />
      <line x1="260" y1={HORIZON_Y - 200} x2="260" y2={HORIZON_Y - 100} stroke="#52525b" strokeWidth="6" />
      <line x1="0" y1={HORIZON_Y - 180} x2="280" y2={HORIZON_Y - 180} stroke="#27272a" strokeWidth="5" />
      <circle cx="0" cy={HORIZON_Y - 178}  r="14" fill="#34d399" />
      <circle cx="280" cy={HORIZON_Y - 178} r="14" fill="#34d399" />
    </g>
    {/* parquet pattern on floor */}
    {Array.from({ length: 18 }).map((_, i) => (
      <line
        key={i}
        x1={i * 70}
        y1={HORIZON_Y + 16}
        x2={i * 70 - 80}
        y2={VH}
        stroke="#0c0703"
        strokeWidth="1"
        opacity="0.7"
      />
    ))}
    {/* plant in corner */}
    <g transform={`translate(${VW - 80}, ${HORIZON_Y - 60})`}>
      <rect x="-22" y="40" width="44" height="44" fill="#1c1410" />
      <ellipse cx="0" cy="30" rx="36" ry="22" fill="#14532d" />
      <ellipse cx="-18" cy="14" rx="22" ry="14" fill="#166534" />
      <ellipse cx="16" cy="20" rx="22" ry="12" fill="#16a34a" />
    </g>
  </g>
);

const GoldenDecor: React.FC<DecorProps> = ({ tier }) => (
  <g>
    {/* coffered gilded ceiling */}
    <rect x="0" y="0" width={VW} height="44" fill="#3a2906" />
    <rect x="0" y="36" width={VW} height="8" fill="#fde047" filter={`url(#glow-${tier.id})`} />
    <rect x="0" y="44" width={VW} height="3" fill="#854d0e" />
    {/* ceiling coffer squares */}
    {Array.from({ length: 8 }).map((_, i) => {
      const x = 70 + i * 140;
      return (
        <g key={i}>
          <rect x={x} y="4" width="100" height="30" fill="#1c1402" stroke="#fde047" strokeWidth="1" />
          <circle cx={x + 50} cy="20" r="4" fill="#fde047" />
        </g>
      );
    })}
    {/* gilded columns spanning floor to ceiling */}
    {[80, 380, 680, 1080].map(x => (
      <g key={x}>
        {/* shaft */}
        <rect x={x - 28} y="48" width="56" height={HORIZON_Y - 48} fill="#3a2906" />
        <rect x={x - 28} y="48" width="8" height={HORIZON_Y - 48} fill="#fde047" opacity="0.5" />
        <rect x={x + 20} y="48" width="8" height={HORIZON_Y - 48} fill="#000" opacity="0.5" />
        {/* vertical flutes */}
        {[-12, 0, 12].map(off => (
          <line key={off} x1={x + off} y1="60" x2={x + off} y2={HORIZON_Y - 28} stroke="#000" strokeWidth="0.6" opacity="0.5" />
        ))}
        {/* capital */}
        <rect x={x - 36} y="48" width="72" height="22" fill="#fde047" />
        <rect x={x - 34} y="54" width="68" height="3" fill="#854d0e" />
        <rect x={x - 38} y="44" width="76" height="6" fill="#fde047" />
        {/* base */}
        <rect x={x - 36} y={HORIZON_Y - 28} width="72" height="28" fill="#fde047" />
        <rect x={x - 34} y={HORIZON_Y - 22} width="68" height="3" fill="#854d0e" />
      </g>
    ))}
    {/* hanging chandeliers between columns */}
    {[230, 530, 880].map(cx => (
      <g key={cx}>
        <line x1={cx} y1="50" x2={cx} y2="90" stroke="#854d0e" strokeWidth="2" />
        <ellipse cx={cx} cy="110" rx="60" ry="18" fill="#fde047" opacity="0.55" filter={`url(#glow-${tier.id})`} />
        <ellipse cx={cx} cy="118" rx="68" ry="28" fill="#fde047" opacity="0.18" />
        {[-40, -16, 8, 32].map(off => (
          <g key={off}>
            <line x1={cx + off} y1="110" x2={cx + off + 4} y2="138" stroke="#854d0e" strokeWidth="1" />
            <circle cx={cx + off + 4} cy="142" r="4" fill="#fff" opacity="0.9" />
            <circle cx={cx + off + 4} cy="142" r="8" fill="#fde047" opacity="0.5" />
          </g>
        ))}
      </g>
    ))}
    {/* trophy display alcove between columns */}
    <g transform="translate(170, 0)">
      <rect x="0" y="160" width="180" height="120" fill="#1c1402" stroke="#fde047" strokeWidth="2" />
      {/* shelves */}
      <line x1="0" y1="200" x2="180" y2="200" stroke="#fde047" strokeWidth="1.5" />
      <line x1="0" y1="240" x2="180" y2="240" stroke="#fde047" strokeWidth="1.5" />
      {/* trophies */}
      {[40, 90, 140].map(cx => (
        <g key={cx}>
          <ellipse cx={cx} cy="194" rx="10" ry="3" fill="#fde047" />
          <path d={`M ${cx - 8} 192 L ${cx - 6} 178 Q ${cx} 170 ${cx + 6} 178 L ${cx + 8} 192 Z`} fill="#fde047" />
          <rect x={cx - 3} y="194" width="6" height="6" fill="#854d0e" />
        </g>
      ))}
      {[40, 90, 140].map(cx => (
        <circle key={cx} cx={cx} cy="222" r="9" fill="#fde047" stroke="#854d0e" strokeWidth="1" />
      ))}
    </g>
    {/* velvet ropes */}
    {[[440, 660], [760, 1020]].map(([x1, x2], i) => (
      <g key={i}>
        <rect x={x1 - 6} y={VH - 80} width="12" height="66" fill="#fde047" />
        <rect x={x2 - 6} y={VH - 80} width="12" height="66" fill="#fde047" />
        <circle cx={x1} cy={VH - 82} r="9" fill="#fde047" />
        <circle cx={x2} cy={VH - 82} r="9" fill="#fde047" />
        <path d={`M ${x1} ${VH - 76} Q ${(x1 + x2) / 2} ${VH - 40} ${x2} ${VH - 76}`} stroke="#b91c1c" strokeWidth="6" fill="none" />
      </g>
    ))}
    {/* marble diamond pattern on floor */}
    {Array.from({ length: 6 }).map((_, i) => (
      <line key={i} x1={VW * (i + 1) / 7} y1={HORIZON_Y + 16} x2={VW * (i + 1) / 7} y2={VH} stroke="#fde047" strokeWidth="0.5" opacity="0.3" />
    ))}
  </g>
);

const ArenaDecor: React.FC<DecorProps> = ({ tier }) => (
  <g>
    {/* jumbotron-like back banner */}
    <rect x={VW * 0.28} y="14" width={VW * 0.44} height="74" rx="10" fill="#000" stroke="#f0abfc" strokeWidth="2" filter={`url(#glow-${tier.id})`} />
    <text x={VW / 2} y="62" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="40" fill="#f0abfc" letterSpacing="14">
      CHAMPION
    </text>
    {/* side LED panels */}
    <rect x="20" y="100" width="120" height="180" fill="#000" stroke="#f0abfc" strokeWidth="1.5" />
    <rect x={VW - 140} y="100" width="120" height="180" fill="#000" stroke="#f0abfc" strokeWidth="1.5" />
    {Array.from({ length: 8 }).map((_, i) => (
      <g key={i}>
        <rect x="30" y={114 + i * 22} width="100" height="12" fill="#f0abfc" opacity={i % 2 ? 0.3 : 0.6} />
        <rect x={VW - 130} y={114 + i * 22} width="100" height="12" fill="#fde047" opacity={i % 2 ? 0.3 : 0.6} />
      </g>
    ))}
    {/* tiered audience silhouette */}
    {Array.from({ length: 4 }).map((_, row) => {
      const y = HORIZON_Y - 100 + row * 22;
      return (
        <g key={row} opacity={0.55 + row * 0.12}>
          {Array.from({ length: 80 }).map((__, i) => {
            const x = 10 + i * (VW / 80);
            const r = 7 + ((i + row) % 4);
            return <circle key={i} cx={x} cy={y} r={r} fill="#0a0316" />;
          })}
          {/* phone-screen specks in crowd */}
          {Array.from({ length: 20 }).map((__, i) => {
            const x = 30 + i * (VW / 20);
            return <circle key={`p-${i}`} cx={x + (row * 5)} cy={y - 2} r="1.2" fill="#fde047" opacity="0.6" />;
          })}
        </g>
      );
    })}
    {/* sweeping spotlights, animated by CSS class */}
    {[180, VW / 2, VW - 180].map((cx, i) => (
      <polygon
        key={cx}
        className={`arena-beam beam-${i}`}
        points={`${cx},0 ${cx - 70},${HORIZON_Y - 100} ${cx + 70},${HORIZON_Y - 100}`}
        fill="#f0abfc"
        opacity="0.22"
      />
    ))}
    {/* lightning bolts */}
    {[180, VW / 2, VW - 180].map((cx, i) => (
      <circle key={`b-${i}`} cx={cx} cy="0" r="14" fill="#f0abfc" filter={`url(#glow-${tier.id})`} />
    ))}
    {/* gold championship ring rope (front) */}
    <line x1="0" y1={VH - 110} x2={VW} y2={VH - 110} stroke="#fde047" strokeWidth="5" />
    <line x1="0" y1={VH - 86} x2={VW} y2={VH - 86} stroke="#dc2626" strokeWidth="5" />
    <line x1="0" y1={VH - 62} x2={VW} y2={VH - 62} stroke="#fde047" strokeWidth="5" />
    {/* corner posts with tassels */}
    {[20, VW - 20].map(x => (
      <g key={x}>
        <rect x={x - 10} y={VH - 130} width="20" height="120" fill="#581c87" stroke="#fde047" strokeWidth="2" />
        <circle cx={x} cy={VH - 130} r="12" fill="#fde047" />
        <path d={`M ${x - 8} ${VH - 122} L ${x} ${VH - 108} L ${x + 8} ${VH - 122} Z`} fill="#dc2626" />
      </g>
    ))}
    {/* flame border bottom */}
    <path
      d={`M 0 ${VH} ${Array.from({ length: 80 }).map((_, i) => `L ${i * 15} ${VH - 10 - (i % 2) * 8}`).join(' ')} L ${VW} ${VH} Z`}
      fill="#dc2626"
      opacity="0.75"
    />
    <path
      d={`M 0 ${VH} ${Array.from({ length: 80 }).map((_, i) => `L ${i * 15} ${VH - 6 - (i % 3) * 4}`).join(' ')} L ${VW} ${VH} Z`}
      fill="#fde047"
      opacity="0.55"
    />
  </g>
);
