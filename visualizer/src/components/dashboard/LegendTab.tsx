import React from 'react';
import type { LobsterTierId } from '../../utils/lobsterTier';
import { LOBSTER_TIERS } from '../../utils/lobsterTier';
import { GYM_TIERS } from '../../utils/gymTier';
import { LOBSTER_SPRITES } from '../../utils/spriteRegistry';
import { GymRenderer } from './GymRenderer';
import { useTranslation } from '../../i18n';

const formatRange = (minChange: number, maxChange: number): string => {
  if (maxChange === Infinity) return `≥ +${minChange} pp`;
  if (minChange === -Infinity) return `< ${maxChange} pp`;
  const lo = minChange >= 0 ? `+${minChange}` : `${minChange}`;
  const hi = maxChange >= 0 ? `+${maxChange}` : `${maxChange}`;
  return `${lo} ~ ${hi} pp`;
};

const LEGEND_SIZE: Record<LobsterTierId, number> = {
  T0: 100, T1: 90, T2: 110, T3: 120,
  T4: 135, T5: 140, T6: 170, T7: 185,
  T8: 220, T9: 350,
};

const ANIM_SIZE: Record<LobsterTierId, number> = {
  T0: 120, T1: 110, T2: 130, T3: 140,
  T4: 155, T5: 160, T6: 200, T7: 220,
  T8: 310, T9: 480,
};

export const LegendTab: React.FC = () => {
  const { t } = useTranslation();
  return (
  <div className="legend-tab">
    {/* ── Lobster Tiers ────────────────────────────────────── */}
    <div className="legend-tab-intro">
      <h2>{t('legend.lobsterTiers')}</h2>
      <p>{t('legend.tiersIntro')}</p>
    </div>

    <div className="legend-lobster-grid">
      {LOBSTER_TIERS.map(tier => {
        const displaySize = LEGEND_SIZE[tier.id] ?? 120;
        return (
          <div key={tier.id} className={`legend-lobster-card legend-lobster-${tier.id.toLowerCase()}`} style={{ position: 'relative' }}>
            <div className="legend-lobster-preview">
              <img
                src={`/sprites/lobsters/${tier.id.toLowerCase()}.png`}
                alt={tier.name}
                width={displaySize}
                height={displaySize}
                style={{ objectFit: 'contain', marginTop: tier.id === 'T9' ? 50 : undefined }}
                draggable={false}
              />
            </div>
            <div className="legend-lobster-badge">
              <span className="legend-lobster-id">{tier.id}</span>
              <span className="legend-lobster-name">{t(`tiers.${tier.id}`)}</span>
              <span className="legend-lobster-emoji">{tier.emoji}</span>
              <span className="legend-lobster-range">{formatRange(tier.minChange, tier.maxChange)}</span>
            </div>
          </div>
        );
      })}
    </div>

    {/* ── Evolving Animations ─────────────────────────────── */}
    <div className="legend-tab-intro" style={{ marginTop: 32 }}>
      <h2>{t('legend.trainingAnimations')}</h2>
      <p>{t('legend.animationsIntro')}</p>
    </div>

    <div className="legend-lobster-grid" style={{ justifyContent: 'center' }}>
      {LOBSTER_TIERS.filter(tier => {
        const s = LOBSTER_SPRITES[tier.id];
        return s?.enabled && s?.srcEvolving;
      }).map(tier => {
        const sprite = LOBSTER_SPRITES[tier.id];
        const displaySize = ANIM_SIZE[tier.id] ?? 120;
        return (
          <div key={tier.id} className={`legend-lobster-card legend-anim-card legend-lobster-${tier.id.toLowerCase()}`} style={{ justifyContent: 'center', position: 'relative' }}>
            <div className="legend-lobster-preview">
              <img
                src={sprite.srcEvolving!}
                alt={`${tier.name} training`}
                width={displaySize}
                height={displaySize}
                style={{ objectFit: 'contain' }}
                draggable={false}
              />
            </div>
            <div className="legend-lobster-badge">
              <span className="legend-lobster-id">{tier.id}</span>
            </div>
          </div>
        );
      })}
    </div>

    {/* ── Gym Rooms ───────────────────────────────────────── */}
    <div className="legend-tab-intro" style={{ marginTop: 32 }}>
      <h2>{t('legend.gymRooms')}</h2>
      <p>{t('legend.gymIntro')}</p>
    </div>

    <div className="legend-gym-grid">
      {GYM_TIERS.map(room => (
        <div key={room.id} className="legend-gym-card">
          <div className="legend-gym-preview">
            <GymRenderer tier={room} />
          </div>
          <div className="legend-gym-overlay">
            <div className="legend-gym-banner">{room.banner}</div>
            <div className="legend-gym-name">{t(`gym.${room.id}.name`)}</div>
            <div className="legend-gym-tagline">{t(`gym.${room.id}.tagline`)}</div>
            <div className="legend-gym-id">{room.id}</div>
            <div className="legend-gym-range">{formatRange(room.minChange, room.maxChange)}</div>
          </div>
        </div>
      ))}
    </div>
  </div>
  );
};
