import React, { useState } from 'react';
import type { UsageStats } from '../../../types';

interface TokenUsageCardProps {
  totalIn: number;
  totalOut: number;
  totalCacheCreation: number;
  totalCacheRead: number;
  proposer: UsageStats;
  system: UsageStats;
  eval_: UsageStats;
}

export const TokenUsageCard: React.FC<TokenUsageCardProps> = ({
  totalIn,
  totalOut,
  totalCacheCreation,
  totalCacheRead,
  proposer,
  system,
  eval_,
}) => {
  const [open, setOpen] = useState(false);
  const fmt = (n: number) => n.toLocaleString();
  const total = totalIn + totalOut;

  return (
    <div className={`stat-card token-usage-card expandable ${open ? 'open' : ''}`} onClick={() => setOpen(o => !o)}>
      <div className="stat-label">
        Tokens · Total
        <span className={`expandable-arrow ${open ? 'open' : ''}`}>▸</span>
      </div>
      <div className="stat-value small">{fmt(total)}</div>
      <div className="token-summary">
        <span>input tokens {fmt(totalIn)}</span>
        <span>output tokens {fmt(totalOut)}</span>
        <span>cache creation input tokens {fmt(totalCacheCreation)}</span>
        <span>cache read input tokens {fmt(totalCacheRead)}</span>
      </div>
      {open && (
        <div className="token-detail" onClick={e => e.stopPropagation()}>
          <div className="token-category">
            <div className="token-cat-label">🧬 Proposer</div>
            <div className="token-cat-row"><span>input tokens</span><span>{fmt(proposer.input_tokens)}</span></div>
            <div className="token-cat-row"><span>output tokens</span><span>{fmt(proposer.output_tokens)}</span></div>
            <div className="token-cat-row"><span>cache creation input tokens</span><span>{fmt(proposer.cache_creation_input_tokens)}</span></div>
            <div className="token-cat-row"><span>cache read input tokens</span><span>{fmt(proposer.cache_read_input_tokens)}</span></div>
          </div>
          <div className="token-category">
            <div className="token-cat-label">⚙️ System</div>
            <div className="token-cat-row"><span>input tokens</span><span>{fmt(system.input_tokens)}</span></div>
            <div className="token-cat-row"><span>output tokens</span><span>{fmt(system.output_tokens)}</span></div>
            <div className="token-cat-row"><span>cache creation input tokens</span><span>{fmt(system.cache_creation_input_tokens)}</span></div>
            <div className="token-cat-row"><span>cache read input tokens</span><span>{fmt(system.cache_read_input_tokens)}</span></div>
          </div>
          <div className="token-category">
            <div className="token-cat-label">📋 Eval</div>
            <div className="token-cat-row"><span>input tokens</span><span>{fmt(eval_.input_tokens)}</span></div>
            <div className="token-cat-row"><span>output tokens</span><span>{fmt(eval_.output_tokens)}</span></div>
            <div className="token-cat-row"><span>cache creation input tokens</span><span>{fmt(eval_.cache_creation_input_tokens)}</span></div>
            <div className="token-cat-row"><span>cache read input tokens</span><span>{fmt(eval_.cache_read_input_tokens)}</span></div>
          </div>
        </div>
      )}
    </div>
  );
};
