/**
 * 敘事幾何 (Narrative Geometry) 型別定義
 * 對應後端 backend.geometry.models 與 API 契約
 */

export type StructuralRole =
  | 'OPEN_THREAD'
  | 'DEVELOP'
  | 'BRANCH'
  | 'REVISIT'
  | 'ESCALATE'
  | 'CONVERGE'
  | 'CHARACTER_SHIFT'
  | 'RELATIONSHIP_CHANGE'
  | 'PAYOFF'
  | 'TRANSITION'
  | 'CLOSE'
  | 'ECHO'
  | string;

export type EdgeType =
  | 'SETS_UP'
  | 'PAYS_OFF'
  | 'ECHOES'
  | 'CONVERGES'
  | 'CONTRASTS'
  | 'CHARACTER_ARC'
  | 'RELATIONSHIP_CHANGE'
  | string;

export type ThreadType =
  | 'MAIN_PLOT'
  | 'SUBPLOT'
  | 'CHARACTER_ARC'
  | 'RELATIONSHIP_ARC'
  | 'THEMATIC'
  | string;

export type GeometryComplexityLevel =
  | 'SPARSE'
  | 'STANDARD'
  | 'DENSE'
  | 'VERY_DENSE';

export interface GeometryNodeDto {
  node_id: string;
  volume_index: number;
  arc_index: number;
  sequence_index: number;
  chapter_start: number;
  chapter_end: number;
  structural_role: StructuralRole;
  primary_thread: string;
  importance: number;
  semantic?: Record<string, any> | null;
  metadata?: Record<string, any>;
}

export interface GeometryEdgeDto {
  edge_id: string;
  source: string;
  target: string;
  edge_type: EdgeType;
  distance: number;
  semantic?: Record<string, any> | null;
  metadata?: Record<string, any>;
}

export interface GeometryThreadDto {
  thread_id: string;
  thread_type: ThreadType;
  node_sequence: string[];
  structural_skeleton: string[];
  semantic?: Record<string, any> | null;
  metadata?: Record<string, any>;
}

export interface GeometryVolumeDto {
  volume_id: string;
  volume_index: number;
  chapter_start: number;
  chapter_end: number;
  arc_ids: string[];
  semantic?: Record<string, any> | null;
}

export interface GeometryStats {
  node_count: number;
  edge_count: number;
  thread_count: number;
  filling_progress: number;
  filled_nodes?: number;
  unfilled_nodes?: number;
}

export interface GeometryParams {
  target_chapters: number;
  volume_count: number;
  complexity: GeometryComplexityLevel | string;
  main_thread_count?: number;
  subplot_count?: number;
  character_arc_count?: number;
  relationship_arc_count?: number;
  thematic_thread_count?: number;
  cross_thread_ratio?: number;
}

export interface GeometryGraphResponse {
  has_geometry: boolean;
  novel_id: string;
  params?: GeometryParams;
  stats: GeometryStats;
  nodes: GeometryNodeDto[];
  edges: GeometryEdgeDto[];
  threads: GeometryThreadDto[];
  volumes: GeometryVolumeDto[];
}

export interface NodeContextPackage {
  novel_id: string;
  chapter_index: number;
  target_node_id: string;
  has_geometry: boolean;
  structural_role: string;
  role_obligation: string;
  incoming_edges_summary: string[];
  outgoing_obligations: string[];
  cross_context_threads: string[];
  echo_contrast_context: string[];
  geometry_overlay_text: string;
  cross_context_text: string;
}

export interface GeometryRepairPayload {
  operation: 'SPLIT' | 'EXPAND' | 'INSERT' | 'COMPRESS' | string;
  condition: string;
  target_nodes?: string[];
  reason?: string;
  detail?: Record<string, any>;
  gatekeeper_context?: Record<string, any>;
}
