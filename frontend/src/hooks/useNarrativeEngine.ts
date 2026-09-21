import { useState, useEffect, useCallback, useRef } from 'react';
import { SettingSystem, ConflictSignature, NarrativeAudit, NarrativeProfile } from '../types';
import {
  getSettingSystems,
  getConflictSignatures,
  getNarrativeAudits,
  getNarrativeProfile,
} from '../api/narrative';
import { NARRATIVE_REFRESH_EVENT, ChapterContentUpdatedDetail } from '../utils/narrativeRefresh';

/**
 * Story Engine 2.0 敘事推理看板資料層（模組化 SSOT）。
 * 照 useTemporalGraph 模式封裝載入與手動刷新，
 * 並內建 3 秒背景輪詢：流水線逐章寫作時看板與待處置診斷會自動更新，
 * 無需手動按「重新整理」。頁面隱藏時暫停輪詢以節省請求。
 */
export function useNarrativeEngine(novelId: string | null, pollIntervalMs: number = 3000) {
  const [settingSystems, setSettingSystems] = useState<SettingSystem[]>([]);
  const [conflictSignatures, setConflictSignatures] = useState<ConflictSignature[]>([]);
  const [narrativeAudits, setNarrativeAudits] = useState<NarrativeAudit[]>([]);
  const [narrativeProfile, setNarrativeProfile] = useState<NarrativeProfile | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const inFlightRef = useRef<boolean>(false);

  const loadNarrativeData = useCallback(async (silent: boolean = false) => {
    if (!novelId || inFlightRef.current) return;
    inFlightRef.current = true;
    if (!silent) setIsLoading(true);
    setError(null);
    try {
      const [sys, sigs, audits, prof] = await Promise.all([
        getSettingSystems(novelId).catch(() => []),
        getConflictSignatures(novelId, 60).catch(() => []),
        getNarrativeAudits(novelId, undefined, false, 60).catch(() => []),
        getNarrativeProfile(novelId).catch(() => null),
      ]);
      setSettingSystems(sys);
      setConflictSignatures(sigs);
      setNarrativeAudits(audits);
      setNarrativeProfile(prof);
    } catch (err: any) {
      setError(err.message || '載入敘事推理資料失敗');
    } finally {
      inFlightRef.current = false;
      if (!silent) setIsLoading(false);
    }
  }, [novelId]);

  // 初次載入 + 切換作品時重載
  useEffect(() => {
    loadNarrativeData();
  }, [loadNarrativeData]);

  // 章節正文生成完成即時刷新：和前端正文同步更新顯示，不等 3 秒輪詢
  useEffect(() => {
    if (!novelId) return;
    const listener = (e: Event) => {
      const detail = (e as CustomEvent<ChapterContentUpdatedDetail>).detail;
      if (!detail || detail.novelId !== novelId) return;
      loadNarrativeData(true);
    };
    window.addEventListener(NARRATIVE_REFRESH_EVENT, listener);
    return () => window.removeEventListener(NARRATIVE_REFRESH_EVENT, listener);
  }, [novelId, loadNarrativeData]);

  // 3 秒背景輪詢（靜默刷新，不觸發 loading 閃爍）
  useEffect(() => {
    if (!novelId) return;
    const timer = setInterval(() => {
      if (!document.hidden) {
        loadNarrativeData(true);
      }
    }, pollIntervalMs);
    return () => clearInterval(timer);
  }, [novelId, loadNarrativeData, pollIntervalMs]);

  return {
    settingSystems,
    conflictSignatures,
    narrativeAudits,
    narrativeProfile,
    isLoading,
    error,
    refresh: loadNarrativeData,
  };
}