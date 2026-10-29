import { useState, useEffect, useCallback } from 'react';
import Dashboard from './pages/Dashboard';
import { browseDirectory, getWorkspaceConfig, type BrowseResult } from './utils/api';
import { LanguageSwitcher, useTranslation } from './i18n';

function DirectoryBrowser({
  onSelect,
  onCancel,
  initialPath,
}: {
  onSelect: (path: string) => void;
  onCancel: () => void;
  initialPath: string;
}) {
  const { t } = useTranslation();
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
    // Start from the parent of the current workspace; if that path is gone
    // (stale/foreign path), fall back to the home directory instead of
    // leaving the dialog empty.
    (async () => {
      setLoading(true);
      setError(null);
      const startPath = initialPath ? initialPath.replace(/\/[^/]*$/, '') : undefined;
      try {
        setBrowse(await browseDirectory(startPath || undefined));
      } catch {
        try {
          setBrowse(await browseDirectory(undefined));
        } catch (e: any) {
          setError(e.message);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [initialPath]);

  // Always render inside the overlay — loading and error states included —
  // so clicking Browse never appears to do nothing.
  return (
    <div className="dir-browser-overlay" onClick={onCancel}>
      <div className="dir-browser" onClick={(e) => e.stopPropagation()}>
        <div className="dir-browser-header">
          <span className="dir-browser-title">{t('app.selectDir')}</span>
          <button className="dir-browser-close" onClick={onCancel}>✕</button>
        </div>
        {error && <div className="dir-browser-error">{error}</div>}
        {!browse ? (
          <div className="dir-browser-loading">{t('common.loading')}</div>
        ) : (
          <>
            <div className="dir-browser-current mono">
              {browse.path}
              <button
                className="dir-browser-select-btn"
                onClick={() => onSelect(browse.path)}
              >
                {t('app.selectThis')}
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
              {loading && <div className="dir-browser-loading">{t('common.loading')}</div>}
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
                <div className="dir-browser-empty">{t('app.noSubdirs')}</div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function App() {
  const { t } = useTranslation();
  const [workspacePath, setWorkspacePath] = useState<string>('');
  const [inputValue, setInputValue] = useState<string>('');
  const [isEditing, setIsEditing] = useState(false);
  const [showBrowser, setShowBrowser] = useState(false);

  // Resolve the workspace to open. A workspace passed to the server at startup
  // (`--workspace`) wins; otherwise the URL param; otherwise ask the user. No
  // hardcoded default: it would be wrong for anyone else (and stale for us).
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get('workspace');
    let cancelled = false;

    const openFromUrl = () => {
      if (fromUrl) {
        setWorkspacePath(fromUrl);
        setInputValue(fromUrl);
      } else {
        setIsEditing(true);
      }
    };

    getWorkspaceConfig()
      .then(({ workspace_root, exists }) => {
        if (cancelled) return;
        if (workspace_root && exists) {
          setWorkspacePath(workspace_root);
          setInputValue(workspace_root);
          const url = new URL(window.location.href);
          url.searchParams.set('workspace', workspace_root);
          window.history.replaceState({}, '', url);
        } else {
          openFromUrl();
        }
      })
      .catch(() => {
        if (!cancelled) openFromUrl();
      });

    return () => {
      cancelled = true;
    };
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

  return (
    <div className="app">
      <div className="workspace-selector">
        <span className="label">{t('app.workspace')}</span>
        {!isEditing ? (
          <button
            className="workspace-path"
            onClick={() => setIsEditing(true)}
            title={t('app.clickToEdit')}
          >
            {workspacePath}
          </button>
        ) : (
          <form onSubmit={handleSubmit} className="workspace-form">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={t('app.enterWorkspacePath')}
              autoFocus
              className="workspace-input"
            />
            <button type="button" className="btn-browse" onClick={() => setShowBrowser(true)}>
              {t('app.browse')}
            </button>
            <button type="submit" className="btn-confirm">{t('app.confirm')}</button>
            <button
              type="button"
              onClick={() => {
                if (!workspacePath) return; // nothing to fall back to — keep editing
                setIsEditing(false);
                setInputValue(workspacePath);
              }}
              className="btn-cancel"
            >
              {t('app.cancel')}
            </button>
          </form>
        )}
        <LanguageSwitcher />
      </div>
      {showBrowser && (
        <DirectoryBrowser
          initialPath={workspacePath}
          onSelect={applyWorkspace}
          onCancel={() => setShowBrowser(false)}
        />
      )}
      {workspacePath ? (
        <Dashboard workspacePath={workspacePath} />
      ) : (
        <div className="loading">
          {t('app.pickWorkspace')}
        </div>
      )}
    </div>
  );
}

export default App;
