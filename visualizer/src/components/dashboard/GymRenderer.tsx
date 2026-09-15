import React from 'react';
import type { GymTier } from '../../utils/gymTier';
import { gymSprite } from '../../utils/spriteRegistry';
import { GymBackdrop } from './GymBackdrop';

/**
 * Renders the room backdrop: a pixel-art image if a sprite is registered for
 * this tier, otherwise the SVG backdrop.
 *
 * The sprite version is rendered as an absolute-positioned <img> covering
 * the room — same CSS slot as the SVG backdrop, so the room layout doesn't
 * shift between the two.
 */
export interface GymRendererProps {
  tier: GymTier;
}

export const GymRenderer: React.FC<GymRendererProps> = ({ tier }) => {
  const sprite = gymSprite(tier.id);
  if (sprite) {
    return (
      <img
        className={`gym-backdrop gym-backdrop-${tier.id.toLowerCase()} gym-backdrop-sprite`}
        src={sprite.src}
        alt=""
        aria-hidden
        draggable={false}
      />
    );
  }
  return <GymBackdrop tier={tier} />;
};
