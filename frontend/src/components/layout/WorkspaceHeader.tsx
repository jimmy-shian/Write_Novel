import React, { useState, useRef, useEffect } from 'react';
import { Novel } from '../../types';
import { StatusDot } from '../common/StatusDot';
import { Button } from '../common/Button';
import { IconDownload } from '../common/Icons';
import { downloadNovelExport } from '../../api/novels';
import { ActiveView } from './ActivityRail';
import { WorkspaceNavDropdown, WorldviewSubTab } from './WorkspaceNavDropdown';

interface WorkspaceHeaderProps {
  activeNovel: Novel | null;
  activeChapterIndex: number;
  activeChapterTitle?: string;
  isDirty: boolean;
  isSaving: boolean;
  isLoading?: boolean;
  activeView: ActiveView;
  worldviewTab?: WorldviewSubTab;
  structureSubTab?: 'geometry' | 'graph' | 'narrative';
  onSave: () => void;
  onToggleExplorerMobile: () => void;
  onToggleCopilotMobile: () => void;
  onSelectView: (view: ActiveView, subTab?: any) => void;
}

export const WorkspaceHeader: React.FC<WorkspaceHeaderProps> = ({
  activeNovel,
  activeChapterIndex,
  activeChapterTitle = '',
  isDirty,
  isSaving,
  isLoading = false,
  activeView,
  worldviewTab,
  structureSubTab = 'geometry',
  onSave,
  onToggleExplorerMobile,
  onToggleCopilotMobile,
  onSelectView,
}) => {
  const [isExportMenuOpen, setIsExportMenuOpen] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setIsExportMenuOpen(false);
      }
    };
    if (isExportMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isExportMenuOpen]);

  const handleExport = (format: 'html' | 'txt') => {
    if (!activeNovel) return;
    downloadNovelExport(activeNovel.id, format);
    setIsExportMenuOpen(false);
  };

  // 推理群組（故事架構中樞：幾何 / 時序圖譜 / 推理引擎）時，
  // 上方「第 X 章」位置的 hover tips 改為顯示「故事架構與推演中樞」；
  // 正文顯示的章名稱文字與左側樹狀圖細綱維持不變。
  const isReasoningGroup =
    activeView === 'structure' ||
    activeView === 'geometry' ||
    activeView === 'graph' ||
    activeView === 'narrative';
  const chapterTip = isReasoningGroup
    ? '故事架構與推演中樞'
    : activeChapterTitle
      ? `第 ${activeChapterIndex} 章：${activeChapterTitle}`
      : `第 ${activeChapterIndex} 章`;

  const novelTitle = activeNovel ? activeNovel.title : '未選擇作品';
  // 正文撰寫視窗下，故事名稱的 hover tips 顯示章節名稱（頂欄只露出章號，全名藏在這裡）；
  // 其他視窗維持顯示故事名稱。
  const novelTip =
    activeView === 'editor'
      ? (activeChapterTitle
        ? `第 ${activeChapterIndex} 章：${activeChapterTitle}`
        : `第 ${activeChapterIndex} 章`)
      : novelTitle;
  // 超過 5 個字才跑馬燈（中日韓文字以字元數計，含代理對安全算法）
  const isLongNovelTitle = Array.from(novelTitle).length > 5;

  return (
    <header className="workspace-topbar">
      <div className="topbar-left">
        <button
          type="button"
          className="btn btn-ghost btn-xs mobile-menu-btn"
          onClick={onToggleExplorerMobile}
          data-tooltip="開啟作品目錄導航"
          data-tooltip-pos="bottom"
        >
          [目錄]
        </button>


        <span
          className="tooltip-ellipsis-wrap tooltip-novel-wrap"
          data-tooltip={novelTip}
          data-tooltip-pos="bottom"
        >
          {isLongNovelTitle ? (
            <span className="novel-title-text marquee-on-hover">
              <span className="marquee-track">
                <span className="marquee-seg">{novelTitle}</span>
                <span className="marquee-seg" aria-hidden="true">{novelTitle}</span>
              </span>
            </span>
          ) : (
            <span className="novel-title-text">{novelTitle}</span>
          )}
        </span>
        {isLoading && (
          <span
            className="select-spinner topbar-loading-spinner"
            data-tooltip="正在載入作品與章節資料..."
            data-tooltip-pos="bottom"
          />
        )}
        <span className="topbar-separator">/</span>
        <span
          className="tooltip-ellipsis-wrap"
          data-tooltip={chapterTip}
          data-tooltip-pos="bottom"
        >
          <span className="chapter-title-text">
            第 {activeChapterIndex} 章
          </span>
        </span>

        <span
          className="save-status-indicator"
          data-tooltip={isSaving ? '儲存中...' : isDirty ? '有未儲存變更' : '已同步儲存'}
          data-tooltip-pos="bottom"
        >
          <StatusDot
            status={isSaving ? 'warning' : isDirty ? 'danger' : 'success'}
          />
          <span className="save-status-label">
            {isSaving ? '儲存中...' : isDirty ? '未儲存' : '已同步'}
          </span>
        </span>
      </div>

      <div className="topbar-right">
        {/* View Switcher Dropdown: 世界觀 / 卷 / 章 / 正文 / 比對 */}
        <WorkspaceNavDropdown
          activeView={activeView}
          worldviewTab={worldviewTab}
          structureSubTab={structureSubTab}
          onSelectView={onSelectView}
        />

        {/* Save button */}
        <Button
          size="sm"
          className="topbar-save-btn"
          variant="primary"
          onClick={onSave}
          disabled={!isDirty || isSaving}
        >
          儲存
        </Button>

        {/* Export Novel Dropdown */}
        <div className="view-switcher-dropdown" ref={exportMenuRef}>
          <Button
            size="sm"
            variant="secondary"
            className="topbar-export-btn"
            disabled={!activeNovel}
            onClick={() => setIsExportMenuOpen(!isExportMenuOpen)}
            data-tooltip="匯出作品檔案 (支援離線 HTML 便攜閱讀器與 TXT)"
            data-tooltip-pos="bottom"
            icon={<IconDownload size={13} />}
          >
            匯出
          </Button>
          {isExportMenuOpen && (
            <div className="view-switcher-menu topbar-export-menu">
              <button
                type="button"
                className="view-switcher-item"
                onClick={() => handleExport('html')}
              >
                HTML 便攜閱讀器 (.html)
              </button>
              <button
                type="button"
                className="view-switcher-item"
                onClick={() => handleExport('txt')}
              >
                純文字全書 (.txt)
              </button>
            </div>
          )}
        </div>

        {/* Mobile Copilot Trigger */}
        <button
          type="button"
          className="btn btn-ghost btn-xs mobile-copilot-btn"
          onClick={onToggleCopilotMobile}
          data-tooltip="開啟 AI 導演對話"
          data-tooltip-pos="bottom"
        >
          [導演]
        </button>
      </div>
    </header>
  );
};
