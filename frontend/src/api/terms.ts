import { request } from './client';
import { StoryTerm } from '../types';

export async function listTerms(
  novelId: string,
  category?: string
): Promise<{ novel_id: string; terms: StoryTerm[] }> {
  const query = category ? `?category=${encodeURIComponent(category)}` : '';
  return request(`/api/novels/${novelId}/terms${query}`);
}

export async function createTerm(
  novelId: string,
  payload: {
    term: string;
    category?: string;
    definition: string;
    notes?: string;
  }
): Promise<StoryTerm> {
  return request<StoryTerm>(`/api/novels/${novelId}/terms`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateTerm(
  novelId: string,
  termId: string,
  payload: {
    term: string;
    category?: string;
    definition: string;
    notes?: string;
  }
): Promise<{ status: string; updated_id: string }> {
  return request(`/api/novels/${novelId}/terms/${termId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function deleteTerm(
  novelId: string,
  termId: string
): Promise<{ status: string; deleted_id: string }> {
  return request(`/api/novels/${novelId}/terms/${termId}`, {
    method: 'DELETE',
  });
}
