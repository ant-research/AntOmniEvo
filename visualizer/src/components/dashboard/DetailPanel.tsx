import React, { useState } from 'react';
import { CollapsibleSection } from './CollapsibleSection';
import { FileTree } from './FileTree';
import { FileViewer } from './FileViewer';
import { openCandidateDirectory } from '../../utils/api';
import type { CandidateWithChange } from './types';
import { useTranslation } from '../../i18n';

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
  const { t } = useTranslation();
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
              Lv.{level.level} {t(`tiers.T${level.level}`)}
            </span>
          </div>
        </div>
        <div className="detail-header-actions">
          <button
            className="detail-open-dir"
            title={t('detail.openDir')}
            onClick={() => openCandidateDirectory(meta.candidate_id).catch(err =>
              console.error('Failed to open directory:', err)
            )}
            aria-label={t('detail.openDir')}
          >
            📂
          </button>
          <button className="detail-close" onClick={onClose} aria-label={t('common.close')}>✕</button>
        </div>
      </div>

      <div className="detail-section">
        <h5>{t('detail.overview')}</h5>
        <div className="detail-grid">
          <div className="detail-item">
            <span className="detail-label">{t('detail.fullId')}</span>
            <span className="detail-value mono">{meta.candidate_id}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">{t('detail.generation')}</span>
            <span className="detail-value">{meta.generation}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">{t('detail.epoch')}</span>
            <span className="detail-value">{meta.epoch}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">{t('detail.datasetIndex')}</span>
            <span className="detail-value">{meta.dataset_index}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">{t('detail.state')}</span>
            <span className="detail-value">
              <span className={`state-dot state-${meta.state}`} />
              {t(`state.${meta.state}`)}
            </span>
          </div>
          <div className="detail-item">
            <span className="detail-label">{t('detail.parent')}</span>
            <span className="detail-value mono">{meta.parent_id ? meta.parent_id.slice(0, 12) : t('detail.parentRoot')}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">{t('detail.children')}</span>
            <span className="detail-value">{meta.children_ids?.length || 0}</span>
          </div>
          {meta.reflection_depth != null && (
            <div className="detail-item">
              <span className="detail-label">{t('detail.reflectionDepth')}</span>
              <span className="detail-value">{meta.reflection_depth}</span>
            </div>
          )}
          <div className="detail-item">
            <span className="detail-label">{t('detail.created')}</span>
            <span className="detail-value">{meta.created_at ? new Date(meta.created_at).toLocaleString() : 'N/A'}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">{t('detail.lastEvaluated')}</span>
            <span className="detail-value">{summary.last_evaluated_at ? new Date(summary.last_evaluated_at).toLocaleString() : 'N/A'}</span>
          </div>
        </div>
      </div>

      <div className="detail-section">
        <h5>{t('detail.score')}</h5>
        <div className="detail-score-row">
          <div className="detail-score-card">
            <span className="detail-score-label">{t('detail.avgScore')}</span>
            <span className="detail-score-num">{summary.avg_score.toFixed(4)}</span>
          </div>
          <div className="detail-score-card">
            <span className="detail-score-label">{t('detail.vsRoot')}</span>
            <span className={`detail-score-num ${changePercent >= 0 ? 'positive' : 'negative'}`}>
              {changePercent >= 0 ? '+' : ''}{changePercent.toFixed(2)} pp
            </span>
          </div>
          <div className="detail-score-card">
            <span className="detail-score-label">{t('detail.rootScore')}</span>
            <span className="detail-score-num">{rootScore.toFixed(4)}</span>
          </div>
        </div>
        {summary.score_list && summary.score_list.length > 0 && (
          <CollapsibleSection title={t('detail.scoresTasks', { n: summary.score_list.length })} defaultOpen={false}>
            <div className="detail-score-table">
              <div className="detail-score-table-header">
                <span>{t('common.dataId')}</span>
                <span>{t('detail.score')}</span>
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
          <p className="detail-loading">{t('detail.loadingDetail')}</p>
        </div>
      )}

      {detail && !detailLoading && (() => {
        const dataDir = meta.data_dir || '';
        const artifactDir = meta.artifact_dir || '';
        const artifactFiles = (Array.isArray(detail.artifact_files) ? detail.artifact_files : []) as string[];

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
            {artifactFiles.length > 0 && (
              <CollapsibleSection title={t('detail.artifactFiles', { n: artifactFiles.length })} defaultOpen={false}>
                <FileTree files={artifactFiles} root={artifactDir} defaultOpenDepth={1} onFileClick={setViewingFile} />
              </CollapsibleSection>
            )}

            {systemRunFiles.length > 0 && (
              <CollapsibleSection title={t('detail.systemRuns', { n: systemRunFiles.length })} defaultOpen={false}>
                <FileTree files={systemRunFiles} root={dataDir} defaultOpenDepth={2} onFileClick={setViewingFile} />
              </CollapsibleSection>
            )}

            {proposerFiles.length > 0 && (
              <CollapsibleSection title={t('detail.proposerRuns', { n: proposerFiles.length })} defaultOpen={false}>
                <FileTree files={proposerFiles} root={dataDir} defaultOpenDepth={2} onFileClick={setViewingFile} />
              </CollapsibleSection>
            )}

            {detail.changelog && (
              <CollapsibleSection title={t('detail.changelog')} defaultOpen={false}>
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
