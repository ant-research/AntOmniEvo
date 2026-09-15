import React, { useState } from 'react';
import { CollapsibleSection } from './CollapsibleSection';
import { FileTree } from './FileTree';
import { FileViewer } from './FileViewer';
import { openCandidateDirectory } from '../../utils/api';
import type { CandidateWithChange } from './types';

interface DetailPanelProps {
  candidate: CandidateWithChange;
  detail: Record<string, any> | null;
  detailLoading: boolean;
  rootScore: number;
  onClose: () => void;
}

export const DetailPanel: React.FC<DetailPanelProps> = ({
  candidate,
  detail,
  detailLoading,
  rootScore,
  onClose,
}) => {
  const { meta, summary, changePercent, level } = candidate;
  const [viewingFile, setViewingFile] = useState<string | null>(null);

  return (
    <div className="detail-content">
      <div className="detail-header">
        <div className="detail-header-left">
          <span className="detail-emoji">{level.emoji}</span>
          <div>
            <h4 className="detail-id">{meta.candidate_id.slice(0, 12)}</h4>
            <span className="detail-level-badge" style={{ background: level.color }}>
              Lv.{level.level} {level.label}
            </span>
          </div>
        </div>
        <div className="detail-header-actions">
          <button
            className="detail-open-dir"
            title="Open candidate directory"
            onClick={() => openCandidateDirectory(meta.candidate_id).catch(err =>
              console.error('Failed to open directory:', err)
            )}
            aria-label="Open directory"
          >
            📂
          </button>
          <button className="detail-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
      </div>

      <div className="detail-section">
        <h5>Overview</h5>
        <div className="detail-grid">
          <div className="detail-item">
            <span className="detail-label">Full ID</span>
            <span className="detail-value mono">{meta.candidate_id}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Generation</span>
            <span className="detail-value">{meta.generation}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Epoch</span>
            <span className="detail-value">{meta.epoch}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Dataset Index</span>
            <span className="detail-value">{meta.dataset_index}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">State</span>
            <span className="detail-value">
              <span className={`state-dot state-${meta.state}`} />
              {meta.state}
            </span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Parent</span>
            <span className="detail-value mono">{meta.parent_id ? meta.parent_id.slice(0, 12) : '— (root)'}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Children</span>
            <span className="detail-value">{meta.children_ids?.length || 0}</span>
          </div>
          {meta.reflection_depth != null && (
            <div className="detail-item">
              <span className="detail-label">Reflection Depth</span>
              <span className="detail-value">{meta.reflection_depth}</span>
            </div>
          )}
          <div className="detail-item">
            <span className="detail-label">Created</span>
            <span className="detail-value">{meta.created_at ? new Date(meta.created_at).toLocaleString() : 'N/A'}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Last Evaluated</span>
            <span className="detail-value">{summary.last_evaluated_at ? new Date(summary.last_evaluated_at).toLocaleString() : 'N/A'}</span>
          </div>
        </div>
      </div>

      <div className="detail-section">
        <h5>Score</h5>
        <div className="detail-score-row">
          <div className="detail-score-card">
            <span className="detail-score-label">Avg Score</span>
            <span className="detail-score-num">{summary.avg_score.toFixed(4)}</span>
          </div>
          <div className="detail-score-card">
            <span className="detail-score-label">vs Root</span>
            <span className={`detail-score-num ${changePercent >= 0 ? 'positive' : 'negative'}`}>
              {changePercent >= 0 ? '+' : ''}{changePercent.toFixed(2)} pp
            </span>
          </div>
          <div className="detail-score-card">
            <span className="detail-score-label">Root Score</span>
            <span className="detail-score-num">{rootScore.toFixed(4)}</span>
          </div>
        </div>
        {summary.score_list && summary.score_list.length > 0 && (
          <CollapsibleSection title={`Scores · ${summary.score_list.length} tasks`} defaultOpen={false}>
            <div className="detail-score-table">
              <div className="detail-score-table-header">
                <span>Data ID</span>
                <span>Score</span>
              </div>
              {summary.score_list.map((s, i) => (
                <div key={i} className="detail-score-table-row">
                  <span className="mono">{s.data_id}</span>
                  <span className={s.score >= 0.5 ? 'positive' : 'negative'}>{s.score.toFixed(4)}</span>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}
      </div>

      {detailLoading && (
        <div className="detail-section">
          <p className="detail-loading">Loading detail…</p>
        </div>
      )}

      {detail && !detailLoading && (() => {
        const dataDir = meta.data_dir || '';
        const specDir = meta.spec_dir || '';
        const specFiles = (Array.isArray(detail.spec_files) ? detail.spec_files : []) as string[];

        const systemRunFiles = Object.values(
          (detail.system_runs ?? {}) as Record<string, string[]>,
        ).flat();

        const pr = (detail.proposer_runs ?? {}) as {
          analysis_results?: string[];
          analysis_trajectories?: string[];
          mutation_trajectories?: string[];
        };
        const proposerFiles = [
          ...(pr.analysis_results || []),
          ...(pr.analysis_trajectories || []),
          ...(pr.mutation_trajectories || []),
        ];

        return (
          <>
            {specFiles.length > 0 && (
              <CollapsibleSection title={`Spec Files · ${specFiles.length}`} defaultOpen={false}>
                <FileTree files={specFiles} root={specDir} defaultOpenDepth={1} onFileClick={setViewingFile} />
              </CollapsibleSection>
            )}

            {systemRunFiles.length > 0 && (
              <CollapsibleSection title={`System Runs · ${systemRunFiles.length} runs`} defaultOpen={false}>
                <FileTree files={systemRunFiles} root={dataDir} defaultOpenDepth={2} onFileClick={setViewingFile} />
              </CollapsibleSection>
            )}

            {proposerFiles.length > 0 && (
              <CollapsibleSection title={`Proposer Runs · ${proposerFiles.length} files`} defaultOpen={false}>
                <FileTree files={proposerFiles} root={dataDir} defaultOpenDepth={2} onFileClick={setViewingFile} />
              </CollapsibleSection>
            )}

            {detail.changelog && (
              <CollapsibleSection title="Changelog" defaultOpen={false}>
                <FileTree files={[detail.changelog as string]} root={dataDir} defaultOpenDepth={0} onFileClick={setViewingFile} />
              </CollapsibleSection>
            )}
          </>
        );
      })()}

      <FileViewer path={viewingFile} onClose={() => setViewingFile(null)} />
    </div>
  );
};
