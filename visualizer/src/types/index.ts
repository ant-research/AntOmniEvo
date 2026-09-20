// Candidate metadata
export interface CandidateMeta {
  candidate_id: string;
  artifact_dir: string;
  data_dir: string;
  parent_id: string | null;
  children_ids: string[];
  created_at: string;
  state: string;
  epoch: number;
  dataset_index: number;
  generation: number;
  reflection_depth?: number;
}

// Single score record
export interface ScoreRecord {
  data_id: string;
  score: number;
}

// Candidate evaluation summary
export interface CandidateSummary {
  candidate_id: string;
  score_list: ScoreRecord[];
  avg_score: number;
  last_evaluated_at: string | null;
}

// Full candidate data
export interface Candidate {
  meta: CandidateMeta;
  summary: CandidateSummary;
}

// Workspace statistics
export interface Statistics {
  root_candidate_id: string;
  best_candidate_id: string;
  best_avg_score: number;
  baseline_avg_score: number;
  current_iteration: number;
  max_iterations: number;
  current_population_size: number;
  total_candidates_created: number;
  rejected_count: number;
  avg_score_history: number[];
  iteration_record_list: IterationRecord[];
  start_time: string;
  last_updated_at: string;
  total_duration_seconds: number;
  proposer_usage: UsageStats;
  system_usage: UsageStats;
  eval_usage: UsageStats;
  proposer_name: string;
}

export interface IterationRecord {
  iteration: number;
  epoch: number;
  selected_id: string;
  new_id: string;
  old_batch_score_sum: number;
  new_batch_score_sum: number;
  accepted: boolean;
  candidate_created: boolean;
  new_val_avg_score: number | null;
  proposer_duration_seconds: number;
  duration_seconds: number;
  timestamp: string;
  reflection_depth: number;
}

export interface UsageStats {
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
}

// Evolution level
export interface EvolutionLevel {
  level: number;
  minChange: number;
  maxChange: number;
  color: string;
  label: string;
  emoji: string;
}

// Workspace info
export interface WorkspaceInfo {
  name: string;
  path: string;
  candidateCount: number;
}
