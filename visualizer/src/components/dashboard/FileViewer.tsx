import React, { useEffect, useMemo, useRef, useState } from 'react';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import json from 'highlight.js/lib/languages/json';
import yaml from 'highlight.js/lib/languages/yaml';
import bash from 'highlight.js/lib/languages/bash';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import sql from 'highlight.js/lib/languages/sql';
import markdownHl from 'highlight.js/lib/languages/markdown';
import xml from 'highlight.js/lib/languages/xml';
import plaintext from 'highlight.js/lib/languages/plaintext';
import { marked } from 'marked';
import 'highlight.js/styles/atom-one-dark.css';
import { getFileContent, type FileContent } from '../../utils/api';

// Register only the languages we actually serve — keeps the bundle lean.
hljs.registerLanguage('python', python);
hljs.registerLanguage('json', json);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('sql', sql);
hljs.registerLanguage('markdown', markdownHl);
hljs.registerLanguage('xml', xml);
hljs.registerLanguage('plaintext', plaintext);

// Map file extensions to hljs language ids.
const EXT_TO_LANG: Record<string, string> = {
  py: 'python',
  pyi: 'python',
  json: 'json',
  jsonl: 'json',
  yaml: 'yaml', yml: 'yaml',
  sh: 'bash', bash: 'bash', zsh: 'bash',
  js: 'javascript', mjs: 'javascript', cjs: 'javascript',
  ts: 'typescript', tsx: 'typescript',
  sql: 'sql',
  md: 'markdown', markdown: 'markdown',
  html: 'xml', xml: 'xml',
  txt: 'plaintext', log: 'plaintext',
};

function getExt(path: string): string {
  const base = path.split('/').pop() || path;
  const dot = base.lastIndexOf('.');
  return dot >= 0 ? base.slice(dot + 1).toLowerCase() : '';
}

function languageFor(path: string): string {
  return EXT_TO_LANG[getExt(path)] || 'plaintext';
}

