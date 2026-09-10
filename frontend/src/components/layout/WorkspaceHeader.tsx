import React, { useState, useRef, useEffect } from 'react';
import { Novel } from '../../types';
import { StatusDot } from '../common/StatusDot';
import { Button } from '../common/Button';
import { CustomSelect } from '../common/CustomSelect';
import { IconDownload } from '../common/Icons';
import { downloadNovelExport } from '../../api/novels';
import { ActiveView } from './ActivityRail';

interface WorkspaceHeaderProps {
  activeNovel: Novel | null;
  activeChapterIndex: number;
  isDirty: boolean;
  isSaving: boolean;
  isLoading?: boolean;
  activeView: ActiveView;
  onSave: () => void;
  onToggleExplorerMobile: () => void;
  onToggleCopilotMobile: () => void;
  onSelectView: (view: ActiveView) => void;
}

const VIEW_OPTIONS: { value: string; label: string }[] = [
  { value: 'editor', label: '章節編輯器' },
  { value: 'diff', label: '審閱對比' },
  { value: 'worldview', label: '全書架構大綱' },
  { value: 'graph', label: '記憶圖譜' },
];

export const WorkspaceHeader: React.FC<WorkspaceHeaderProps> = ({
  activeNovel,
  activeChapterIndex,
  isDirty,
  isSaving,
  isLoading = false,
  activeView,
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
          className="novel-title-text marquee-on-hover"
          data-tooltip={activeNovel ? activeNovel.title : '未選擇作品'}
          data-tooltip-pos="bottom"
        >
          {activeNovel ? activeNovel.title : '未選擇作品'}
        </span>
        {isLoading && (
          <span className="select-spinner" title="正在載入作品與章節資料..." style={{ width: 13, height: 13, borderWidth: 2 }} />
        )}
        <span className="topbar-separator">/</span>
        <span className="chapter-title-text">第 {activeChapterIndex} 章</span>

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
        {/* Collapsible View Selector Dropdown */}
        <div className="topbar-view-switcher-dropdown">
          <CustomSelect
            value={activeView}
            options={VIEW_OPTIONS}
            onChange={(val) => onSelectView(val as ActiveView)}
            className="topbar-view-select"
          />
        </div>


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
            title="匯出作品檔案 (支援離線 HTML 便攜閱讀器與 TXT)"
            icon={<IconDownload size={13} />}
          >
            匯出
          </Button>
          {isExportMenuOpen && (
            <div className="view-switcher-menu" style={{ right: 0, left: 'auto', minWidth: '190px' }}>
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
