import { useEffect, useRef, useState } from 'react';
import type { Candidate, Statistics } from '../types';
import {
  getCandidates,
  getStatistics,
  getStatisticsMtime,
  setWorkspaceConfig,
} from '../utils/api';

const POLL_INTERVAL_MS = 20000;

export interface DashboardData {
  candidates: Candidate[];
  statistics: Statistics | null;
  loading: boolean;
  error: string | null;
}

export function useDashboardData(workspacePath: string): DashboardData {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [statistics, setStatistics] = useState<Statistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastMtimeRef = useRef<number>(0);

  useEffect(() => {
    let cancelled = false;
    lastMtimeRef.current = 0;

    async function fetchAll() {
      const [candidatesData, statsData] = await Promise.all([
        getCandidates(),
        getStatistics(),
      ]);
      if (cancelled) return;
      setCandidates(candidatesData);
      setStatistics(statsData);
    }

    async function initialLoad() {
      setLoading(true);
      setError(null);
      try {
        await setWorkspaceConfig(workspacePath);
        await fetchAll();
        lastMtimeRef.current = await getStatisticsMtime();
      } catch (err) {
        if (cancelled) return;
        console.error('Failed to load data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    async function poll() {
      try {
        const mtime = await getStatisticsMtime();
        if (cancelled) return;
        if (mtime !== 0 && mtime !== lastMtimeRef.current) {
          lastMtimeRef.current = mtime;
          await fetchAll();
        }
      } catch (err) {
        console.warn('Poll failed:', err);
      }
    }

    if (!workspacePath) return;
    initialLoad();
    const id = window.setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [workspacePath]);

  return { candidates, statistics, loading, error };
}
