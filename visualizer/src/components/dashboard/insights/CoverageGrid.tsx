import React, { useCallback, useMemo, useState } from 'react';
import type { Candidate } from '../../../types';
import { getCandidateDetail } from '../../../utils/api';
import { FileViewer } from '../FileViewer';

interface CoverageGridProps {
  candidates: Candidate[];
  onSelectCandidate?: (id: string) => void;
}

interface QuestionRow {
  dataId: string;
  avgScore: number;
  scores: Map<string, number>;
}

export const CoverageGrid: React.FC<CoverageGridProps> = ({ candidates, onSelectCandidate }) => {
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [contextContent, setContextContent] = useState<string | null>(null);
  const [contextTitle, setContextTitle] = useState<string>('');
  const [loadingCell, setLoadingCell] = useState<string | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [addInput, setAddInput] = useState('');
  const [addError, setAddError] = useState<string | null>(null);

  const candidateMap = useMemo(
    () => new Map(candidates.map(c => [c.meta.candidate_id, c])),
    [candidates],
  );

  const aliveIds = useMemo(
    () =>
      candidates
        .filter(c => c.meta.state !== 'unavailable' && c.summary.score_list.length > 0)
        .sort((a, b) => b.summary.avg_score - a.summary.avg_score)
        .map(c => c.meta.candidate_id),
    [candidates],
  );

  const available = useMemo(
    () => compareIds
      .map(id => candidateMap.get(id))
      .filter((c): c is Candidate => c != null && c.summary.score_list.length > 0),
    [compareIds, candidateMap],
  );

  const handleAdd = useCallback((id: string) => {
    const trimmed = id.trim();
    if (!trimmed) return;
    const match = candidates.find(c => c.meta.candidate_id.startsWith(trimmed));
    if (!match) {
      setAddError(`Candidate "${trimmed}" not found`);
      return;
    }
    const fullId = match.meta.candidate_id;
    setAddError(null);
    setCompareIds(prev => prev.includes(fullId) ? prev : [...prev, fullId]);
    setAddInput('');
  }, [candidates]);

  const handleRemove = useCallback((id: string) => {
    setCompareIds(prev => prev.filter(x => x !== id));
  }, []);

  const { rows, unsolvedCount } = useMemo(() => {
    const questionMap = new Map<string, Map<string, number>>();

    for (const cand of available) {
      for (const s of cand.summary.score_list) {
        if (!questionMap.has(s.data_id)) questionMap.set(s.data_id, new Map());
        questionMap.get(s.data_id)!.set(cand.meta.candidate_id, s.score);
      }
    }

    const rows: QuestionRow[] = [];
    let unsolved = 0;

    for (const [dataId, scores] of questionMap) {
      const vals = [...scores.values()];
      const avgScore = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
      if (vals.every(v => v === 0)) unsolved++;
      rows.push({ dataId, avgScore, scores });
    }

    rows.sort((a, b) => a.avgScore - b.avgScore || a.dataId.localeCompare(b.dataId));

    return { rows, unsolvedCount: unsolved };
  }, [available]);

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
        setContextContent(`No system run file found for candidate ${candidateId.slice(0, 8)} on data ${dataId}.\n\nThis candidate was evaluated before run recording was enabled.`);
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

  return (
    <div className="qm-container">
      <div className="qm-selector">
        <div className="qm-selector-add">
          <input
            className="qm-selector-input mono"
            type="text"
            value={addInput}
            onChange={e => { setAddInput(e.target.value); setAddError(null); }}
            onKeyDown={e => { if (e.key === 'Enter') handleAdd(addInput); }}
            placeholder="Add candidate ID (prefix ok)"
          />
          <button className="qm-selector-add-btn" onClick={() => handleAdd(addInput)}>Add</button>
          {compareIds.length > 0 && (
            <button className="qm-selector-reset-btn" onClick={() => setCompareIds([])}>Clear</button>
          )}
          {addError && <span className="qm-selector-error">{addError}</span>}
        </div>
        <div className="qm-selector-alive">
          {aliveIds.map(id => {
            const inCompare = compareIds.includes(id);
            return (
              <button
                key={id}
                className={`qm-alive-chip ${inCompare ? 'active' : ''}`}
                onClick={() => inCompare ? handleRemove(id) : handleAdd(id)}
                title={inCompare ? 'Remove from comparison' : 'Add to comparison'}
              >
                <span className="mono">{id.slice(0, 8)}</span>
                <span className="qm-alive-chip-score">{candidateMap.get(id)?.summary.avg_score.toFixed(4)}</span>
              </button>
            );
          })}
        </div>
      </div>

      {available.length === 0 && (
        <div className="qm-empty">Select candidates above to compare.</div>
      )}

      {available.length > 0 && (
      <div className="qm-summary">
        <span className="qm-summary-item">
          <strong>{rows.length}</strong> questions
        </span>
        <span className="qm-summary-sep">·</span>
        <span className="qm-summary-item qm-unsolved-count">
          <strong>{unsolvedCount}</strong> unsolved by all
        </span>
        <span className="qm-summary-sep">·</span>
        <span className="qm-summary-item">
          <strong>{available.length}</strong> candidates
        </span>
      </div>
      )}

      {available.length > 0 && (
        <div className="qm-scroll">
          <table className="qm-table">
            <thead>
              <tr>
                <th className="qm-th-question">Question</th>
                <th className="qm-th-rate">Avg Score</th>
                {available.map(c => (
                  <th key={c.meta.candidate_id} className="qm-th-cand" title={c.meta.candidate_id}>
                    <div className="qm-cand-id mono">
                      <span
                        className={onSelectCandidate ? 'qm-cand-id-link' : ''}
                        onClick={onSelectCandidate ? () => onSelectCandidate(c.meta.candidate_id) : undefined}
                      >{c.meta.candidate_id.slice(0, 8)}</span>
                      <button
                        className="qm-th-remove"
                        onClick={() => handleRemove(c.meta.candidate_id)}
                        title="Remove from comparison"
                      >✕</button>
                    </div>
                    <div className="qm-cand-score">{c.summary.avg_score.toFixed(2)}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => {
                const isUnsolved = row.avgScore === 0;
                return (
                  <tr key={row.dataId} className={isUnsolved ? 'qm-row-unsolved' : ''}>
                    <td className="qm-td-question mono">{row.dataId}</td>
                    <td className="qm-td-rate">
                      <span className={`qm-rate-badge ${isUnsolved ? 'zero' : row.avgScore >= 0.8 ? 'high' : row.avgScore >= 0.4 ? 'mid' : 'low'}`}>
                        {row.avgScore.toFixed(2)}
                      </span>
                    </td>
                    {available.map(c => {
                      const score = row.scores.get(c.meta.candidate_id);
                      const cellKey = `${c.meta.candidate_id}:${row.dataId}`;
                      const isLoading = loadingCell === cellKey;
                      return (
                        <td key={c.meta.candidate_id} className="qm-td-cell">
                          {isLoading ? (
                            <span className="qm-dot qm-dot-loading">...</span>
                          ) : score === undefined ? (
                            <span className="qm-dot qm-dot-none" title="No data">—</span>
                          ) : (
                            <span className="qm-cell-content">
                              <span
                                className={score >= 0.5 ? 'qm-dot qm-dot-pass' : score > 0 ? 'qm-dot qm-dot-partial' : 'qm-dot qm-dot-fail'}
                                title={score.toFixed(4)}
                              >
                                {score.toFixed(2)}
                              </span>
                              <span className="qm-cell-actions">
                                <button
                                  className="qm-cell-btn"
                                  title="View system run"
                                  onClick={() => handleViewRun(c.meta.candidate_id, row.dataId)}
                                >▶</button>
                                <button
                                  className="qm-cell-btn"
                                  title="View analysis context"
                                  onClick={() => handleViewContext(c.meta.candidate_id, row.dataId)}
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
