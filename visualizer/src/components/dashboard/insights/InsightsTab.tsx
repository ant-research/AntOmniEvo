import React, { useCallback, useMemo, useState } from 'react';
import type { CandidateWithChange } from '../types';
import type { Statistics } from '../../../types';
import { getCandidateDetail } from '../../../utils/api';
import { DetailPanel } from '../DetailPanel';
import { AncestorChain } from '../lineage/AncestorChain';
import { CollapsibleSection } from '../CollapsibleSection';
import { CoverageGrid } from './CoverageGrid';
import { LineageCompare } from './MaraChains';

interface InsightsTabProps {
  candidates: CandidateWithChange[];
  rootScore: number;
  statistics: Statistics | null;
}

export const InsightsTab: React.FC<InsightsTabProps> = ({ candidates, rootScore, statistics }) => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, any> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const candidateMap = useMemo(
    () => new Map(candidates.map(c => [c.meta.candidate_id, c])),
    [candidates],
  );

  const handleSelectCandidate = useCallback(async (id: string) => {
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

  const selectedCandidate = selectedId ? candidateMap.get(selectedId) : null;

  return (
    <div className="insights-tab">
      <CollapsibleSection title="Val Coverage Grid" defaultOpen={false}>
        <CoverageGrid candidates={candidates} onSelectCandidate={handleSelectCandidate} />
      </CollapsibleSection>

      <CollapsibleSection title="Lineage Compare" defaultOpen={false}>
        <LineageCompare
          candidates={candidates}
          onSelectCandidate={handleSelectCandidate}
          iterationRecords={statistics?.iteration_record_list ?? []}
        />
      </CollapsibleSection>

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
