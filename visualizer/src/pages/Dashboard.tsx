import React, { useCallback, useMemo, useState } from 'react';
import { useDashboardData } from '../hooks/useDashboardData';
import { calculateChangePercent, getEvolutionLevel } from '../utils/evolutionLevel';
import { EvolutionTab } from '../components/dashboard/EvolutionTab';
import { LineageTreeTab } from '../components/dashboard/lineage/LineageTreeTab';
import { StatsTab } from '../components/dashboard/stats/StatsTab';
import { InsightsTab } from '../components/dashboard/insights/InsightsTab';
import { LegendTab } from '../components/dashboard/LegendTab';
import './Dashboard.css';

interface DashboardProps {
  workspacePath: string;
}

type TabKey = 'evolution' | 'tree' | 'stats' | 'insights' | 'legend';
const VALID_TABS: TabKey[] = ['evolution', 'tree', 'stats', 'insights', 'legend'];

function getInitialTab(): TabKey {
  const hash = window.location.hash.slice(1);
  return VALID_TABS.includes(hash as TabKey) ? (hash as TabKey) : 'evolution';
}

const Dashboard: React.FC<DashboardProps> = ({ workspacePath }) => {
  const [activeTab, _setActiveTab] = useState<TabKey>(getInitialTab);
  const setActiveTab = useCallback((tab: TabKey) => {
    _setActiveTab(tab);
    window.location.hash = tab;
  }, []);
  const { candidates, statistics, loading, error } = useDashboardData(workspacePath);

  const rootScore = useMemo(() => {
    return statistics?.baseline_avg_score ?? 0;
  }, [statistics]);

  const candidateWithChange = useMemo(() => {
    return candidates.map(c => {
      const changePercent = calculateChangePercent(c.summary.avg_score, rootScore);
      const level = getEvolutionLevel(changePercent);
      return { ...c, changePercent, level };
    }).sort((a, b) => b.changePercent - a.changePercent);
  }, [candidates, rootScore]);

  if (loading) {
    return (
      <div className="dashboard loading">
        <div className="loading-spinner">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard error">
        <div className="error-message">
          <h2>❌ Error</h2>
          <p>{error}</p>
          <p className="hint">Make sure the API server is running: python api/server.py</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>🦞 Lobster Gym</h1>
        <div className="workspace-info"></div>
      </div>

      <div className="tab-nav">
        <button
          className={`tab-btn ${activeTab === 'evolution' ? 'active' : ''}`}
          onClick={() => setActiveTab('evolution')}
        >
          🦞 Evolution ({candidateWithChange.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'tree' ? 'active' : ''}`}
          onClick={() => setActiveTab('tree')}
        >
          🧬 Lineage Tree
        </button>
        <button
          className={`tab-btn ${activeTab === 'stats' ? 'active' : ''}`}
          onClick={() => setActiveTab('stats')}
        >
          📊 Stats
        </button>
        <button
          className={`tab-btn ${activeTab === 'insights' ? 'active' : ''}`}
          onClick={() => setActiveTab('insights')}
        >
          🔍 Insights
        </button>
        <button
          className={`tab-btn ${activeTab === 'legend' ? 'active' : ''}`}
          onClick={() => setActiveTab('legend')}
        >
          🏅 Legend
        </button>
      </div>

      <div className="tab-content">
        {activeTab === 'evolution' && (
          <EvolutionTab candidates={candidateWithChange} rootScore={rootScore} />
        )}
        {activeTab === 'tree' && (
          <LineageTreeTab candidates={candidateWithChange} statistics={statistics} rootScore={rootScore} />
        )}
        {activeTab === 'stats' && (
          <StatsTab candidates={candidates} statistics={statistics} rootScore={rootScore} />
        )}
        {activeTab === 'insights' && (
          <InsightsTab candidates={candidateWithChange} rootScore={rootScore} statistics={statistics} />
        )}
        {activeTab === 'legend' && (
          <LegendTab />
        )}
      </div>
    </div>
  );
};

export default Dashboard;
