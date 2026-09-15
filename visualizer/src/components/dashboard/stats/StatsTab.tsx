import React from 'react';
import type { Candidate, Statistics } from '../../../types';
import { ScoreHistoryChart } from './ScoreHistoryChart';
import { CandidateListCard } from './CandidateListCard';
import { TokenUsageCard } from './TokenUsageCard';

interface StatsTabProps {
  candidates: Candidate[];
  statistics: Statistics | null;
  rootScore: number;
}

const EMPTY_USAGE = {
  input_tokens: 0,
  output_tokens: 0,
  cache_creation_input_tokens: 0,
  cache_read_input_tokens: 0,
};

// Format absolute datetime as YYYY-MM-DD HH:mm:ss in local time.
function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
    + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// Format a positive duration in seconds as "Dd HH:mm:ss" (days only when > 0).
function fmtDuration(sec: number | null | undefined): string {
  if (sec == null || Number.isNaN(sec)) return '—';
  const total = Math.max(0, Math.floor(sec));
  const days = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => n.toString().padStart(2, '0');
  const hms = `${pad(h)}:${pad(m)}:${pad(s)}`;
  return days > 0 ? `${days}d ${hms}` : hms;
}

export const StatsTab: React.FC<StatsTabProps> = ({ candidates, statistics, rootScore }) => {
  const maxScore = candidates.length > 0
    ? Math.max(...candidates.map(c => c.summary.avg_score))
    : 0;

  return (
    <div className="stats-tab">
      <h3>📊 Statistics</h3>
      {statistics?.iteration_record_list && statistics.iteration_record_list.length > 0 && (
        <ScoreHistoryChart statistics={statistics} />
      )}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Iteration</div>
          <div className="stat-value">
            {statistics?.current_iteration ?? '—'}
            {statistics?.max_iterations ? <span className="stat-sub"> / {statistics.max_iterations}</span> : ''}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Population Size</div>
          <div className="stat-value">{statistics?.current_population_size ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Created</div>
          <div className="stat-value">{statistics?.total_candidates_created ?? candidates.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Rejected</div>
          <div className="stat-value">{statistics?.rejected_count ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Best Score</div>
          <div className="stat-value highlight">{maxScore.toFixed(4)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Baseline</div>
          <div className="stat-value">{rootScore.toFixed(4)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Root ID</div>
          <div className="stat-value small">{statistics?.root_candidate_id?.slice(0, 8) || 'N/A'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Best ID</div>
          <div className="stat-value small">{statistics?.best_candidate_id?.slice(0, 8) || 'N/A'}</div>
        </div>
        <div className="stat-row">
          <div className="stat-card">
            <div className="stat-label">Start Time</div>
            <div className="stat-value small mono">{fmtDateTime(statistics?.start_time)}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Last Updated</div>
            <div className="stat-value small mono">{fmtDateTime(statistics?.last_updated_at)}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Total Duration</div>
            <div className="stat-value small mono">{fmtDuration(statistics?.total_duration_seconds)}</div>
          </div>
        </div>
        <CandidateListCard
          label="Available Candidates"
          candidates={candidates.filter(c => c.meta.state !== 'unavailable')}
          rootScore={rootScore}
        />
        {statistics?.proposer_usage && (() => {
          const pu = statistics.proposer_usage;
          const su = statistics.system_usage || EMPTY_USAGE;
          const eu = statistics.eval_usage || EMPTY_USAGE;
          const totalIn = pu.input_tokens + su.input_tokens + eu.input_tokens;
          const totalOut = pu.output_tokens + su.output_tokens + eu.output_tokens;
          const totalCacheCreation = pu.cache_creation_input_tokens + su.cache_creation_input_tokens + eu.cache_creation_input_tokens;
          const totalCacheRead = pu.cache_read_input_tokens + su.cache_read_input_tokens + eu.cache_read_input_tokens;
          return (
            <TokenUsageCard
              totalIn={totalIn}
              totalOut={totalOut}
              totalCacheCreation={totalCacheCreation}
              totalCacheRead={totalCacheRead}
              proposer={pu}
              system={su}
              eval_={eu}
            />
          );
        })()}
      </div>
    </div>
  );
};
