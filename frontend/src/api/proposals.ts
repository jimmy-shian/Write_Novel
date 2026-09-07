import { request } from './client';
import { DraftProposal, ReviewComment } from '../types';

export async function listProposals(
  novelId: string,
  chapterIndex?: number | null,
  status?: string | null
): Promise<{ novel_id: string; proposals: DraftProposal[] }> {
  const params = new URLSearchParams();
  if (chapterIndex !== undefined && chapterIndex !== null) {
    params.set('chapter', String(chapterIndex));
  }
  if (status) {
    params.set('status', status);
  }
  const query = params.toString() ? `?${params.toString()}` : '';
  return request(`/api/novels/${novelId}/proposals${query}`);
}

export async function createProposal(
  novelId: string,
  payload: {
    chapter_index: number;
    proposed_text: string;
    original_text?: string;
    review_comments?: ReviewComment[];
  }
): Promise<DraftProposal> {
  return request<DraftProposal>(`/api/novels/${novelId}/proposals`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getProposal(
  novelId: string,
  proposalId: string
): Promise<DraftProposal> {
  return request<DraftProposal>(`/api/novels/${novelId}/proposals/${proposalId}`);
}

export async function updateProposalStatus(
  novelId: string,
  proposalId: string,
  status: 'pending' | 'accepted' | 'rejected' | 'revised'
): Promise<{ status: string; proposal_id: string; new_status: string }> {
  return request(`/api/novels/${novelId}/proposals/${proposalId}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  });
}

export async function applyProposal(
  novelId: string,
  proposalId: string
): Promise<{ status: string; proposal_id: string; chapter_index: number; version: number }> {
  return request(`/api/novels/${novelId}/proposals/${proposalId}/apply`, {
    method: 'POST',
  });
}
