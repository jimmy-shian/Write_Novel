import { request } from './client';
import { TemporalGraphSlice, TemporalEntity, TemporalFact } from '../types';

export async function getTemporalGraph(
  novelId: string,
  chapterIndex?: number | null
): Promise<TemporalGraphSlice> {
  const query = chapterIndex !== undefined && chapterIndex !== null ? `?chapter=${chapterIndex}` : '';
  return request<TemporalGraphSlice>(`/api/novels/${novelId}/temporal-graph${query}`);
}

export async function upsertTemporalEntity(
  novelId: string,
  payload: {
    name: string;
    entity_type?: 'character' | 'item' | 'location' | 'faction' | 'concept';
    summary?: string;
    attributes?: Record<string, any>;
    chapter_index?: number;
  }
): Promise<TemporalEntity> {
  return request<TemporalEntity>(`/api/novels/${novelId}/temporal-graph/entities`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function deleteTemporalEntity(
  novelId: string,
  entityId: string
): Promise<{ status: string; deleted_id: string }> {
  return request(`/api/novels/${novelId}/temporal-graph/entities/${entityId}`, {
    method: 'DELETE',
  });
}

export async function addTemporalFact(
  novelId: string,
  payload: {
    fact_statement: string;
    valid_from_chapter: number;
    source_entity_id?: string | null;
    target_entity_id?: string | null;
    relation_type?: string;
    episode_id?: string | null;
  }
): Promise<TemporalFact> {
  return request<TemporalFact>(`/api/novels/${novelId}/temporal-graph/facts`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function invalidateTemporalFact(
  novelId: string,
  factId: string,
  invalidFromChapter: number,
  supersededBy?: string | null
): Promise<{ status: string; invalidated_id: string; invalid_from_chapter: number }> {
  return request(`/api/novels/${novelId}/temporal-graph/facts/${factId}/invalidate`, {
    method: 'POST',
    body: JSON.stringify({
      invalid_from_chapter: invalidFromChapter,
      superseded_by: supersededBy,
    }),
  });
}

export async function deleteTemporalFact(
  novelId: string,
  factId: string
): Promise<{ status: string; deleted_id: string }> {
  return request(`/api/novels/${novelId}/temporal-graph/facts/${factId}`, {
    method: 'DELETE',
  });
}

export async function extractFactsFromChapter(
  novelId: string,
  chapterIndex: number,
  chapterContent: string
): Promise<{ status: string; episode_id: string; summary: string; entities_found: number; facts_added: number; invalidated_count: number }> {
  return request(`/api/novels/${novelId}/temporal-graph/extract-from-chapter`, {
    method: 'POST',
    body: JSON.stringify({
      chapter_index: chapterIndex,
      chapter_content: chapterContent,
    }),
  });
}
