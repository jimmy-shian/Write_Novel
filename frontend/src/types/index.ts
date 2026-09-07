/**
 * Shared Type Definitions for AI Novel Factory.
 */

export type CreationStage =
  | 'worldview'
  | 'characters'
  | 'foreshadowing'
  | 'volumes'
  | 'volume_skeleton'
  | 'writer'
  | 'editor'
  | 'evaluate';

export interface Novel {
  id: string;
  title: string;
  genre: string;
  style: string;
  pipeline_prompt?: string;
  created_at?: string;
}

export interface Chapter {
  id?: number;
  novel_id: string;
  chapter_index: number;
  title?: string;
  content: string;
  synopsis?: string;
  thinking?: string;
  is_dirty?: boolean;
  version?: number;
  word_count?: number;
}

export interface Volume {
  volume_index: number;
  title: string;
  summary: string;
  chapters?: Chapter[];
}

export interface TemporalEntity {
  id: string;
  novel_id: string;
  name: string;
  entity_type: 'character' | 'item' | 'location' | 'faction' | 'concept';
  summary: string;
  attributes: Record<string, any>;
  created_chapter: number;
  updated_chapter: number;
}

export interface TemporalFact {
  id: string;
  novel_id: string;
  source_entity_id?: string | null;
  target_entity_id?: string | null;
  source_name?: string;
  target_name?: string;
  relation_type?: string;
  fact_statement: string;
  valid_from_chapter: number;
  invalid_from_chapter?: number | null;
  is_active: boolean;
  superseded_by?: string | null;
}

export interface TemporalEpisode {
  id: string;
  novel_id: string;
  chapter_index: number;
  summary: string;
  content_hash?: string;
  created_at?: string;
}

export interface TemporalGraphSlice {
  novel_id: string;
  chapter_slice: number | null;
  entities: TemporalEntity[];
  facts: TemporalFact[];
  episodes: TemporalEpisode[];
}

export interface StoryTerm {
  id: string;
  novel_id: string;
  category: string;
  term: string;
  definition: string;
  notes?: string;
  created_at?: string;
}

export interface ReviewComment {
  type: 'pacing' | 'character_voice' | 'plot_hole' | 'atmosphere' | 'grammar';
  severity?: 'critical' | 'suggestion' | 'praise';
  comment: string;
  accepted?: boolean;
}

export interface DraftProposal {
  id: string;
  novel_id: string;
  chapter_index: number;
  original_text: string;
  proposed_text: string;
  review_comments: ReviewComment[];
  status: 'pending' | 'accepted' | 'rejected' | 'revised';
  created_at?: string;
}

export interface AgentConfig {
  agent_name: string;
  api_key: string;
  base_url: string;
  model: string;
  temperature: number;
  top_p: number;
  max_tokens: number;
  enable_thinking: number;
}
