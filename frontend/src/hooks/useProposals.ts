import { useState, useEffect, useCallback } from 'react';
import { DraftProposal } from '../types';
import {
  listProposals,
  createProposal,
  updateProposalStatus,
  applyProposal,
} from '../api/proposals';

export function useProposals(novelId: string | null, chapterIndex: number) {
  const [proposals, setProposals] = useState<DraftProposal[]>([]);
  const [selectedProposal, setSelectedProposal] = useState<DraftProposal | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProposals = useCallback(async () => {
    if (!novelId) {
      setProposals([]);
      setSelectedProposal(null);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const res = await listProposals(novelId, chapterIndex);
      setProposals(res.proposals || []);
      if (res.proposals && res.proposals.length > 0) {
        // Default select first pending proposal or first proposal
        const pending = res.proposals.find((p) => p.status === 'pending');
        setSelectedProposal(pending || res.proposals[0]);
      } else {
        setSelectedProposal(null);
      }
    } catch (err: any) {
      setError(err.message || '無法取得草稿建議清單');
    } finally {
      setIsLoading(false);
    }
  }, [novelId, chapterIndex]);

  useEffect(() => {
    fetchProposals();
  }, [fetchProposals]);

  const handleApply = useCallback(
    async (proposalId: string) => {
      if (!novelId) return false;
      try {
        await applyProposal(novelId, proposalId);
        await fetchProposals();
        return true;
      } catch (err: any) {
        setError(err.message || '套用建議失敗');
        return false;
      }
    },
    [novelId, fetchProposals]
  );

  const handleReject = useCallback(
    async (proposalId: string) => {
      if (!novelId) return false;
      try {
        await updateProposalStatus(novelId, proposalId, 'rejected');
        await fetchProposals();
        return true;
      } catch (err: any) {
        setError(err.message || '拒絕建議失敗');
        return false;
      }
    },
    [novelId, fetchProposals]
  );

  return {
    proposals,
    selectedProposal,
    setSelectedProposal,
    isLoading,
    error,
    refreshProposals: fetchProposals,
    applyProposal: handleApply,
    rejectProposal: handleReject,
  };
}
