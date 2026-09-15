/**
 * Data loading utilities
 * Loads candidate and statistics data from workspace directories
 */

import type { Candidate, CandidateMeta, CandidateSummary, Statistics, WorkspaceInfo } from '../types';
import * as fs from 'fs';
import * as path from 'path';

// Get workspace list
export function getWorkspaceList(workspaceRoot: string): WorkspaceInfo[] {
  const workspaces: WorkspaceInfo[] = [];

  try {
    const entries = fs.readdirSync(workspaceRoot, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory()) {
        const fullPath = path.join(workspaceRoot, entry.name);
        const candidatesPath = path.join(fullPath, 'candidates');

        if (fs.existsSync(candidatesPath)) {
          const candidates = fs.readdirSync(candidatesPath);
          workspaces.push({
            name: entry.name,
            path: fullPath,
            candidateCount: candidates.length,
          });
        }
      }
    }
  } catch (error) {
    console.error('Error listing workspaces:', error);
  }

  // Sort by name in descending order
  return workspaces.sort((a, b) => b.name.localeCompare(a.name));
}

// Load a single candidate's data
export function loadCandidate(workspacePath: string, candidateId: string): Candidate | null {
  try {
    const dataDir = path.join(workspacePath, 'candidates', candidateId, 'data');

    // Read meta.json
    const metaPath = path.join(dataDir, 'meta.json');
    if (!fs.existsSync(metaPath)) return null;
    const meta: CandidateMeta = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));

    // Read summary.json
    const summaryPath = path.join(dataDir, 'summary.json');
    let summary: CandidateSummary = {
      candidate_id: candidateId,
      score_list: [],
      avg_score: 0,
      last_evaluated_at: null,
    };
    if (fs.existsSync(summaryPath)) {
      summary = JSON.parse(fs.readFileSync(summaryPath, 'utf-8'));
    }

    return { meta, summary };
  } catch (error) {
    console.error(`Error loading candidate ${candidateId}:`, error);
    return null;
  }
}

// Load all candidates in a workspace
export function loadAllCandidates(workspacePath: string): Candidate[] {
  const candidates: Candidate[] = [];
  const candidatesPath = path.join(workspacePath, 'candidates');

  try {
    const ids = fs.readdirSync(candidatesPath);
    for (const id of ids) {
      const candidate = loadCandidate(workspacePath, id);
      if (candidate) {
        candidates.push(candidate);
      }
    }
  } catch (error) {
    console.error('Error loading candidates:', error);
  }

  return candidates;
}

// Load statistics
export function loadStatistics(workspacePath: string): Statistics | null {
  try {
    const statsPath = path.join(workspacePath, 'logs', 'statistics.json');
    if (!fs.existsSync(statsPath)) return null;
    const stats = JSON.parse(fs.readFileSync(statsPath, 'utf-8'));

    return stats;
  } catch (error) {
    console.error('Error loading statistics:', error);
    return null;
  }
}

// Get root candidate (typically the one without a parent_id)
export function getRootCandidate(candidates: Candidate[]): Candidate | null {
  // Find generation=0
  const root = candidates.find(c => c.meta.generation === 0);
  if (root) return root;

  // Or find one with null parent_id
  return candidates.find(c => c.meta.parent_id === null) || null;
}

// Build candidate relationship graph
export interface CandidateNode {
  id: string;
  parentId: string | null;
  generation: number;
  avgScore: number;
  children: string[];
}

export function buildCandidateGraph(candidates: Candidate[]): Map<string, CandidateNode> {
  const graph = new Map<string, CandidateNode>();

  for (const candidate of candidates) {
    graph.set(candidate.meta.candidate_id, {
      id: candidate.meta.candidate_id,
      parentId: candidate.meta.parent_id,
      generation: candidate.meta.generation,
      avgScore: candidate.summary.avg_score,
      children: candidate.meta.children_ids || [],
    });
  }

  return graph;
}

// Calculate absolute change (percentage points) for each candidate vs root
export function calculateRelativeScores(
  candidates: Candidate[],
  rootId: string
): Map<string, { changePercent: number; baseline: number; current: number }> {
  const result = new Map<string, { changePercent: number; baseline: number; current: number }>();

  const root = candidates.find(c => c.meta.candidate_id === rootId);
  if (!root) return result;

  const baseline = root.summary.avg_score;

  for (const candidate of candidates) {
    const current = candidate.summary.avg_score;
    const changePercent = (current - baseline) * 100;
    result.set(candidate.meta.candidate_id, {
      changePercent,
      baseline,
      current,
    });
  }

  return result;
}