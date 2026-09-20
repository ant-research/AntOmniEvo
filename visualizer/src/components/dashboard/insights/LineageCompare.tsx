import React, { useCallback, useEffect, useMemo, useState } from 'react';
import type { Candidate } from '../../../types';
import { getCandidateDetail } from '../../../utils/api';
import { FileViewer } from '../FileViewer';

interface LineageCompareProps {
  candidates: Candidate[];
  onSelectCandidate?: (id: string) => void;
}

interface RunScore {
  score: number;
  files: string[];
}

export const LineageCompare: React.FC<LineageCompareProps> = ({ candidates, onSelectCandidate }) => {
  const [inputId, setInputId] = useState('');
  const [generations, setGenerations] = useState(3);
  const [details, setDetails] = useState<Map<string, Record<string, any>>>(new Map());
  const [loading, setLoading] = useState(false);
  const [viewingFile, setViewingFile] = useState<string | null>(null);

  const candidateMap = useMemo(
    () => new Map(candidates.map(c => [c.meta.candidate_id, c])),
    [candidates],
  );

  const allIds = useMemo(
    () => candidates.map(c => c.meta.candidate_id).sort(),
    [candidates],
  );

  const chain = useMemo(() => {
    if (!inputId) return [];
    const result: Candidate[] = [];
    let currentId: string | null = inputId;
    for (let i = 0; i <= generations && currentId; i++) {
      const cand = candidateMap.get(currentId);
      if (!cand) break;
      result.push(cand);
      currentId = cand.meta.parent_id;
    }
    return result;
  }, [inputId, generations, candidateMap]);

  useEffect(() => {
    if (chain.length < 2) return;
    let cancelled = false;
    setLoading(true);

    const idsToFetch = chain
      .map(c => c.meta.candidate_id)
      .filter(id => !details.has(id));

    if (idsToFetch.length === 0) {
      setLoading(false);
      return;
    }

    Promise.all(idsToFetch.map(id => getCandidateDetail(id).then(d => [id, d] as const)))
      .then(results => {
        if (cancelled) return;
        setDetails(prev => {
          const next = new Map(prev);
          for (const [id, detail] of results) next.set(id, detail);
          return next;
        });
      })
      .catch(e => console.error('Failed to fetch details:', e))
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [chain]);

  const { sharedIds, scoreMap, avgScoreMap } = useMemo(() => {
    if (chain.length < 2) return { sharedIds: [] as string[], scoreMap: new Map(), avgScoreMap: new Map<string, number>() };

    // Collect data_ids only from system_run_scores (train)
    const candidateDataIds = chain.map(c => {
      const detail = details.get(c.meta.candidate_id);
      const trainScores = detail?.system_run_scores as Record<string, number> | undefined;
      return trainScores ? new Set(Object.keys(trainScores)) : new Set<string>();
    });

    // Union of all train data_ids across the lineage (not intersection — show all)
    const allDataIds = new Set<string>();
    for (const ids of candidateDataIds) {
      for (const id of ids) allDataIds.add(id);
    }
    const shared = [...allDataIds].sort();

    const map = new Map<string, Map<string, RunScore>>();
    // Compute average score from system_run_scores (not from iteration records / summary.avg_score)
    const avgs = new Map<string, number>();
    for (const cand of chain) {
      const detail = details.get(cand.meta.candidate_id);
      const trainScores = (detail?.system_run_scores ?? {}) as Record<string, number>;
      const scores = Object.values(trainScores);
      avgs.set(cand.meta.candidate_id, scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : -1);
    }

    for (const dataId of shared) {
      const row = new Map<string, RunScore>();
      for (const cand of chain) {
        const detail = details.get(cand.meta.candidate_id);
        const trainScores = (detail?.system_run_scores ?? {}) as Record<string, number>;
        const trainRuns = (detail?.system_runs ?? {}) as Record<string, string[]>;

        const valRuns = (detail?.val_system_runs ?? {}) as Record<string, string[]>;
        const score = trainScores[dataId] ?? -1;
        const files = trainRuns[dataId] ?? valRuns[dataId] ?? [];
        row.set(cand.meta.candidate_id, { score, files });
      }
      map.set(dataId, row);
    }

    return { sharedIds: shared, scoreMap: map, avgScoreMap: avgs };
  }, [chain, details]);

  const [contextContent, setContextContent] = useState<string | null>(null);
  const [contextTitle, setContextTitle] = useState<string>('');

  const handleViewRun = useCallback((candidateId: string, dataId: string) => {
    const row = scoreMap.get(dataId);
    if (!row) return;
    const entry = row.get(candidateId);
    if (entry && entry.files.length > 0) {
      setViewingFile(entry.files[entry.files.length - 1]);
    } else {
      setContextContent(`No system run file found for candidate ${candidateId.slice(0, 8)} on data ${dataId}.\n\nThis candidate was evaluated before run recording was enabled.`);
      setContextTitle(`${candidateId.slice(0, 8)} · ${dataId}`);
    }
  }, [scoreMap]);

  const handleViewContext = useCallback(async (candidateId: string, dataId: string) => {
    try {
      const detail = await getCandidateDetail(candidateId);
      const valRuns = (detail.val_system_runs ?? {}) as Record<string, string[]>;
      const trainRuns = (detail.system_runs ?? {}) as Record<string, string[]>;
      const files = valRuns[dataId] ?? trainRuns[dataId] ?? [];
      const artifactFiles = (detail.artifact_files ?? []) as string[];
      const changelog = (detail.changelog ?? null) as string | null;

      const lines = [
        `# Candidate: ${candidateId}`,
        `# Data ID: ${dataId}`,
        '',
        '## Artifact files',
        ...artifactFiles,
        '',
        '## Run files',
        ...(files.length > 0 ? files : ['(no run files found)']),
        ...(changelog ? ['', '## Changelog', changelog] : []),
      ];
      setContextContent(lines.join('\n'));
      setContextTitle(`${candidateId.slice(0, 8)} · ${dataId}`);
    } catch (e) {
      console.error('Failed to load context:', e);
    }
  }, []);

  const selectedCandidate = inputId ? candidateMap.get(inputId) : null;

  return (
    <div className="lc-container">
      <div className="lc-controls">
        <div className="lc-field">
          <label className="lc-label">Candidate</label>
          <input
            className="lc-input mono"
            list="lc-candidate-list"
            value={inputId}
            onChange={e => setInputId(e.target.value)}
            placeholder="Type or select candidate ID"
          />
          <datalist id="lc-candidate-list">
            {allIds.map(id => (
              <option key={id} value={id} />
            ))}
          </datalist>
        </div>
        <div className="lc-field">
          <label className="lc-label">Generations up</label>
          <input
            className="lc-input lc-input-num"
            type="number"
            min={1}
            max={20}
            value={generations}
            onChange={e => setGenerations(Math.max(1, parseInt(e.target.value) || 1))}
          />
        </div>
      </div>

      {inputId && !selectedCandidate && (
        <div className="lc-empty">Candidate not found.</div>
      )}

      {chain.length > 0 && (
        <div className="lc-chain">
          <div className="lc-chain-label">Lineage ({chain.length} candidates):</div>
          <div className="lc-chain-items">
            {chain.map((c, i) => (
              <React.Fragment key={c.meta.candidate_id}>
                {i > 0 && <span className="lc-chain-arrow">&larr;</span>}
                <span className={`lc-chain-item mono ${i === 0 ? 'lc-chain-current' : ''}`}>
                  {c.meta.candidate_id.slice(0, 8)}
                  <span className="lc-chain-gen">G{c.meta.generation}</span>
                </span>
              </React.Fragment>
            ))}
          </div>
        </div>
      )}

      {loading && <div className="lc-empty">Loading run data...</div>}

      {!loading && chain.length >= 2 && sharedIds.length > 0 && (
        <div className="lc-scroll">
          <table className="qm-table">
            <thead>
              <tr>
                <th className="qm-th-question">Data ID</th>
                {chain.map((c, i) => (
                  <th key={c.meta.candidate_id} className="qm-th-cand">
                    <div className="qm-cand-id mono">
                      {i === 0 ? 'self' : `ancestor ${i}`}
                    </div>
                    <div className="qm-cand-id mono" style={{ opacity: 0.7 }}>
                      <span
                        className={onSelectCandidate ? 'qm-cand-id-link' : ''}
                        onClick={onSelectCandidate ? () => onSelectCandidate(c.meta.candidate_id) : undefined}
                      >{c.meta.candidate_id.slice(0, 8)}</span>
                    </div>
                    <div className="qm-cand-score">{(() => { const avg = avgScoreMap.get(c.meta.candidate_id); return avg !== undefined && avg >= 0 ? avg.toFixed(4) : '—'; })()}</div>
                  </th>
                ))}
                {chain.length === 2 && (
                  <th className="qm-th-cand">
                    <div className="qm-cand-id">Delta</div>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {sharedIds.map(dataId => {
                const row = scoreMap.get(dataId)!;
                const selfEntry = row.get(chain[0].meta.candidate_id);
                const ancestorEntry = row.get(chain[chain.length - 1].meta.candidate_id);
                const selfScore = selfEntry?.score ?? -1;
                const ancestorScore = ancestorEntry?.score ?? -1;
                const hasBothScores = selfScore >= 0 && ancestorScore >= 0;
                const delta = hasBothScores ? selfScore - ancestorScore : null;
                return (
                  <tr key={dataId} className={delta !== null ? (delta > 0 ? 'lc-row-improved' : delta < 0 ? 'lc-row-regressed' : '') : ''}>
                    <td className="qm-td-question mono">{dataId}</td>
                    {chain.map(c => {
                      const entry = row.get(c.meta.candidate_id);
                      const score = entry?.score ?? -1;
                      return (
                        <td key={c.meta.candidate_id} className="qm-td-cell">
                          {score < 0 ? (
                            <span className="qm-dot qm-dot-none" title="No score">—</span>
                          ) : (
                            <span className="qm-cell-content">
                              <span
                                className={`qm-score-val ${score >= 1 ? 'perfect' : score >= 0.5 ? 'pass' : 'fail'}`}
                                title={score.toFixed(4)}
                              >
                                {score.toFixed(2)}
                              </span>
                              <span className="qm-cell-actions">
                                <button
                                  className="qm-cell-btn"
                                  title="View system run"
                                  onClick={() => handleViewRun(c.meta.candidate_id, dataId)}
                                >▶</button>
                                <button
                                  className="qm-cell-btn"
                                  title="View analysis context"
                                  onClick={() => handleViewContext(c.meta.candidate_id, dataId)}
                                >⋯</button>
                              </span>
                            </span>
                          )}
                        </td>
                      );
                    })}
                    {chain.length === 2 && (
                      <td className="qm-td-cell">
                        {delta !== null ? (
                          <span className={`lc-delta ${delta > 0 ? 'positive' : delta < 0 ? 'negative' : ''}`}>
                            {delta > 0 ? '+' : ''}{delta.toFixed(2)}
                          </span>
                        ) : (
                          <span className="qm-dot qm-dot-none">—</span>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!loading && chain.length >= 2 && sharedIds.length === 0 && (
        <div className="lc-empty">No shared data IDs across the lineage chain.</div>
      )}

      {chain.length < 2 && selectedCandidate && (
        <div className="lc-empty">No parent found — this may be the root candidate.</div>
      )}

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
