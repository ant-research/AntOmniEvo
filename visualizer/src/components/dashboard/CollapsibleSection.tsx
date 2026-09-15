import React, { useState } from 'react';

interface CollapsibleSectionProps {
  title: string;
  sub?: boolean;
  defaultOpen: boolean;
  children: React.ReactNode;
}

export const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({
  title,
  sub,
  defaultOpen,
  children,
}) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`collapsible ${sub ? 'collapsible-sub' : ''}`}>
      <button className="collapsible-header" onClick={() => setOpen(v => !v)}>
        <span className={`collapsible-arrow ${open ? 'open' : ''}`}>▸</span>
        <span className="collapsible-title">{title}</span>
      </button>
      <div className="collapsible-body" style={{ display: open ? undefined : 'none' }}>{children}</div>
    </div>
  );
};
