import React, { useMemo, useState } from 'react';
import type { Candidate } from '../../../types';
import { calculateChangePercent, getEvolutionLevel } from '../../../utils/evolutionLevel';
import { openCandidateDirectory } from '../../../utils/api';

// State dot colors matching lineage tree
const STATE_COLORS: Record<string, string> = {
  evolving: '#facc15',
  pending: '#4ade80',
};

interface CandidateListCardProps {
  label: string;
  candidates: Candidate[];
  rootScore: number;
}

export const CandidateListCard: React.FC<CandidateListCardProps> = ({
  label,
  candidates,
  rootScore,
}) => {
  const [open, setOpen] = useState(false);

  const sorted = useMemo(
    () => [...candidates].sort((a, b) => b.summary.avg_score - a.summary.avg_score),
    [candidates]
  );

  return (
    <div className={`stat-card stat-card-wide candidate-list-card expandable ${open ? 'open' : ''}`}>
      <div className="candidate-list-header" onClick={() => setOpen(v => !v)}>
        <div className="stat-label">{label}</div>
        <div className="candidate-list-count">
          <span className="stat-value">{candidates.length}</span>
          <span className={`candidate-list-arrow ${open ? 'open' : ''}`}>▸</span>
        </div>
      </div>
      {open && sorted.length > 0 && (
        <div className="candidate-list-body">
          {sorted.map(c => {
            const pct = calculateChangePercent(c.summary.avg_score, rootScore);
            const lvl = getEvolutionLevel(pct);
            const stateColor = STATE_COLORS[c.meta.state] || '#666';
            return (
              <div key={c.meta.candidate_id} className="candidate-list-row">
                <span className="candidate-list-dot" style={{ background: stateColor }} />
                <span className="candidate-list-state-label" style={{ color: stateColor }}>{c.meta.state}</span>
                <span className="candidate-list-id mono">{c.meta.candidate_id.slice(0, 8)}</span>
                <span className="candidate-list-gen">G{c.meta.generation || 0}</span>
                <span className="candidate-list-score">{c.summary.avg_score.toFixed(4)}</span>
                <span className={`candidate-list-change ${pct >= 0 ? 'positive' : 'negative'}`}>
                  {pct >= 0 ? '+' : ''}{pct.toFixed(2)} pp
                </span>
                <span className="candidate-list-state-badge" style={{ background: lvl.color }}>
                  {lvl.emoji} {lvl.label}
                </span>
                <button
                  className="candidate-list-open-dir"
                  title="Open candidate directory"
                  onClick={(e) => {
                    e.stopPropagation();
                    openCandidateDirectory(c.meta.candidate_id).catch(err =>
                      console.error('Failed to open directory:', err)
                    );
                  }}
                >
                  📂
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
