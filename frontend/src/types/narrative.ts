/**
 * Story Engine 2.0 (Narrative Reasoning System) Types
 */

export interface NarrativeProfile {
  commercial_positioning?: string;
  dominant_appeal?: string;
  tone?: string;
  humor_level?: 'low' | 'medium' | 'high' | string;
  power_fantasy_level?: 'low' | 'medium' | 'medium_high' | 'high' | 'absolute' | string;
  emotional_intensity?: 'low' | 'medium' | 'high' | string;
  pacing_preference?: string;
  narrative_complexity?: 'single_track' | 'multi_faction' | 'epic' | string;
  custom_notes?: string;
}

export interface SettingSystem {
  id: string;
  novel_id: string;
  name: string;
  type: 'power_mechanism' | 'ecological_law' | 'political_institution' | 'social_rule' | 'generic' | string;
  mechanism: string;
  cost?: string | null;
  boundary?: string | null;
  failure_condition?: string | null;
  stakeholder?: string | null;
  social_effect?: string | null;
  theme_link?: string | null;
  current_state: 'active' | 'deprecated' | 'evolving' | string;
  usage_count: number;
  last_used_chapter: number;
  created_at?: string;
  updated_at?: string;
}

export interface SettingHealthIssue {
  setting_name: string;
  issue_type: string;
  description: string;
  remediation?: string;
}

export interface SettingHealthReport {
  passed: boolean;
  score: number;
  total_systems: number;
  systems_count?: number;
  boundary_missing_systems?: string[];
  issues: SettingHealthIssue[];
  summary?: string;
}

export interface ConflictSignature {
  id: string;
  novel_id: string;
  chapter_start: number;
  chapter_end: number;
  initiator?: string | null;
  antagonist_goal?: string | null;
  pressure_type: string;
  protagonist_strategy: string;
  power_used?: string | null;
  twist_mechanism?: string | null;
  outcome: string;
  cost?: string | null;
  emotional_effect?: string | null;
  setting_used?: string | null;
  signature_hash?: string;
  created_at?: string;
}

export interface ConflictRepetitionMatch {
  prior_chapter_range: string;
  initiator?: string;
  similarity: number;
  reasons: string[];
  prior_summary?: string;
}

export interface ConflictRepetitionDiagnosis {
  has_repetition: boolean;
  max_similarity: number;
  match_count: number;
  matches: ConflictRepetitionMatch[];
}

export interface NarrativeAudit {
  id: string;
  novel_id: string;
  chapter_index: number;
  dimension: 'voice_integrity' | 'conflict_novelty' | 'ability_constraints' | 'pacing_balance' | string;
  severity: 'pass' | 'watch' | 'warning' | 'critical' | string;
  evidence: string;
  recommendation: string;
  action_required: number | boolean;
  resolved: number | boolean;
  created_at?: string;
}

export interface NarrativeAuditFinding {
  dimension: string;
  severity: string;
  evidence: string;
  recommendation: string;
  action_required: boolean;
}

export interface NarrativeAuditRunResult {
  chapter_index: number;
  overall_action: 'PASS' | 'WATCH' | 'REVISE' | 'CRITICAL' | 'NO_ACTION_REQUIRED';
  scene_function?: string;
  findings_count: number;
  findings: NarrativeAuditFinding[];
  is_breathing_scene: boolean;
  summary: string;
}
