import React, { useMemo, useState } from 'react';
import type { CandidateWithChange } from '../types';

interface AncestorChainProps {
  candidateId: string;
  candidateMap: Map<string, CandidateWithChange>;
  onNavigate?: (id: string) => void;
}

export const AncestorChain: React.FC<AncestorChainProps> = ({
  candidateId,
  candidateMap,
  onNavigate,
}) => {
  const [expanded, setExpanded] = useState(false);

  const chain = useMemo(() => {
    const result: CandidateWithChange[] = [];
    let currentId: string | null = candidateId;
    while (currentId) {
      const cand = candidateMap.get(currentId);
      if (!cand) break;
      result.push(cand);
      currentId = cand.meta.parent_id;
    }
    return result;
  }, [candidateId, candidateMap]);

  if (chain.length <= 1) return null;

  return (
    <div className="ancestor-chain">
      <button
        className="ancestor-chain-toggle"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="ancestor-chain-icon">{expanded ? '▾' : '▸'}</span>
        Ancestors ({chain.length - 1})
      </button>
      {expanded && (
        <div className="ancestor-chain-list">
          {chain.map((c, i) => {
            const isCurrent = i === 0;
            return (
              <div
                key={c.meta.candidate_id}
                className={`ancestor-chain-item ${isCurrent ? 'current' : ''} ${!isCurrent && onNavigate ? 'clickable' : ''}`}
                onClick={!isCurrent && onNavigate ? () => onNavigate(c.meta.candidate_id) : undefined}
              >
                <span className="ancestor-chain-connector">
                  {i === 0 ? '' : '│'}
                </span>
                <span className="ancestor-chain-node">
                  <span className="ancestor-chain-id mono">{c.meta.candidate_id.slice(0, 8)}</span>
                  <span className="ancestor-chain-gen">G{c.meta.generation ?? 0}</span>
                  <span className="ancestor-chain-score">{c.summary.avg_score.toFixed(4)}</span>
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
