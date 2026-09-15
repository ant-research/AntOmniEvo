import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Statistics } from '../../../types';
import { getCandidateDetail } from '../../../utils/api';
import { DetailPanel } from '../DetailPanel';
import { AncestorChain } from './AncestorChain';
import { TreeNode } from './TreeNode';
import type { CandidateWithChange } from '../types';

interface LineageTreeTabProps {
  candidates: CandidateWithChange[];
  statistics: Statistics | null;
  rootScore: number;
}

export const LineageTreeTab: React.FC<LineageTreeTabProps> = ({
  candidates,
  statistics,
  rootScore,
}) => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, any> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [expandedSet, setExpandedSet] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [activeMatchIdx, setActiveMatchIdx] = useState(0);
  const treePanelRef = useRef<HTMLDivElement>(null);

  const parentMap = useMemo(() => {
    const map = new Map<string, string[]>();
    candidates.forEach(c => {
      if (c.meta.parent_id) {
        if (!map.has(c.meta.parent_id)) map.set(c.meta.parent_id, []);
        map.get(c.meta.parent_id)!.push(c.meta.candidate_id);
      }
    });
    return map;
  }, [candidates]);

  const candidateMap = useMemo(() => {
    const map = new Map<string, CandidateWithChange>();
    candidates.forEach(c => map.set(c.meta.candidate_id, c));
    return map;
  }, [candidates]);

  const rootId = statistics?.root_candidate_id || candidates.find(c => !c.meta.parent_id)?.meta.candidate_id;

  // Default expansion: root + first 2 levels
  useEffect(() => {
    if (!rootId) return;
    const initial = new Set<string>();
    const seed = (id: string, depth: number) => {
      if (depth >= 2) return;
      initial.add(id);
      (parentMap.get(id) || []).forEach(child => seed(child, depth + 1));
    };
    seed(rootId, 0);
    setExpandedSet(initial);
  }, [rootId, parentMap]);

  const toggleNode = useCallback((id: string, recursive: boolean) => {
    setExpandedSet(prev => {
      const next = new Set(prev);
      const isOpen = next.has(id);
      if (recursive) {
        const stack = [id];
        const subtree: string[] = [];
        while (stack.length) {
          const cur = stack.pop()!;
          subtree.push(cur);
          (parentMap.get(cur) || []).forEach(c => stack.push(c));
        }
        if (isOpen) subtree.forEach(n => next.delete(n));
        else subtree.forEach(n => next.add(n));
      } else {
        if (isOpen) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }, [parentMap]);

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

  // Match candidate_id by prefix or substring (case-insensitive).
  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return [] as string[];
    return candidates
      .map(c => c.meta.candidate_id)
      .filter(id => id.toLowerCase().includes(q));
  }, [search, candidates]);

  // Reset cursor when the query (and therefore the match list) changes.
  useEffect(() => {
    setActiveMatchIdx(0);
  }, [search]);

  const revealCandidate = useCallback((id: string) => {
    if (!candidateMap.has(id)) return;
    // Expand every ancestor so the node is visible.
    setExpandedSet(prev => {
      const next = new Set(prev);
      let cur: string | null | undefined = id;
      // Include the node itself so its children stay collapsed but the node renders.
      while (cur) {
        next.add(cur);
        const parent: string | null = candidateMap.get(cur)?.meta.parent_id ?? null;
        cur = parent;
      }
      return next;
    });
    setHighlightId(id);
    // Scroll into view on the next paint after expansion has applied.
    requestAnimationFrame(() => {
      const root = treePanelRef.current;
      if (!root) return;
      const el = root.querySelector<HTMLElement>(`[data-node-id="${id}"]`);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }, [candidateMap]);

  // Auto-reveal the active match as the user types or steps through.
  useEffect(() => {
    if (matches.length === 0) {
      setHighlightId(null);
      return;
    }
    const idx = Math.min(activeMatchIdx, matches.length - 1);
    revealCandidate(matches[idx]);
  }, [matches, activeMatchIdx, revealCandidate]);

  const stepMatch = useCallback((delta: number) => {
    if (matches.length === 0) return;
    setActiveMatchIdx(idx => (idx + delta + matches.length) % matches.length);
  }, [matches.length]);

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (matches.length === 0) return;
      const idx = Math.min(activeMatchIdx, matches.length - 1);
      const id = matches[idx];
      if (e.shiftKey) stepMatch(-1);
      else if (matches.length > 1) stepMatch(1);
      // Enter also selects the active match for inspection.
      handleSelect(id);
    } else if (e.key === 'Escape') {
      setSearch('');
      setHighlightId(null);
    }
  };

  if (candidates.length === 0) {
    return (
      <div className="lineage-tab empty">
        <p>No candidates found</p>
      </div>
    );
  }

  const selectedCandidate = selectedId ? candidateMap.get(selectedId) : null;

  return (
    <div className="lineage-tab">
      <div className="lineage-header">
        <h3>🧬 Lineage Tree</h3>
        <span className="lineage-summary">
          {candidates.length} candidates · root score {rootScore.toFixed(4)}
          <span className="lineage-hint"> · shift+click ▸ to expand subtree</span>
        </span>
        <div className="lineage-search">
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder="🔍 search candidate id (Enter to select)"
            className="lineage-search-input"
          />
          {search && (
            <span className="lineage-search-meta">
              {matches.length === 0
                ? 'no match'
                : `${Math.min(activeMatchIdx, matches.length - 1) + 1} / ${matches.length}`}
              {matches.length > 1 && (
                <>
                  <button className="lineage-search-step" onClick={() => stepMatch(-1)} title="Previous (shift+enter)">↑</button>
                  <button className="lineage-search-step" onClick={() => stepMatch(1)} title="Next (enter)">↓</button>
                </>
              )}
              <button className="lineage-search-clear" onClick={() => { setSearch(''); setHighlightId(null); }} title="Clear (esc)">✕</button>
            </span>
          )}
        </div>
      </div>
      <div className="lineage-body">
        <div className="lineage-tree-panel" ref={treePanelRef}>
          {rootId && (
            <TreeNode
              nodeId={rootId}
              candidateMap={candidateMap}
              parentMap={parentMap}
              depth={0}
              selectedId={selectedId}
              onSelect={handleSelect}
              expandedSet={expandedSet}
              onToggle={toggleNode}
              highlightId={highlightId}
            />
          )}
        </div>
        <div className={`lineage-detail-panel ${selectedId ? 'open' : ''}`}>
          {selectedId && selectedCandidate ? (
            <>
              <AncestorChain
                candidateId={selectedId}
                candidateMap={candidateMap}
                onNavigate={(id) => { revealCandidate(id); handleSelect(id); }}
              />
              <DetailPanel
                candidate={selectedCandidate}
                detail={detail}
                detailLoading={detailLoading}
                rootScore={rootScore}
                onClose={() => { setSelectedId(null); setDetail(null); }}
              />
            </>
          ) : (
            <div className="detail-placeholder">
              <span className="detail-placeholder-icon">👈</span>
              <p>Click a node to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