function formatJson(raw: string, isJsonl: boolean): string {
  if (isJsonl) {
    // Pretty-print each line, preserve the line-per-record structure.
    return raw
      .split('\n')
      .map(line => {
        const trimmed = line.trim();
        if (!trimmed) return '';
        try {
          return JSON.stringify(JSON.parse(trimmed), null, 2);
        } catch {
          return line;
        }
      })
      .filter(Boolean)
      .join('\n\n');
  }
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

interface FileViewerProps {
  path: string | null;
  inlineContent?: string | null;
  inlineTitle?: string;
  onClose: () => void;
}

type RenderMode = 'code' | 'markdown';

export const FileViewer: React.FC<FileViewerProps> = ({ path, inlineContent, inlineTitle, onClose }) => {
  const [file, setFile] = useState<FileContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<RenderMode>('code');
  const [copyStatus, setCopyStatus] = useState<'idle' | 'success' | 'fail'>('idle');
  const codeRef = useRef<HTMLElement>(null);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).then(
      () => { setCopyStatus('success'); setTimeout(() => setCopyStatus('idle'), 2000); },
      () => { setCopyStatus('fail'); setTimeout(() => setCopyStatus('idle'), 2000); },
    );
  };

  // Reset state and fetch whenever the target file changes.
  useEffect(() => {
    if (!path) {
      setFile(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setFile(null);
    getFileContent(path)
      .then(f => { if (!cancelled) setFile(f); })
      .catch(e => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [path]);

  // Default to markdown-rendered mode for .md files; code otherwise.
  useEffect(() => {
    if (!path) return;
    setMode(getExt(path) === 'md' ? 'markdown' : 'code');
  }, [path]);

  const ext = path ? getExt(path) : '';
  const lang = path ? languageFor(path) : 'plaintext';
  const isMarkdown = ext === 'md' || ext === 'markdown';

  // For code mode: pretty-print JSON/JSONL once and reuse.
  const displayText = useMemo(() => {
    if (!file || file.content == null) return '';
    if (ext === 'json' || ext === 'jsonl') {
      return formatJson(file.content, ext === 'jsonl');
    }
    return file.content;
  }, [file, ext]);

  // Re-run highlight after every text change in code mode.
  useEffect(() => {
    if (mode !== 'code' || !codeRef.current || !displayText) return;
    codeRef.current.removeAttribute('data-highlighted');
    hljs.highlightElement(codeRef.current);
  }, [mode, displayText, lang]);

  // Markdown HTML, computed only when needed.
  const markdownHtml = useMemo(() => {
    if (mode !== 'markdown' || !file || file.content == null) return '';
    return marked.parse(file.content, { async: false }) as string;
  }, [mode, file]);

  // Close on Escape for keyboard users.
  useEffect(() => {
    if (!path && !inlineContent) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [path, inlineContent, onClose]);

  // Inline content mode: render directly without fetching
  if (!path && inlineContent != null) {
    return (
      <div className="file-viewer-overlay" onClick={onClose}>
        <div className="file-viewer-modal" onClick={e => e.stopPropagation()}>
          <div className="file-viewer-header">
            <div className="file-viewer-title">
              <span className="file-viewer-name mono">{inlineTitle ?? 'Context'}</span>
            </div>
            <div className="file-viewer-actions">
              <button
                className={`file-viewer-copy ${copyStatus !== 'idle' ? `file-viewer-copy-${copyStatus}` : ''}`}
                onClick={() => handleCopy(inlineContent)}
                title="Copy to clipboard"
              >
                {copyStatus === 'success' ? '✓ Copied' : copyStatus === 'fail' ? '✗ Failed' : '📋 Copy'}
              </button>
              <button className="file-viewer-close" onClick={onClose} aria-label="Close">✕</button>
            </div>
          </div>
          <div className="file-viewer-body">
            <div className="file-viewer-code-container">
              <pre><code className="language-plaintext">{inlineContent}</code></pre>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!path) return null;

  const fileName = path.split('/').pop() || path;

  return (
    <div className="file-viewer-overlay" onClick={onClose}>
      <div className="file-viewer-modal" onClick={e => e.stopPropagation()}>
        <div className="file-viewer-header">
          <div className="file-viewer-title">
            <span className="file-viewer-name mono">{fileName}</span>
            {file && (
              <span className="file-viewer-meta">
                {lang} · {formatBytes(file.size)}
                {file.truncated && <span className="file-viewer-warn"> · truncated</span>}
              </span>
            )}
          </div>
          <div className="file-viewer-actions">
            {isMarkdown && file?.content && (
              <button
                className={`file-viewer-mode ${mode === 'markdown' ? 'active' : ''}`}
                onClick={() => setMode(m => m === 'markdown' ? 'code' : 'markdown')}
                title="Toggle markdown rendering"
              >
                {mode === 'markdown' ? '⟨/⟩ source' : '📖 rendered'}
              </button>
            )}
            {file?.content != null && (
              <button
                className={`file-viewer-copy ${copyStatus !== 'idle' ? `file-viewer-copy-${copyStatus}` : ''}`}
                onClick={() => handleCopy(file.content!)}
                title="Copy to clipboard"
              >
                {copyStatus === 'success' ? '✓ Copied' : copyStatus === 'fail' ? '✗ Failed' : '📋 Copy'}
              </button>
            )}
            <button className="file-viewer-close" onClick={onClose} aria-label="Close">✕</button>
          </div>
        </div>
        <div className="file-viewer-path mono" title={path}>{path}</div>

        <div className="file-viewer-body">
          {loading && <div className="file-viewer-loading">Loading…</div>}
          {error && <div className="file-viewer-error">{error}</div>}
          {!loading && !error && file && file.binary && (
            <div className="file-viewer-binary">Binary file — preview unavailable.</div>
          )}
          {!loading && !error && file && !file.binary && mode === 'code' && (
            <div className="file-viewer-code-container">
              <div className="file-viewer-line-numbers" aria-hidden="true">
                {displayText.split('\n').map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>
              <pre className="file-viewer-pre"><code ref={codeRef} className={`language-${lang}`}>{displayText}</code></pre>
            </div>
          )}
          {!loading && !error && file && !file.binary && mode === 'markdown' && (
            <div className="file-viewer-markdown" dangerouslySetInnerHTML={{ __html: markdownHtml }} />
          )}
        </div>
      </div>
    </div>
  );
};
