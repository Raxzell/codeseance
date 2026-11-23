export interface FileDiff {
  file_path: string;
  status: "added" | "modified" | "deleted" | "renamed";
  additions: number;
  deletions: number;
  diff_snippet: string;
  symbols: string[];
}

export interface CommitNode {
  commit_hash: string;
  short_hash: string;
  author: string;
  date: string;
  message: string;
  files_changed: string[];
  additions: number;
  deletions: number;
  is_bugfix: boolean;
  diffs: FileDiff[];
}

export interface FileHotspot {
  file_path: string;
  commit_count: number;
  bugfix_count: number;
  total_churn: number;
  drift_score: number;
  hotspot_score: number;
  symbols: string[];
  last_modified: string;
}

export interface PresetRepoInfo {
  preset_id: string;
  name: string;
  tagline: string;
  description: string;
  language: string;
  commit_count: number;
  estimated_drift: number;
  sample_questions: string[];
}

export interface RepoSummary {
  repo_id: string;
  name: string;
  source_type: "preset" | "github";
  source_url: string | null;
  total_commits: number;
  genesis_date: string;
  latest_date: string;
  theseus_drift_score: number;
  drift_verdict: string;
  commits: CommitNode[];
  hotspots: FileHotspot[];
  languages: Record<string, number>;
}

export interface Citation {
  commit_hash: string;
  short_hash: string;
  date: string;
  author: string;
  file_path: string;
  commit_message: string;
  diff_snippet: string;
  relevance_score: number;
}

export interface SeanceAskResponse {
  repo_id: string;
  question: string;
  answer: string;
  citations: Citation[];
  mode: "llm" | "extractive";
  retrieved_commit_count: number;
}

export interface HealthResponse {
  status: string;
  llm_configured: boolean;
  llm_provider: string;
  presets_available: number;
  summoned_repos_cached: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  mode?: "llm" | "extractive";
  retrievedCommitCount?: number;
  timestamp: string;
}

export interface DiffInspectionTarget {
  commitHash: string;
  shortHash: string;
  author: string;
  date: string;
  message: string;
  activeFile: string;
  diffs: FileDiff[];
  fallbackSnippet?: string;
  sourceLabel: "citation" | "timeline";
}
