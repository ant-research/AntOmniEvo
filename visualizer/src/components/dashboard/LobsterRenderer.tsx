import React from 'react';
import type { LobsterTier } from '../../utils/lobsterTier';
import { lobsterSprite } from '../../utils/spriteRegistry';
import { LobsterSVG } from './LobsterSVG';

/**
 * Renders the lobster figure: an animated pixel-art sprite if one is
 * registered + enabled for this tier, otherwise the SVG fallback. This lets
 * you populate the sprite folder one tier at a time without breaking anything.
 *
 * The `state` className is mirrored onto the sprite img so the same CSS
 * animations defined for `.lobster-svg.state-evolving` can be re-applied to
 * `.lobster-sprite.state-evolving` (sprite-sheet keyframes go in
 * Dashboard.css if and when we add them).
 */
export interface LobsterRendererProps {
  tier: LobsterTier;
  state: 'pending' | 'evolving' | 'unavailable';
  size?: number;
}

export const LobsterRenderer: React.FC<LobsterRendererProps> = ({
  tier, state, size = 120,
}) => {
  const sprite = lobsterSprite(tier.id, state);
  if (sprite) {
    const scale = sprite.scale ?? 1;
    const displaySize = Math.round(size * scale);
    return (
      <img
        className={`lobster-sprite tier-${tier.id.toLowerCase()} state-${state}`}
        src={sprite.src}
        alt={tier.name}
        width={displaySize}
        height={displaySize}
        style={{
          objectFit: 'contain',
          margin: `${-(displaySize - size) / 2}px`,
        }}
        draggable={false}
      />
    );
  }
  return <LobsterSVG tier={tier} state={state} size={size} />;
};
