import React, { useState } from 'react';
import type { UsageStats } from '../../../types';
import { useTranslation } from '../../../i18n';

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
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const fmt = (n: number) => n.toLocaleString();
  const total = totalIn + totalOut;

  return (
    <div className={`stat-card token-usage-card expandable ${open ? 'open' : ''}`} onClick={() => setOpen(o => !o)}>
      <div className="stat-label">
        {t('tokens.total')}
        <span className={`expandable-arrow ${open ? 'open' : ''}`}>▸</span>
      </div>
      <div className="stat-value small">{fmt(total)}</div>
      <div className="token-summary">
        <span>{t('tokens.input')} {fmt(totalIn)}</span>
        <span>{t('tokens.output')} {fmt(totalOut)}</span>
        <span>{t('tokens.cacheCreation')} {fmt(totalCacheCreation)}</span>
        <span>{t('tokens.cacheRead')} {fmt(totalCacheRead)}</span>
      </div>
      {open && (
        <div className="token-detail" onClick={e => e.stopPropagation()}>
          <div className="token-category">
            <div className="token-cat-label">{t('tokens.proposer')}</div>
            <div className="token-cat-row"><span>{t('tokens.input')}</span><span>{fmt(proposer.input_tokens)}</span></div>
            <div className="token-cat-row"><span>{t('tokens.output')}</span><span>{fmt(proposer.output_tokens)}</span></div>
            <div className="token-cat-row"><span>{t('tokens.cacheCreation')}</span><span>{fmt(proposer.cache_creation_input_tokens)}</span></div>
            <div className="token-cat-row"><span>{t('tokens.cacheRead')}</span><span>{fmt(proposer.cache_read_input_tokens)}</span></div>
          </div>
          <div className="token-category">
            <div className="token-cat-label">{t('tokens.system')}</div>
            <div className="token-cat-row"><span>{t('tokens.input')}</span><span>{fmt(system.input_tokens)}</span></div>
            <div className="token-cat-row"><span>{t('tokens.output')}</span><span>{fmt(system.output_tokens)}</span></div>
            <div className="token-cat-row"><span>{t('tokens.cacheCreation')}</span><span>{fmt(system.cache_creation_input_tokens)}</span></div>
            <div className="token-cat-row"><span>{t('tokens.cacheRead')}</span><span>{fmt(system.cache_read_input_tokens)}</span></div>
          </div>
          <div className="token-category">
            <div className="token-cat-label">{t('tokens.eval')}</div>
            <div className="token-cat-row"><span>{t('tokens.input')}</span><span>{fmt(eval_.input_tokens)}</span></div>
            <div className="token-cat-row"><span>{t('tokens.output')}</span><span>{fmt(eval_.output_tokens)}</span></div>
            <div className="token-cat-row"><span>{t('tokens.cacheCreation')}</span><span>{fmt(eval_.cache_creation_input_tokens)}</span></div>
            <div className="token-cat-row"><span>{t('tokens.cacheRead')}</span><span>{fmt(eval_.cache_read_input_tokens)}</span></div>
          </div>
        </div>
      )}
    </div>
  );
};
