import React, { useCallback, useMemo, useState } from 'react';
import type { CandidateWithChange } from './types';
import { getCandidateDetail } from '../../utils/api';
import { DetailPanel } from './DetailPanel';
import { AncestorChain } from './lineage/AncestorChain';
import { GYM_TIERS, getGymTier, type GymTier } from '../../utils/gymTier';
import { getLobsterTier } from '../../utils/lobsterTier';
import { LobsterRenderer } from './LobsterRenderer';
import { lobsterSprite } from '../../utils/spriteRegistry';
import { GymRenderer } from './GymRenderer';

interface EvolutionTabProps {
  candidates: CandidateWithChange[];
  rootScore: number;
}

export const EvolutionTab: React.FC<EvolutionTabProps> = ({ candidates, rootScore }) => {
  const [collapsedRooms, setCollapsedRooms] = useState<Set<string>>(() => new Set(['graveyard']));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, any> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const toggleRoom = useCallback((roomId: string) => {
    setCollapsedRooms(prev => {
      const next = new Set(prev);
      if (next.has(roomId)) next.delete(roomId);
      else next.add(roomId);
      return next;
    });
  }, []);

  const candidateMap = useMemo(() => {
    const map = new Map<string, CandidateWithChange>();
    candidates.forEach(c => map.set(c.meta.candidate_id, c));
    return map;
  }, [candidates]);

  const handleSelect = useCallback(async (id: string) => {
    if (selectedId === id) {
      setSelectedId(null);
      setDetail(null);
      return;
    }
    setSelectedId(id);
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await getCandidateDetail(id);
      setDetail(d);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, [selectedId]);

  const { living, dead } = useMemo(() => {
    const living: CandidateWithChange[] = [];
    const dead: CandidateWithChange[] = [];
    candidates.forEach(c => {
      if (c.meta.state === 'unavailable') dead.push(c);
      else living.push(c);
    });
    living.sort((a, b) => b.changePercent - a.changePercent);
    dead.sort((a, b) => b.changePercent - a.changePercent);
    return { living, dead };
  }, [candidates]);

  // Bucket living candidates into 6 gym rooms by their changePercent.
  const roomGroups = useMemo(() => {
    const groups = new Map<GymTier['id'], CandidateWithChange[]>();
    living.forEach(c => {
      const tier = getGymTier(c.changePercent);
      const list = groups.get(tier.id) ?? [];
      list.push(c);
      groups.set(tier.id, list);
    });
    // Sort within each room by lobster tier descending (top dog first).
    groups.forEach(list => {
      list.sort((a, b) => getLobsterTier(b.changePercent).level - getLobsterTier(a.changePercent).level);
    });
    return groups;
  }, [living]);

  if (candidates.length === 0) {
    return (
      <div className="evolution-tab empty">
        <p>No candidates found</p>
      </div>
    );
  }

  // Render best→worst, skipping empty rooms entirely.
  const populatedRooms = [...GYM_TIERS]
    .sort((a, b) => b.rank - a.rank)
    .filter(t => (roomGroups.get(t.id)?.length ?? 0) > 0);

  const selectedCandidate = selectedId ? candidateMap.get(selectedId) : null;

  return (
    <div className="evolution-tab">
      {populatedRooms.map(tier => {
        const list = roomGroups.get(tier.id) ?? [];
        const roomKey = tier.id.toLowerCase();
        const isCollapsed = collapsedRooms.has(roomKey);
        return (
          <section key={tier.id} className={`gym-room gym-room-${roomKey} ${isCollapsed ? 'collapsed' : ''}`}>
            {!isCollapsed && <GymRenderer tier={tier} />}
            <header
              className="gym-room-header"
              onClick={() => toggleRoom(roomKey)}
              role="button"
              tabIndex={0}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') toggleRoom(roomKey); }}
            >
              <span className="gym-room-banner">{tier.banner}</span>
              <span className="gym-room-title">{tier.name}</span>
              <span className="gym-room-tagline">{tier.tagline}</span>
              <span className="gym-room-count">{list.length}</span>
              <span className={`room-toggle-arrow ${isCollapsed ? '' : 'open'}`}>▾</span>
            </header>
            {!isCollapsed && (
              <div className="gym-room-floor">
                {list.map(c => (
                  <LobsterCard
                    key={c.meta.candidate_id}
                    candidate={c}
                    selected={selectedId === c.meta.candidate_id}
                    onSelect={handleSelect}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}

      {dead.length > 0 && (
        <section className={`gym-room graveyard ${collapsedRooms.has('graveyard') ? 'collapsed' : ''}`}>
          <header
            className="gym-room-header graveyard-header"
            onClick={() => toggleRoom('graveyard')}
            role="button"
            tabIndex={0}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') toggleRoom('graveyard'); }}
          >
            <span className="gym-room-banner">🪦</span>
            <span className="gym-room-title">Graveyard</span>
            <span className="gym-room-count">{dead.length}</span>
            <span className={`room-toggle-arrow ${collapsedRooms.has('graveyard') ? '' : 'open'}`}>▾</span>
          </header>
          {!collapsedRooms.has('graveyard') && (
            <div className="gym-room-floor gym-room-graveyard">
              {dead.map(c => (
                <LobsterCard
                  key={c.meta.candidate_id}
                  candidate={c}
                  buried
                  selected={selectedId === c.meta.candidate_id}
                  onSelect={handleSelect}
                />
              ))}
            </div>
          )}
        </section>
      )}

      {selectedId && selectedCandidate && (
        <div className="lobster-detail-overlay" onClick={() => { setSelectedId(null); setDetail(null); }}>
          <div className="lobster-detail-modal" onClick={e => e.stopPropagation()}>
            <AncestorChain
              candidateId={selectedId}
              candidateMap={candidateMap}
            />
            <DetailPanel
              candidate={selectedCandidate}
              detail={detail}
              detailLoading={detailLoading}
              rootScore={rootScore}
              onClose={() => { setSelectedId(null); setDetail(null); }}
            />
          </div>
        </div>
      )}
    </div>
  );
};

interface LobsterCardProps {
  candidate: CandidateWithChange;
  buried?: boolean;
  selected?: boolean;
  onSelect?: (id: string) => void;
}

const LobsterCard: React.FC<LobsterCardProps> = ({ candidate: c, buried, selected, onSelect }) => {
  const lobster = useMemo(() => getLobsterTier(c.changePercent), [c.changePercent]);
  const state: 'pending' | 'evolving' | 'unavailable' =
    c.meta.state === 'evolving' || c.meta.state === 'unavailable' ? c.meta.state : 'pending';
  const figureSize = 121 * lobster.scale;
  // Include the sprite scale so the card width matches the actual rendered size.
  const sprite = lobsterSprite(lobster.id, state === 'evolving' ? 'evolving' : state === 'unavailable' ? 'unavailable' : 'pending');
  const displaySize = Math.round(figureSize * (sprite?.scale ?? 1));

  return (
    <div
      className={`lobster-card lobster-tier-${lobster.id.toLowerCase()} state-${state} ${buried ? 'buried' : ''} ${selected ? 'selected' : ''} ${onSelect ? 'clickable' : ''}`}
      style={{
        '--lobster-color': lobster.bodyColor,
        '--lobster-outline': lobster.outlineColor,
        '--figure-size': `${displaySize}px`,
      } as React.CSSProperties}
      onClick={() => onSelect?.(c.meta.candidate_id)}
      role={onSelect ? 'button' : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={e => {
        if (!onSelect) return;
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(c.meta.candidate_id);
        }
      }}
    >
      <div className="lobster-stage">
        {buried ? (
          <span className="lobster-tombstone">🪦</span>
        ) : (
          <LobsterRenderer tier={lobster} state={state} size={figureSize} />
        )}
        <div className="lobster-floor" />
      </div>

      <div className="lobster-info">
        <div className="lobster-id mono">{c.meta.candidate_id.slice(0, 8)}</div>
        <div className="lobster-generation">
          Gen {c.meta.generation || 0} · Epoch {c.meta.epoch} · Idx {c.meta.dataset_index}
        </div>
        <div className="lobster-score">
          <span className="score-value">{c.summary.avg_score.toFixed(4)}</span>
        </div>
        <div className="lobster-change" data-type={c.changePercent >= 0 ? 'positive' : 'negative'}>
          {c.changePercent >= 0 ? '↑' : '↓'} {Math.abs(c.changePercent).toFixed(2)} pp
        </div>
        <div className="lobster-level">
          <span className="level-badge" style={{ background: lobster.bodyColor, borderColor: lobster.outlineColor }}>
            {lobster.id} · {lobster.name}
          </span>
          {!buried && (
            <span className={`state-chip state-chip-${state}`}>
              {state === 'evolving' && '⚡ evolving'}
              {state === 'pending' && '⏳ pending'}
              {state === 'unavailable' && '— inactive'}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
