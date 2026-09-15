import React, { useMemo } from 'react';

interface FileTreeProps {
  /** Absolute file paths to display. */
  files: string[];
  /**
   * Common root used to compute the relative tree key.
   * If empty/not a prefix of a file, that file's full path is used as-is.
   */
  root: string;
  /** Tree depth (0-based) opened by default. */
  defaultOpenDepth?: number;
  /** Click handler for file (leaf) nodes. */
  onFileClick?: (fullPath: string) => void;
}

interface TreeNode {
  name: string;
  fullPath: string;
  isDir: boolean;
  children: TreeNode[];
}

function buildTree(files: string[], root: string): TreeNode[] {
  const normRoot = root.endsWith('/') ? root.slice(0, -1) : root;
  const rootNode: TreeNode = { name: '', fullPath: normRoot, isDir: true, children: [] };

  for (const full of files) {
    let rel = full;
    if (normRoot && rel.startsWith(normRoot)) {
      rel = rel.slice(normRoot.length);
      if (rel.startsWith('/')) rel = rel.slice(1);
    }
    if (!rel) continue;
    const parts = rel.split('/');
    let cur = rootNode;
    parts.forEach((part, i) => {
      const isLeaf = i === parts.length - 1;
      let child = cur.children.find(c => c.name === part);
      if (!child) {
        child = {
          name: part,
          fullPath: isLeaf ? full : `${cur.fullPath}/${part}`,
          isDir: !isLeaf,
          children: [],
        };
        cur.children.push(child);
      }
      cur = child;
    });
  }

  // Directories first, then files; alphabetical within each group.
  const sort = (node: TreeNode) => {
    node.children.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    node.children.forEach(sort);
  };
  sort(rootNode);

  return rootNode.children;
}

const TreeRow: React.FC<{
  node: TreeNode;
  depth: number;
  defaultOpenDepth: number;
  onFileClick?: (fullPath: string) => void;
}> = ({ node, depth, defaultOpenDepth, onFileClick }) => {
  const [open, setOpen] = React.useState(depth < defaultOpenDepth);
  const clickable = !node.isDir && !!onFileClick;
  return (
    <div className="spec-tree-node">
      <div
        className={`spec-tree-row ${node.isDir ? 'dir' : 'file'} ${clickable ? 'clickable' : ''}`}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => {
          if (node.isDir) setOpen(v => !v);
          else if (onFileClick) onFileClick(node.fullPath);
        }}
        title={node.fullPath}
      >
        {node.isDir ? (
          <span className="spec-tree-twisty">{open ? '▾' : '▸'}</span>
        ) : (
          <span className="spec-tree-twisty leaf">·</span>
        )}
        <span className="spec-tree-icon">{node.isDir ? '📁' : '📄'}</span>
        <span className="spec-tree-name mono">{node.name}</span>
      </div>
      {node.isDir && open && node.children.length > 0 && (
        <div>
          {node.children.map(child => (
            <TreeRow
              key={child.fullPath}
              node={child}
              depth={depth + 1}
              defaultOpenDepth={defaultOpenDepth}
              onFileClick={onFileClick}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const FileTree: React.FC<FileTreeProps> = ({ files, root, defaultOpenDepth = 1, onFileClick }) => {
  const tree = useMemo(() => buildTree(files, root), [files, root]);
  if (tree.length === 0) {
    return <div className="spec-tree-empty">(no files)</div>;
  }
  return (
    <div className="spec-tree">
      {tree.map(node => (
        <TreeRow
          key={node.fullPath}
          node={node}
          depth={0}
          defaultOpenDepth={defaultOpenDepth}
          onFileClick={onFileClick}
        />
      ))}
    </div>
  );
};
