import { useState, useEffect, useCallback } from 'react';
import { TemporalGraphSlice, TemporalFact, TemporalEntity } from '../types';
import {
  getTemporalGraph,
  addTemporalFact,
  invalidateTemporalFact,
  deleteTemporalFact,
  extractFactsFromChapter,
} from '../api/temporal';

export function useTemporalGraph(novelId: string | null, chapterIndex: number) {
  const [graphSlice, setGraphSlice] = useState<TemporalGraphSlice | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchGraph = useCallback(async () => {
    if (!novelId) {
      setGraphSlice(null);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const data = await getTemporalGraph(novelId, chapterIndex);
      setGraphSlice(data);
    } catch (err: any) {
      setError(err.message || '無法取得時序知識圖譜');
    } finally {
      setIsLoading(false);
    }
  }, [novelId, chapterIndex]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  const handleAddFact = useCallback(
    async (statement: string) => {
      if (!novelId) return;
      try {
        await addTemporalFact(novelId, {
          fact_statement: statement,
          valid_from_chapter: chapterIndex,
        });
        await fetchGraph();
      } catch (err: any) {
        setError(err.message || '新增事實失敗');
      }
    },
    [novelId, chapterIndex, fetchGraph]
  );

  const handleInvalidateFact = useCallback(
    async (factId: string, supersededBy?: string) => {
      if (!novelId) return;
      try {
        await invalidateTemporalFact(novelId, factId, chapterIndex, supersededBy);
        await fetchGraph();
      } catch (err: any) {
        setError(err.message || '作廢事實失敗');
      }
    },
    [novelId, chapterIndex, fetchGraph]
  );

  const handleDeleteFact = useCallback(
    async (factId: string) => {
      if (!novelId) return;
      try {
        await deleteTemporalFact(novelId, factId);
        await fetchGraph();
      } catch (err: any) {
        setError(err.message || '刪除事實失敗');
      }
    },
    [novelId, fetchGraph]
  );

  const handleExtractFromChapter = useCallback(
    async (chapterContent: string) => {
      if (!novelId || !chapterContent.trim()) return null;
      setIsExtracting(true);
      setError(null);
      try {
        const res = await extractFactsFromChapter(novelId, chapterIndex, chapterContent);
        await fetchGraph();
        return res;
      } catch (err: any) {
        setError(err.message || '提取事實失敗');
        return null;
      } finally {
        setIsExtracting(false);
      }
    },
    [novelId, chapterIndex, fetchGraph]
  );

  return {
    graphSlice,
    isLoading,
    isExtracting,
    error,
    refreshGraph: fetchGraph,
    addFact: handleAddFact,
    invalidateFact: handleInvalidateFact,
    deleteFact: handleDeleteFact,
    extractFromChapter: handleExtractFromChapter,
  };
}
