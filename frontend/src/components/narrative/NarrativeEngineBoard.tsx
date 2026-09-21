import React, { useState } from 'react';
import { Novel } from '../../types';
import { Button } from '../common/Button';
import {
  IconCompass,
  IconShield,
  IconSparkles,
  IconLayers,
  IconRefresh,
} from '../common/Icons';
import { syncSettingSystemsFromWorldview } from '../../api/narrative';
import { useNarrativeEngine } from '../../hooks/useNarrativeEngine';
import { SettingSystemsTab } from './SettingSystemsTab';
import { ConflictSignaturesTab } from './ConflictSignaturesTab';
import { NarrativeAuditsTab } from './NarrativeAuditsTab';
import { NarrativeProfileTab } from './NarrativeProfileTab';
import { showToast } from '../common/Toast';

export type NarrativeSubTab = 'settings' | 'conflicts' | 'audits' | 'profile';

interface NarrativeEngineBoardProps {
  novel: Novel | null;
  activeChapterIndex: number;
}

export const NarrativeEngineBoard: React.FC<NarrativeEngineBoardProps> = ({
  novel,
  activeChapterIndex,
}) => {
  const [currentTab, setCurrentTab] = useState<NarrativeSubTab>('settings');
  const [isSyncing, setIsSyncing] = useState<boolean>(false);

  const novelId = novel?.id || '';

  // 模組化資料層：3 秒自動輪詢刷新（流水線寫作時看板即時更新）
  const {
    settingSystems,
    conflictSignatures,
    narrativeAudits,
    narrativeProfile,
    isLoading,
    error,
    refresh: loadNarrativeData,
  } = useNarrativeEngine(novelId || null);

  // Sync from Worldview handler
  const handleSyncWorldview = async () => {
    if (!novelId) return;
    setIsSyncing(true);
    try {
      const res = await syncSettingSystemsFromWorldview(novelId);
      showToast(`世界觀設定同步完成，提煉出 ${res.synced_count} 個運作態設定實體！`, 'success');
      await loadNarrativeData(false);
    } catch (err: any) {
      showToast(`同步世界觀失敗: ${err.message}`, 'danger');
    } finally {
      setIsSyncing(false);
    }
  };

  const unresolvedAuditsCount = narrativeAudits.filter((a) => !a.resolved).length;

  if (!novel) {
    return (
      <div className="narrative-empty-screen">
        <IconCompass size={40} className="text-muted" />
        <p className="empty-title">請先選擇或建立一部作品</p>
        <p className="empty-desc">Story Engine 2.0 敘事推理引擎需要以特定作品為目標進行長程因果治理。</p>
      </div>
    );
  }

  return (
    <div className="narrative-engine-board">
      {/* 頁籤列＋重新整理合併為一列（計數已在各頁籤標籤內，統計 chip 列整並刪除） */}
      <nav className="narrative-nav-tabs" aria-label="敘事推理頁籤">
        <button
          type="button"
          className={`narrative-nav-btn ${currentTab === 'settings' ? 'active' : ''}`}
          onClick={() => setCurrentTab('settings')}
          data-tooltip="由世界觀提煉的力量體系與運作規則庫"
          data-tooltip-pos="bottom"
        >
          <IconShield size={16} />
          <span>世界觀運作庫 ({settingSystems.length})</span>
        </button>

        <button
          type="button"
          className={`narrative-nav-btn ${currentTab === 'conflicts' ? 'active' : ''}`}
          onClick={() => setCurrentTab('conflicts')}
          data-tooltip="長程因果鏈與衝突模式帳本"
          data-tooltip-pos="bottom"
        >
          <IconLayers size={16} />
          <span>因果簽名帳本 ({conflictSignatures.length})</span>
        </button>

        <button
          type="button"
          className={`narrative-nav-btn ${currentTab === 'audits' ? 'active' : ''}`}
          onClick={() => setCurrentTab('audits')}
          data-tooltip="總監 2.0 對全書的審計診斷與處置建議"
          data-tooltip-pos="bottom"
        >
          <IconSparkles size={16} />
          <span>總監 2.0 審計診斷</span>
          {unresolvedAuditsCount > 0 && (
            <span className="tab-pill-badge">{unresolvedAuditsCount}</span>
          )}
        </button>

        <button
          type="button"
          className={`narrative-nav-btn ${currentTab === 'profile' ? 'active' : ''}`}
          onClick={() => setCurrentTab('profile')}
          data-tooltip="作品整體敘事風格與結構畫像"
          data-tooltip-pos="bottom"
        >
          <IconCompass size={16} />
          <span>作品敘事畫像</span>
        </button>

        <span className="narrative-nav-spacer" />
        <Button
          size="sm"
          variant="ghost"
          className="narrative-nav-refresh"
          onClick={() => loadNarrativeData(false)}
          isLoading={isLoading}
          icon={<IconRefresh size={14} />}
          data-tooltip="刷新所有敘事推理資料（看板亦會每 3 秒自動同步）"
          data-tooltip-pos="bottom"
        >
          重新整理
        </Button>
      </nav>

      {/* Tab Content Viewports */}
      {error && (
        <div
          style={{ padding: '8px 16px', color: 'var(--color-danger, #e5484d)', fontSize: 12 }}
        >
          載入敘事推理資料失敗: {error}
        </div>
      )}
      <div className="narrative-board-body">
        {currentTab === 'settings' && (
          <SettingSystemsTab
            novelId={novelId}
            systems={settingSystems}
            isLoading={isLoading}
            isSyncing={isSyncing}
            onRefresh={loadNarrativeData}
            onSyncFromWorldview={handleSyncWorldview}
          />
        )}

        {currentTab === 'conflicts' && (
          <ConflictSignaturesTab
            novelId={novelId}
            signatures={conflictSignatures}
            isLoading={isLoading}
            onRefresh={loadNarrativeData}
          />
        )}

        {currentTab === 'audits' && (
          <NarrativeAuditsTab
            novelId={novelId}
            audits={narrativeAudits}
            activeChapterIndex={activeChapterIndex}
            isLoading={isLoading}
            onRefresh={loadNarrativeData}
          />
        )}

        {currentTab === 'profile' && (
          <NarrativeProfileTab
            novelId={novelId}
            profile={narrativeProfile}
            isLoading={isLoading}
            onRefresh={loadNarrativeData}
          />
        )}
      </div>
    </div>
  );
};
