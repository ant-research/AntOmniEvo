import React from 'react';
import type { CandidateWithChange } from '../types';

interface TreeNodeProps {
  nodeId: string;
  candidateMap: Map<string, CandidateWithChange>;
  parentMap: Map<string, string[]>;
  depth: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
  expandedSet: Set<string>;
  onToggle: (id: string, recursive: boolean) => void;
  highlightId?: string | null;
}

export const TreeNode: React.FC<TreeNodeProps> = ({
  nodeId,
  candidateMap,
  parentMap,
  depth,
  selectedId,
  onSelect,
  expandedSet,
  onToggle,
  highlightId,
}) => {
  const expanded = expandedSet.has(nodeId);
  const candidate = candidateMap.get(nodeId);
  const children = (parentMap.get(nodeId) || []).slice().sort((a, b) => {
    const ca = candidateMap.get(a);
    const cb = candidateMap.get(b);
    const ta = ca?.meta.created_at ?? '';
    const tb = cb?.meta.created_at ?? '';
    return ta < tb ? -1 : ta > tb ? 1 : 0;
  });
  const hasChildren = children.length > 0;
  const isSelected = selectedId === nodeId;
  const isHighlighted = highlightId === nodeId;

  if (!candidate) return null;

  const { changePercent, level } = candidate;

  return (
    <div className="tree-node-wrapper">
      <div
        className={`tree-node-row ${isSelected ? 'selected' : ''} ${isHighlighted ? 'highlighted' : ''}`}
        style={{ '--node-color': level.color } as React.CSSProperties}
        data-node-id={nodeId}
        onClick={() => onSelect(nodeId)}
      >
        {/* Shift+click expands the entire subtree. */}
        <button
          className={`tree-toggle ${hasChildren ? '' : 'leaf'}`}
          onClick={e => {
            e.stopPropagation();
            if (hasChildren) onToggle(nodeId, e.shiftKey);
          }}
          title={hasChildren ? (expanded ? 'Collapse (shift+click: whole subtree)' : 'Expand (shift+click: whole subtree)') : ''}
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          {hasChildren ? (expanded ? '▾' : '▸') : '·'}
        </button>

        <span className="tree-node-dot" style={{ background: level.color }} />
        <span className="tree-node-id">{nodeId.slice(0, 8)}</span>
        <span className="tree-node-gen-badge">
          G{candidate.meta.generation || 0} E{candidate.meta.epoch} I{candidate.meta.dataset_index}
        </span>
        <span className="tree-node-score-val">{candidate.summary.avg_score.toFixed(4)}</span>
        <span className={`tree-node-change ${changePercent >= 0 ? 'positive' : 'negative'}`}>
          {changePercent >= 0 ? '↑' : '↓'}{Math.abs(changePercent).toFixed(2)}pp
        </span>
        <span className="tree-node-level-badge" style={{ background: level.color }}>
          {level.emoji} {level.label}
        </span>
        {hasChildren && (
          <span className="tree-node-children-count">{children.length}</span>
        )}
      </div>

      {hasChildren && expanded && (
        <div className="tree-children">
          {children.map(childId => (
            <TreeNode
              key={childId}
              nodeId={childId}
              candidateMap={candidateMap}
              parentMap={parentMap}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              expandedSet={expandedSet}
              onToggle={onToggle}
              highlightId={highlightId}
            />
          ))}
        </div>
      )}
    </div>
  );
};
