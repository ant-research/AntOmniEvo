import { useState, useEffect, useCallback } from 'react';
import Dashboard from './pages/Dashboard';
import { browseDirectory, type BrowseResult } from './utils/api';

// Default workspace path
const DEFAULT_WORKSPACE = '/Users/jacklv/work/omnievo/antomnievo/example/text2sql/workspace';

function DirectoryBrowser({
  onSelect,
  onCancel,
  initialPath,
}: {
  onSelect: (path: string) => void;
  onCancel: () => void;
  initialPath: string;
}) {
  const [browse, setBrowse] = useState<BrowseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (dirPath?: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await browseDirectory(dirPath);
      setBrowse(result);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Start from the parent of the current workspace
    const startPath = initialPath ? initialPath.replace(/\/[^/]*$/, '') : undefined;
    load(startPath || undefined);
  }, [initialPath, load]);

  if (!browse && loading) return <div className="dir-browser-loading">Loading…</div>;
  if (error) return <div className="dir-browser-error">{error}</div>;
  if (!browse) return null;

  return (
    <div className="dir-browser-overlay" onClick={onCancel}>
      <div className="dir-browser" onClick={(e) => e.stopPropagation()}>
        <div className="dir-browser-header">
          <span className="dir-browser-title">Select Workspace Directory</span>
          <button className="dir-browser-close" onClick={onCancel}>✕</button>
        </div>
        <div className="dir-browser-current mono">
          {browse.path}
          <button
            className="dir-browser-select-btn"
            onClick={() => onSelect(browse.path)}
          >
            Select This
          </button>
        </div>
        <div className="dir-browser-list">
          {browse.parent && (
            <div
              className="dir-browser-item dir-browser-parent"
              onClick={() => load(browse.parent!)}
            >
              📁 ..
            </div>
          )}
          {loading && <div className="dir-browser-loading">Loading…</div>}
          {!loading && browse.dirs.map((name) => (
            <div
              key={name}
              className="dir-browser-item"
              onClick={() => load(`${browse.path}/${name}`)}
            >
              📁 {name}
            </div>
          ))}
          {!loading && browse.dirs.length === 0 && (
            <div className="dir-browser-empty">No subdirectories</div>
          )}
        </div>
      </div>
    </div>
  );
}

function App() {
  const [workspacePath, setWorkspacePath] = useState<string>('');
  const [inputValue, setInputValue] = useState<string>('');
  const [isEditing, setIsEditing] = useState(false);
  const [showBrowser, setShowBrowser] = useState(false);

  // Read workspace from URL params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ws = params.get('workspace');
    if (ws) {
      setWorkspacePath(ws);
      setInputValue(ws);
    } else {
      // Use default workspace
      setWorkspacePath(DEFAULT_WORKSPACE);
      setInputValue(DEFAULT_WORKSPACE);
    }
  }, []);

  const applyWorkspace = (path: string) => {
    setWorkspacePath(path);
    setInputValue(path);
    const url = new URL(window.location.href);
    url.searchParams.set('workspace', path);
    window.history.pushState({}, '', url);
    setIsEditing(false);
    setShowBrowser(false);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim()) {
      applyWorkspace(inputValue.trim());
    }
  };

  // Show loading state
  if (!workspacePath) {
    return <div className="loading">Loading...</div>;
  }

  return (
    <div className="app">
      <div className="workspace-selector">
        <span className="label">Workspace:</span>
        {!isEditing ? (
          <button
            className="workspace-path"
            onClick={() => setIsEditing(true)}
            title="Click to edit"
          >
            {workspacePath}
          </button>
        ) : (
          <form onSubmit={handleSubmit} className="workspace-form">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Enter workspace path"
              autoFocus
              className="workspace-input"
            />
            <button type="button" className="btn-browse" onClick={() => setShowBrowser(true)}>
              Browse
            </button>
            <button type="submit" className="btn-confirm">Confirm</button>
            <button
              type="button"
              onClick={() => {
                setIsEditing(false);
                setInputValue(workspacePath);
              }}
              className="btn-cancel"
            >
              Cancel
            </button>
          </form>
        )}
      </div>
      {showBrowser && (
        <DirectoryBrowser
          initialPath={workspacePath}
          onSelect={applyWorkspace}
          onCancel={() => setShowBrowser(false)}
        />
      )}
      <Dashboard workspacePath={workspacePath} />
    </div>
  );
}

export default App;
