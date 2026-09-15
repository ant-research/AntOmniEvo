import React, { useMemo } from 'react';
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Scatter,
} from 'recharts';
import type { Statistics } from '../../../types';

interface ChartPoint {
  iteration: number;
  bestScore: number;
  valScore: number | null;
  accepted: boolean | null;
  acceptedScore: number | null;
  rejectedScore: number | null;
  timestamp: string | null;
  durationSeconds: number | null;
  candidateId: string | null;
}

export const ScoreHistoryChart: React.FC<{ statistics: Statistics }> = ({ statistics }) => {
  const { iteration_record_list, baseline_avg_score } = statistics;

  // Build chart data from iteration_record_list ordered by iteration number.
  // bestScore = running max of new_val_avg_score from accepted runs, seeded by baseline.
  const chartData = useMemo<ChartPoint[]>(() => {
    if (!iteration_record_list || iteration_record_list.length === 0) {
      if (baseline_avg_score != null) {
        return [{
          iteration: 0,
          bestScore: baseline_avg_score,
          valScore: null,
          accepted: null,
          acceptedScore: null,
          rejectedScore: null,
          timestamp: null,
          durationSeconds: null,
          candidateId: null,
        }];
      }
      return [];
    }

    const sorted = [...iteration_record_list].sort((a, b) => a.iteration - b.iteration);
    const points: ChartPoint[] = [];

    let bestSoFar = baseline_avg_score ?? -Infinity;
    if (baseline_avg_score != null) {
      points.push({
        iteration: 0,
        bestScore: baseline_avg_score,
        valScore: null,
        accepted: null,
        acceptedScore: null,
        rejectedScore: null,
        timestamp: null,
        durationSeconds: null,
        candidateId: null,
      });
    }

    for (const rec of sorted) {
      const val = rec.new_val_avg_score ?? null;
      if (rec.accepted === true && val != null && val > bestSoFar) {
        bestSoFar = val;
      }
      points.push({
        iteration: rec.iteration,
        bestScore: bestSoFar === -Infinity ? (val ?? 0) : bestSoFar,
        valScore: val,
        accepted: rec.accepted ?? null,
        acceptedScore: rec.accepted === true ? val : null,
        rejectedScore: rec.accepted === false ? val : null,
        timestamp: rec.timestamp ?? null,
        durationSeconds: rec.duration_seconds ?? null,
        candidateId: rec.new_id || null,
      });
    }

    return points;
  }, [iteration_record_list, baseline_avg_score]);

  if (chartData.length === 0) return null;

  const yMin = Math.min(...chartData.map(d => d.bestScore), baseline_avg_score ?? Infinity) * 0.995;
  const yMax = Math.max(...chartData.map(d => d.bestScore)) * 1.005;

  const lastIter = chartData[chartData.length - 1].iteration;
  const tickStep = Math.max(1, Math.ceil((lastIter + 1) / 10));
  const xTicks: number[] = [];
  for (let i = 0; i <= lastIter; i += tickStep) xTicks.push(i);
  if (xTicks[xTicks.length - 1] !== lastIter) xTicks.push(lastIter);

  const hasAccepted = chartData.some(d => d.acceptedScore != null);
  const hasRejected = chartData.some(d => d.rejectedScore != null);

  return (
    <div className="score-history-chart">
      <div className="chart-legend">
        <span className="chart-legend-item">
          <span className="chart-legend-line best" /> Best Avg Score
        </span>
        {hasAccepted && (
          <span className="chart-legend-item">
            <span className="chart-legend-dot accepted" /> Accepted
          </span>
        )}
        {hasRejected && (
          <span className="chart-legend-item">
            <span className="chart-legend-dot rejected" /> Rejected
          </span>
        )}
        {baseline_avg_score != null && (
          <span className="chart-legend-item">
            <span className="chart-legend-line baseline" /> Baseline
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={chartData} margin={{ top: 8, right: 24, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
          <XAxis
            dataKey="iteration"
            type="number"
            domain={[0, lastIter]}
            ticks={xTicks}
            tick={{ fill: '#aaa', fontSize: 11 }}
            label={{ value: 'Iteration', position: 'insideBottomRight', offset: -4, fill: '#888', fontSize: 11 }}
            allowDecimals={false}
          />
          <YAxis
            domain={[yMin, yMax]}
            tick={{ fill: '#aaa', fontSize: 11 }}
            tickFormatter={(v: number) => v.toFixed(2)}
          />
          <Tooltip
            content={((props: any) => {
              const { active, payload, label } = props;
              if (!active || !payload || payload.length === 0) return null;
              const iter = Math.round(Number(label));
              const ts = payload[0]?.payload?.timestamp;
              let formatted: string | null = null;
              if (ts) {
                const d = new Date(ts);
                if (!isNaN(d.getTime())) {
                  const pad = (n: number) => String(n).padStart(2, '0');
                  formatted = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
                }
              }
              const labelMap: Record<string, string> = {
                bestScore: 'Best Score',
                acceptedScore: 'Accepted',
                rejectedScore: 'Rejected',
              };
              const items = payload
                .filter((p: any) => p.value != null && p.dataKey !== 'iteration')
                .map((p: any) => {
                  const key = String(p.dataKey ?? p.name);
                  const display = typeof p.value === 'number' ? p.value.toFixed(4) : String(p.value);
                  return { key, name: labelMap[key] ?? key, value: display, color: p.color ?? p.stroke ?? p.fill };
                });
              const dur = payload[0]?.payload?.durationSeconds;
              const durStr = dur != null ? (dur >= 60 ? `${Math.floor(dur / 60)}m ${Math.round(dur % 60)}s` : `${Math.round(dur)}s`) : null;
              const cid = payload[0]?.payload?.candidateId;
              return (
                <div style={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, fontSize: 12, padding: '8px 10px', color: '#fff' }}>
                  <div style={{ color: '#FFD700', marginBottom: 4 }}>{`Iteration ${iter}`}</div>
                  {items.map((it: any) => (
                    <div key={it.key} style={{ color: it.color }}>{`${it.name} : ${it.value}`}</div>
                  ))}
                  {durStr && <div style={{ color: '#aaa' }}>{`Duration : ${durStr}`}</div>}
                  {cid && (
                    <div style={{ color: '#60a5fa', marginTop: 4 }}>
                      {`ID: ${cid}`}
                    </div>
                  )}
                  {formatted && <div style={{ color: '#FFD700', marginTop: 4 }}>{formatted}</div>}
                </div>
              );
            }) as any}
          />
          {baseline_avg_score != null && (
            <ReferenceLine
              y={baseline_avg_score}
              stroke="#666"
              strokeDasharray="6 3"
              strokeWidth={1}
            />
          )}
          <Line
            type="stepAfter"
            dataKey="bestScore"
            stroke="#4ade80"
            strokeWidth={2}
            dot={false}
            name="bestScore"
          />
          {hasAccepted && (
            <Scatter
              dataKey="acceptedScore"
              fill="#4ade80"
              shape="circle"
              r={4}
              name="Accepted"
              cursor="pointer"
              onClick={(data: any) => {
                const cid = data?.candidateId;
                if (cid) {
                  navigator.clipboard.writeText(cid);
                }
              }}
            />
          )}
          {hasRejected && (
            <Scatter
              dataKey="rejectedScore"
              fill="#f87171"
              shape="cross"
              r={4}
              name="Rejected"
              cursor="pointer"
              onClick={(data: any) => {
                const cid = data?.candidateId;
                if (cid) {
                  navigator.clipboard.writeText(cid);
                }
              }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};
