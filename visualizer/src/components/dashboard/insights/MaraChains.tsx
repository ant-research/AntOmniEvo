import React, { useCallback, useEffect, useMemo, useState } from 'react';
import type { Candidate, IterationRecord } from '../../../types';
import { getBatchScores, getCandidateDetail } from '../../../utils/api';
import { FileViewer } from '../FileViewer';

interface LineageCompareProps {
  candidates: Candidate[];
  onSelectCandidate?: (id: string) => void;
  iterationRecords?: IterationRecord[];
}

function fmtDuration(sec: number | null | undefined): string {
  if (sec == null || Number.isNaN(sec)) return '—';
  const total = Math.max(0, Math.floor(sec));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => n.toString().padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

interface ChainInfo {
  nodes: Candidate[];       // [depth0, depth1, ..., depth_max] — oldest first
  candidate: Candidate;     // the candidate this chain is built from (last node)
  parentOfRoot: Candidate | null; // depth 0's parent (the baseline)
  maxDepth: number;
  newestCreatedAt: string;
}

interface ReflectionStats {
  commonCount: number;      // number of common data IDs
  parentSum: number;        // parent's score sum on common data
  depth0Sum: number;        // depth 0's score sum on common data
  maxSum: number;           // max score sum across all depths on common data
  delta1: number;           // depth0Sum - parentSum
  delta2: number;           // maxSum - parentSum
  reflectionValue: number;  // delta2 - delta1
}

function computeReflectionStats(
  chain: ChainInfo,
  detailScores: Map<string, Record<string, number>>,
): ReflectionStats | null {
  if (!chain.parentOfRoot) return null;

  const parentId = chain.parentOfRoot.meta.candidate_id;
  const parentScores = detailScores.get(parentId);
  if (!parentScores) return null;

  const depth0Scores = detailScores.get(chain.nodes[0].meta.candidate_id);
  if (!depth0Scores) return null;

  // Common data IDs = parent ∩ depth0 (both are always complete)
  const commonArr = Object.keys(parentScores).filter(id => id in depth0Scores);
  if (commonArr.length === 0) return null;

  const parentSum = commonArr.reduce((sum, id) => sum + parentScores[id], 0);
  const depth0Sum = commonArr.reduce((sum, id) => sum + depth0Scores[id], 0);

  // For max: include a depth node only if it has all common IDs (skip incomplete ones)
  let maxSum = depth0Sum;
  for (let i = 1; i < chain.nodes.length; i++) {
    const scores = detailScores.get(chain.nodes[i].meta.candidate_id);
    if (!scores) continue;
    const hasAll = commonArr.every(id => id in scores);
    if (!hasAll) continue;
    const nodeSum = commonArr.reduce((sum, id) => sum + scores[id], 0);
    if (nodeSum > maxSum) maxSum = nodeSum;
  }

  const delta1 = depth0Sum - parentSum;
  const delta2 = maxSum - parentSum;

  return {
    commonCount: commonArr.length,
    parentSum,
    depth0Sum,
    maxSum,
    delta1,
    delta2,
    reflectionValue: delta2 - delta1,
  };
}

function buildChains(candidates: Candidate[]): ChainInfo[] {
  const candidateMap = new Map(candidates.map(c => [c.meta.candidate_id, c]));

  // Build mara chains from candidates with reflection_depth >= 1
  // Group by depth-0 root, keep only the deepest chain per group
  const rootToChain = new Map<string, ChainInfo>();
  const inMaraChain = new Set<string>();

  for (const cand of candidates) {
    const depth = cand.meta.reflection_depth ?? 0;
    if (depth === 0) continue;

    const chainLength = depth + 1;
    const chain: Candidate[] = [cand];
    let current = cand;
    for (let i = 1; i < chainLength && current.meta.parent_id; i++) {
      const parent = candidateMap.get(current.meta.parent_id);
      if (!parent) break;
      chain.push(parent);
      current = parent;
    }

    chain.reverse(); // oldest first (chain[0] = depth 0)

    const root = chain[0];
    const rootId = root.meta.candidate_id;
    const existing = rootToChain.get(rootId);

    // Keep the deepest chain per root
    if (existing && existing.maxDepth >= depth) continue;

    const parentOfRoot = root.meta.parent_id ? candidateMap.get(root.meta.parent_id) ?? null : null;

    rootToChain.set(rootId, {
      nodes: chain,
      candidate: cand,
      parentOfRoot,
      maxDepth: depth,
      newestCreatedAt: cand.meta.created_at,
    });

    // Track all candidates that are part of a mara chain
    for (const node of chain) inMaraChain.add(node.meta.candidate_id);
  }

  // Add single-node entries for depth=0 candidates NOT already in a mara chain
  for (const cand of candidates) {
    const depth = cand.meta.reflection_depth ?? 0;
    if (depth !== 0) continue;
    if (inMaraChain.has(cand.meta.candidate_id)) continue;

    const parentOfRoot = cand.meta.parent_id ? candidateMap.get(cand.meta.parent_id) ?? null : null;

    rootToChain.set(cand.meta.candidate_id, {
      nodes: [cand],
      candidate: cand,
      parentOfRoot,
      maxDepth: 0,
      newestCreatedAt: cand.meta.created_at,
    });
  }

  const chains = [...rootToChain.values()];
  chains.sort((a, b) => b.newestCreatedAt.localeCompare(a.newestCreatedAt));
  return chains;
}


const DEFAULT_SHOW = 10;

export const LineageCompare: React.FC<LineageCompareProps> = ({ candidates, onSelectCandidate, iterationRecords }) => {
  const iterByCandidate = useMemo(() => {
    const m = new Map<string, IterationRecord>();
    for (const r of iterationRecords ?? []) {
      if (r.new_id) m.set(r.new_id, r);
    }
    return m;
  }, [iterationRecords]);
  const [searchQuery, setSearchQuery] = useState('');
  const [showCount, setShowCount] = useState(DEFAULT_SHOW);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [expandedGenerations, setExpandedGenerations] = useState<Map<number, Candidate[]>>(new Map());
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [contextContent, setContextContent] = useState<string | null>(null);
  const [contextTitle, setContextTitle] = useState<string>('');
  const [loadingCell, setLoadingCell] = useState<string | null>(null);

  // Detail loading for batch score comparison
  const [loadingDetails, setLoadingDetails] = useState<Set<string>>(new Set());
  const [detailScores, setDetailScores] = useState<Map<string, Record<string, number>>>(new Map());

  const candidateMap = useMemo(
    () => new Map(candidates.map(c => [c.meta.candidate_id, c])),
    [candidates],
  );

  const allChains = useMemo(() => buildChains(candidates), [candidates]);

  // Preload batch scores for all chains + their parents via batch API
  useEffect(() => {
    const idsToLoad = new Set<string>();
    for (const chain of allChains) {
      if (chain.parentOfRoot) idsToLoad.add(chain.parentOfRoot.meta.candidate_id);
      for (const node of chain.nodes) idsToLoad.add(node.meta.candidate_id);
    }

    const missing = [...idsToLoad].filter(id => !detailScores.has(id));
    if (missing.length === 0) return;

    setLoadingDetails(prev => new Set([...prev, ...missing]));

    getBatchScores(missing).then(result => {
      setDetailScores(prev => {
        const next = new Map(prev);
        for (const [id, scores] of Object.entries(result)) {
          next.set(id, scores);
        }
        return next;
      });
    }).catch(e => {
      console.error('Failed to preload batch scores:', e);
    }).finally(() => {
      setLoadingDetails(prev => {
        const next = new Set(prev);
        missing.forEach(id => next.delete(id));
        return next;
      });
    });
  }, [allChains]); // eslint-disable-line react-hooks/exhaustive-deps

  const filteredChains = useMemo(() => {
    if (!searchQuery.trim()) return allChains;
    const q = searchQuery.trim().toLowerCase();
    return allChains.filter(chain =>
      chain.nodes.some(n => n.meta.candidate_id.toLowerCase().includes(q))
    );
  }, [allChains, searchQuery]);

  const displayedChains = filteredChains.slice(0, showCount);

  // Load batch scores for expanded chain (including parent of root)
  const loadBatchScores = useCallback(async (chain: ChainInfo) => {
    const allIds = chain.nodes.map(n => n.meta.candidate_id);
    if (chain.parentOfRoot) allIds.push(chain.parentOfRoot.meta.candidate_id);
    const idsToLoad = allIds.filter(id => !detailScores.has(id));

    if (idsToLoad.length === 0) return;

    setLoadingDetails(prev => new Set([...prev, ...idsToLoad]));

    try {
      const results = await Promise.all(
        idsToLoad.map(id => getCandidateDetail(id).then(d => [id, d] as const))
      );
      setDetailScores(prev => {
        const next = new Map(prev);
        for (const [id, detail] of results) {
          const scores = (detail?.system_run_scores ?? {}) as Record<string, number>;
          next.set(id, scores);
        }
        return next;
      });
    } catch (e) {
      console.error('Failed to load batch scores:', e);
    } finally {
      setLoadingDetails(prev => {
        const next = new Set(prev);
        idsToLoad.forEach(id => next.delete(id));
        return next;
      });
    }
  }, [detailScores]);

  const handleToggleExpand = useCallback((idx: number, chain: ChainInfo) => {
    if (expandedIdx === idx) {
      setExpandedIdx(null);
    } else {
      setExpandedIdx(idx);
      loadBatchScores(chain);
    }
  }, [expandedIdx, loadBatchScores]);

  // Expand more generations (walk up from chain root)
  const handleExpandGenerations = useCallback((chainIdx: number, chain: ChainInfo) => {
    const root = chain.nodes[0];
    const existing = expandedGenerations.get(chainIdx) ?? [];
    const lastAncestor = existing.length > 0 ? existing[existing.length - 1] : root;

    if (!lastAncestor.meta.parent_id) return;
    const parent = candidateMap.get(lastAncestor.meta.parent_id);
    if (!parent) return;

    setExpandedGenerations(prev => {
      const next = new Map(prev);
      next.set(chainIdx, [...existing, parent]);
      return next;
    });

    // Also load batch scores for newly added ancestor
    if (!detailScores.has(parent.meta.candidate_id)) {
      getCandidateDetail(parent.meta.candidate_id)
        .then(d => {
          const scores = (d?.system_run_scores ?? {}) as Record<string, number>;
          setDetailScores(prev => {
            const next = new Map(prev);
            next.set(parent.meta.candidate_id, scores);
            return next;
          });
        })
        .catch(e => console.error('Failed to load ancestor scores:', e));
    }
  }, [candidateMap, expandedGenerations, detailScores]);

  // Shrink generations (remove the oldest ancestor)
  const handleShrinkGenerations = useCallback((chainIdx: number) => {
    setExpandedGenerations(prev => {
      const existing = prev.get(chainIdx) ?? [];
      if (existing.length === 0) return prev;
      const next = new Map(prev);
      next.set(chainIdx, existing.slice(0, -1));
      return next;
    });
  }, []);

  // Build batch score comparison data for expanded chain (including ancestors)
  const getExpandedNodes = useCallback((chain: ChainInfo, chainIdx: number): Candidate[] => {
    const ancestors = expandedGenerations.get(chainIdx) ?? [];
    return [...ancestors.slice().reverse(), ...chain.nodes];
  }, [expandedGenerations]);

  const getBatchComparison = useCallback((nodes: Candidate[]) => {
    const allDataIds = new Set<string>();
    for (const node of nodes) {
      const scores = detailScores.get(node.meta.candidate_id);
      if (scores) Object.keys(scores).forEach(did => allDataIds.add(did));
    }
    return [...allDataIds].sort();
  }, [detailScores]);

  const handleViewRun = useCallback(async (candidateId: string, dataId: string) => {
    const cellKey = `${candidateId}:${dataId}`;
    setLoadingCell(cellKey);
    try {
      const detail = await getCandidateDetail(candidateId);
      const valRuns = (detail.val_system_runs ?? {}) as Record<string, string[]>;
      const trainRuns = (detail.system_runs ?? {}) as Record<string, string[]>;
      const files = valRuns[dataId] ?? trainRuns[dataId] ?? [];
      if (files.length > 0) {
        setViewingFile(files[files.length - 1]);
      } else {
        setContextContent(`No system run file found for candidate ${candidateId.slice(0, 8)} on data ${dataId}.`);
        setContextTitle(`${candidateId.slice(0, 8)} · ${dataId}`);
      }
    } catch (e) {
      console.error('Failed to load system run:', e);
    } finally {
      setLoadingCell(null);
    }
  }, []);

  const handleViewContext = useCallback(async (candidateId: string, dataId: string) => {
    const cellKey = `${candidateId}:${dataId}`;
    setLoadingCell(cellKey);
    try {
      const detail = await getCandidateDetail(candidateId);
      const valRuns = (detail.val_system_runs ?? {}) as Record<string, string[]>;
      const trainRuns = (detail.system_runs ?? {}) as Record<string, string[]>;
      const files = valRuns[dataId] ?? trainRuns[dataId] ?? [];
      const specFiles = (detail.spec_files ?? []) as string[];
      const changelog = (detail.changelog ?? null) as string | null;
      const proposerRuns = (detail.proposer_runs ?? {}) as Record<string, any>;
      const analysisResults = ((proposerRuns.analysis_results ?? []) as string[])
        .filter(f => f.endsWith(`/${dataId}.json`));

      const lines = [
        `# Candidate: ${candidateId}`,
        `# Data ID: ${dataId}`,
        '',
        '## Spec files',
        ...specFiles,
        '',
        '## Run files',
        ...(files.length > 0 ? files : ['(no run files found)']),
        ...(analysisResults.length > 0 ? ['', '## Analysis', ...analysisResults] : []),
        ...(changelog ? ['', '## Changelog', changelog] : []),
      ];
      setContextContent(lines.join('\n'));
      setContextTitle(`${candidateId.slice(0, 8)} · ${dataId}`);
    } catch (e) {
      console.error('Failed to load context:', e);
    } finally {
      setLoadingCell(null);
    }
  }, []);

  // Summary stats (only mara chains count toward reflection metrics)
  const stats = useMemo(() => {
    const total = allChains.length;
    const maraChains = allChains.filter(c => c.maxDepth > 0);
    let computed = 0;
    let improved = 0;
    let totalValue = 0;

    for (const chain of maraChains) {
      const rs = computeReflectionStats(chain, detailScores);
      if (rs) {
        computed++;
        totalValue += rs.reflectionValue;
        if (rs.reflectionValue > 0) improved++;
      }
    }

    const avgImprove = computed > 0 ? totalValue / computed : 0;

    return { total, reflectionCount: maraChains.length, computed, improved, avgImprove };
  }, [allChains, detailScores]);

  return (
    <div className="mc-container">
      {/* Summary */}
      <div className="mc-summary">
        <span className="mc-stat">{stats.total} candidates</span>
        <span className="qm-summary-sep">·</span>
        <span className="mc-stat">{stats.reflectionCount} with reflection</span>
        <span className="qm-summary-sep">·</span>
        <span className="mc-stat">{stats.improved} improved</span>
        <span className="qm-summary-sep">·</span>
        <span className="mc-stat">avg reflection gain {stats.avgImprove.toFixed(2)}</span>
      </div>

      {/* Search */}
      <div className="lc-controls">
        <div className="lc-field" style={{ flex: 1 }}>
          <label className="lc-label">Search by candidate ID</label>
          <input
            className="lc-input mono"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Type candidate ID to filter..."
          />
        </div>
      </div>

      {filteredChains.length === 0 && (
        <div className="lc-empty">No candidates match &quot;{searchQuery}&quot;</div>
      )}

      {/* Chain list */}
      <div className="mc-list">
        {displayedChains.map((chain, idx) => {
          const isExpanded = expandedIdx === idx;
          const allNodes = isExpanded ? getExpandedNodes(chain, idx) : chain.nodes;
          const hasReflection = chain.maxDepth > 0;
          const rs = chain.parentOfRoot != null ? computeReflectionStats(chain, detailScores) : null;
          const dataIds = isExpanded ? getBatchComparison(allNodes) : [];
          const isLoading = chain.nodes.some(n => loadingDetails.has(n.meta.candidate_id));
          const isSingleNode = chain.nodes.length === 1;

          return (
            <div key={chain.candidate.meta.candidate_id} className="mc-card">
              {/* Header */}
              <div className="mc-header" onClick={() => handleToggleExpand(idx, chain)}>
                <div className="mc-chain-path">
                  {chain.nodes.map((node, ni) => (
                    <React.Fragment key={node.meta.candidate_id}>
                      {ni > 0 && <span className="lc-chain-arrow">→</span>}
                      <span
                        className={`mc-node mono ${ni === 0 && !isSingleNode ? 'mc-node-root' : ''} ${ni === chain.nodes.length - 1 ? 'mc-node-final' : ''}`}
                        onClick={e => { e.stopPropagation(); onSelectCandidate?.(node.meta.candidate_id); }}
                        title={`depth=${node.meta.reflection_depth ?? 0} val=${node.summary.avg_score.toFixed(4)}`}
                      >
                        {node.meta.candidate_id.slice(0, 8)}
                        {!isSingleNode && <span className="mc-depth">d{node.meta.reflection_depth ?? 0}</span>}
                        <span className="lc-chain-gen">G{node.meta.generation}</span>
                      </span>
                    </React.Fragment>
                  ))}
                </div>
                <div className="mc-header-stats">
                  {rs && hasReflection ? (
                    <>
                      <span className="mc-val-score">{rs.parentSum.toFixed(1)}</span>
                      <span className={`mc-arrow ${rs.delta1 > 0 ? 'positive' : rs.delta1 < 0 ? 'negative' : ''}`}>→</span>
                      <span className="mc-val-score">{rs.depth0Sum.toFixed(1)}</span>
                      <span className={`mc-arrow ${rs.reflectionValue > 0 ? 'positive' : rs.reflectionValue < 0 ? 'negative' : ''}`}>→</span>
                      <span className="mc-val-score">{rs.maxSum.toFixed(1)}</span>
                      <span className="mc-delta-group">
                        <span className={`mc-delta-item ${rs.delta1 > 0 ? 'positive' : rs.delta1 < 0 ? 'negative' : ''}`}>
                          Δ1={rs.delta1 > 0 ? '+' : ''}{rs.delta1.toFixed(1)}
                        </span>
                        <span className={`mc-delta-item ${rs.delta2 > 0 ? 'positive' : rs.delta2 < 0 ? 'negative' : ''}`}>
                          Δ2={rs.delta2 > 0 ? '+' : ''}{rs.delta2.toFixed(1)}
                        </span>
                        <span className={`mc-delta-item mc-delta-gain ${rs.reflectionValue > 0 ? 'positive' : rs.reflectionValue < 0 ? 'negative' : ''}`}>
                          gain={rs.reflectionValue > 0 ? '+' : ''}{rs.reflectionValue.toFixed(1)}
                        </span>
                      </span>
                    </>
                  ) : rs ? (
                    <>
                      <span className="mc-val-score">{rs.parentSum.toFixed(1)}</span>
                      <span className={`mc-arrow ${rs.delta1 > 0 ? 'positive' : rs.delta1 < 0 ? 'negative' : ''}`}>→</span>
                      <span className="mc-val-score">{rs.depth0Sum.toFixed(1)}</span>
                      <span className="mc-delta-group">
                        <span className={`mc-delta-item ${rs.delta1 > 0 ? 'positive' : rs.delta1 < 0 ? 'negative' : ''}`}>
                          Δ={rs.delta1 > 0 ? '+' : ''}{rs.delta1.toFixed(1)}
                        </span>
                      </span>
                    </>
                  ) : null}
                  <span className="mc-expand-icon">{isExpanded ? '▾' : '▸'}</span>
                </div>
              </div>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="mc-detail">
                  {/* Generation controls */}
                  <div className="mc-gen-controls">
                    <span className="mc-gen-label">Generations: {allNodes.length}</span>
                    {(expandedGenerations.get(idx) ?? []).length > 0 && (
                      <button className="mc-gen-btn" onClick={() => handleShrinkGenerations(idx)}>−</button>
                    )}
                    {allNodes[0].meta.parent_id && (
                      <button className="mc-gen-btn" onClick={() => handleExpandGenerations(idx, chain)}>+</button>
                    )}
                  </div>

                  {/* Reflection stats */}
                  {rs && (
                    <div className="mc-iter-info">
                      <span>Common: {rs.commonCount} IDs</span>
                      <span className="qm-summary-sep">·</span>
                      <span>Parent: {rs.parentSum.toFixed(1)}</span>
                      <span className="qm-summary-sep">·</span>
                      <span>Δ1(d0−parent): {rs.delta1 > 0 ? '+' : ''}{rs.delta1.toFixed(2)}</span>
                      <span className="qm-summary-sep">·</span>
                      <span>Δ2(max−parent): {rs.delta2 > 0 ? '+' : ''}{rs.delta2.toFixed(2)}</span>
                      <span className="qm-summary-sep">·</span>
                      <span className={rs.reflectionValue > 0 ? 'mc-accepted' : rs.reflectionValue < 0 ? 'mc-rejected' : ''}>
                        Reflection gain: {rs.reflectionValue > 0 ? '+' : ''}{rs.reflectionValue.toFixed(2)}
                      </span>
                    </div>
                  )}

                  {/* Chain-level iteration + duration (the whole mara chain shares one iteration record) */}
                  {(() => {
                    const leafIter = iterByCandidate.get(chain.candidate.meta.candidate_id);
                    if (!leafIter) return null;
                    return (
                      <div className="mc-iter-info">
                        <span
                          title={`proposer ${fmtDuration(leafIter.proposer_duration_seconds)} / total ${fmtDuration(leafIter.duration_seconds)}`}
                        >
                          iteration <strong>{leafIter.iteration}</strong>
                          <span className="qm-summary-sep">·</span>
                          cost <strong>{fmtDuration(leafIter.duration_seconds)}</strong>
                        </span>
                      </div>
                    );
                  })()}

                  {/* Batch score comparison table */}
                  {isLoading && <div className="lc-empty">Loading batch scores...</div>}

                  {!isLoading && dataIds.length > 0 && (
                    <div className="lc-scroll" style={{ maxHeight: '400px' }}>
                      <table className="qm-table">
                        <thead>
                          <tr>
                            <th className="qm-th-question">Data ID</th>
                            {allNodes.map(node => (
                              <th key={node.meta.candidate_id} className="qm-th-cand">
                                <div className="qm-cand-id mono">
                                  <span
                                    className={onSelectCandidate ? 'qm-cand-id-link' : ''}
                                    onClick={onSelectCandidate ? () => onSelectCandidate(node.meta.candidate_id) : undefined}
                                  >{node.meta.candidate_id.slice(0, 8)}</span>
                                </div>
                                <div className="qm-cand-id mono" style={{ opacity: 0.6, fontSize: '0.68rem' }}>
                                  G{node.meta.generation} d{node.meta.reflection_depth ?? 0}
                                </div>
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {dataIds.map(dataId => {
                            return (
                              <tr key={dataId}>
                                <td className="qm-td-question mono">{dataId}</td>
                                {allNodes.map(node => {
                                  const scores = detailScores.get(node.meta.candidate_id);
                                  const score = scores?.[dataId] ?? -1;
                                  const cellKey = `${node.meta.candidate_id}:${dataId}`;
                                  const isCellLoading = loadingCell === cellKey;
                                  return (
                                    <td key={node.meta.candidate_id} className="qm-td-cell">
                                      {isCellLoading ? (
                                        <span className="qm-dot qm-dot-loading">...</span>
                                      ) : score < 0 ? (
                                        <span className="qm-dot qm-dot-none">-</span>
                                      ) : (
                                        <span className="qm-cell-content">
                                          <span className={`qm-score-val ${score >= 1 ? 'perfect' : score >= 0.5 ? 'pass' : 'fail'}`}>
                                            {score.toFixed(2)}
                                          </span>
                                          <span className="qm-cell-actions">
                                            <button
                                              className="qm-cell-btn"
                                              title="View system run"
                                              onClick={() => handleViewRun(node.meta.candidate_id, dataId)}
                                            >▶</button>
                                            <button
                                              className="qm-cell-btn"
                                              title="View context"
                                              onClick={() => handleViewContext(node.meta.candidate_id, dataId)}
                                            >⋯</button>
                                          </span>
                                        </span>
                                      )}
                                    </td>
                                  );
                                })}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {!isLoading && dataIds.length === 0 && (
                    <div className="lc-empty">No batch run data available.</div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Show more / Show less */}
      <div className="mc-pagination">
        {showCount > DEFAULT_SHOW && (
          <button className="mc-show-more" onClick={() => setShowCount(DEFAULT_SHOW)}>
            Show less
          </button>
        )}
        {filteredChains.length > showCount && (
          <button className="mc-show-more" onClick={() => setShowCount(prev => prev + 10)}>
            Show more ({filteredChains.length - showCount} remaining)
          </button>
        )}
      </div>

      <FileViewer path={viewingFile} onClose={() => setViewingFile(null)} />
      <FileViewer
        path={null}
        inlineContent={contextContent}
        inlineTitle={contextTitle}
        onClose={() => setContextContent(null)}
      />
    </div>
  );
};
