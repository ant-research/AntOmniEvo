/**
 * API client
 * Communicates with Flask backend
 *
 * Backend model: single global WORKSPACE_ROOT state.
 * Call order: setWorkspaceConfig(path) → getCandidates() / getStatistics() / ...
 */

import type { Candidate, Statistics } from '../types';

const API_BASE = 'http://localhost:3001';

export function getApiBase(): string {
  const params = new URLSearchParams(window.location.search);
  const apiUrl = params.get('api');
  return apiUrl || API_BASE;
}

// Set backend WORKSPACE_ROOT; must be called before other GET requests
export async function setWorkspaceConfig(workspacePath: string): Promise<void> {
  const response = await fetch(`${getApiBase()}/api/config/workspace`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: workspacePath }),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Failed to set workspace: ${response.status} ${body}`);
  }
}

export async function getCandidates(): Promise<Candidate[]> {
  const response = await fetch(`${getApiBase()}/api/candidates`);
  if (!response.ok) {
    throw new Error(`Failed to fetch candidates: ${response.statusText}`);
  }
  return response.json();
}

export async function getStatistics(): Promise<Statistics | null> {
  const response = await fetch(`${getApiBase()}/api/statistics`);
  if (!response.ok) {
    if (response.status === 404) return null;
    throw new Error(`Failed to fetch statistics: ${response.statusText}`);
  }
  return response.json();
}

// Lightweight mtime check; 0 = file not found
export async function getStatisticsMtime(): Promise<number> {
  const response = await fetch(`${getApiBase()}/api/statistics/mtime`);
  if (!response.ok) return 0;
  const body = await response.json();
  return body.mtime ?? 0;
}

export async function getCandidateDetail(candidateId: string): Promise<any> {
  const response = await fetch(`${getApiBase()}/api/candidate/${candidateId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch candidate detail: ${response.statusText}`);
  }
  return response.json();
}

export async function getBatchScores(candidateIds: string[]): Promise<Record<string, Record<string, number>>> {
  const response = await fetch(`${getApiBase()}/api/batch-scores`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_ids: candidateIds }),
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch batch scores: ${response.statusText}`);
  }
  return response.json();
}

export interface FileContent {
  path: string;
  rel_path: string;
  size: number;
  truncated: boolean;
  binary: boolean;
  content: string | null;
}

export async function getFileContent(filePath: string): Promise<FileContent> {
  const url = `${getApiBase()}/api/file?file=${encodeURIComponent(filePath)}`;
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(body.error || `Failed to fetch file: ${response.statusText}`);
  }
  return response.json();
}

export interface BrowseResult {
  path: string;
  parent: string | null;
  dirs: string[];
}

export async function browseDirectory(dirPath?: string): Promise<BrowseResult> {
  const params = dirPath ? `?path=${encodeURIComponent(dirPath)}` : '';
  const response = await fetch(`${getApiBase()}/api/browse${params}`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(body.error || `Failed to browse: ${response.statusText}`);
  }
  return response.json();
}

export async function openCandidateDirectory(candidateId: string): Promise<void> {
  const response = await fetch(`${getApiBase()}/api/open-directory`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_id: candidateId }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(body.error || `Failed to open directory: ${response.statusText}`);
  }
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${getApiBase()}/health`);
    return response.ok;
  } catch {
    return false;
  }
}