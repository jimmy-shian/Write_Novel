import React from 'react';
import { Button } from '../common/Button';
import { IconCopy, IconEdit } from '../common/Icons';
import type { WorldviewTab } from './WorldviewPane';

interface WorldviewPaneHeaderProps {
  activeTab: WorldviewTab;
  novel: {
    title: string;
    genre?: string | null;
    style?: string | null;
  };
  characterCount: number;
  volumeCount: number;
  fontSize: number;
  copiedContent: boolean;
  isSaving: boolean;
  saveSuccess: boolean;
  worldbuildingViewMode: 'card' | 'raw';
  charactersViewMode: 'card' | 'raw';
  plotViewMode: 'card' | 'raw';
  onTabChange: (tab: WorldviewTab) => void;
  onWorldbuildingViewModeChange: () => void;
  onCharactersViewModeChange: () => void;
  onPlotViewModeChange: () => void;
  onRefresh?: () => void;
  onSave: () => void;
  onEditNovel: () => void;
  onFontSizeChange?: (size: number) => void;
  onCopyContent: () => void;
}

export const WorldviewPaneHeader: React.FC<WorldviewPaneHeaderProps> = ({
  activeTab,
  novel,
  characterCount,
  volumeCount,
  fontSize,
  copiedContent,
  isSaving,
  saveSuccess,
  worldbuildingViewMode,
  charactersViewMode,
  plotViewMode,
  onTabChange,
  onWorldbuildingViewModeChange,
  onCharactersViewModeChange,
  onPlotViewModeChange,
  onRefresh,
  onSave,
  onEditNovel,
  onFontSizeChange,
  onCopyContent,
}) => (
  <>
    <div className="worldview-header">
      <div className="worldview-tabs">
        <button
          type="button"
          className={`worldview-tab-btn ${activeTab === 'worldview' ? 'active' : ''}`}
          onClick={() => onTabChange('worldview')}
        >
          世界觀構建
        </button>
        <button
          type="button"
          className={`worldview-tab-btn ${activeTab === 'characters' ? 'active' : ''}`}
          onClick={() => onTabChange('characters')}
        >
          角色聖經 {characterCount > 0 && `(${characterCount})`}
        </button>
        <button
          type="button"
          className={`worldview-tab-btn ${activeTab === 'plot' ? 'active' : ''}`}
          onClick={() => onTabChange('plot')}
        >
          分卷骨架與大綱 {volumeCount > 0 && `(${volumeCount}卷)`}
        </button>
      </div>

      <div className="worldview-actions">
        {activeTab === 'worldview' && (
          <>
            <Button size="xs" variant="secondary" onClick={onWorldbuildingViewModeChange} title="切換卡片或純文字檢視">
              {worldbuildingViewMode === 'card' ? '切換純文字 / JSON' : '切換結構化卡片'}
            </Button>
            <span className="btn-divider" />
          </>
        )}
        {activeTab === 'characters' && (
          <>
            <Button size="xs" variant="secondary" onClick={onCharactersViewModeChange} title="切換卡片清單或純文字檢視">
              {charactersViewMode === 'card' ? '切換純文字 / JSON' : '切換卡片清單'}
            </Button>
            <span className="btn-divider" />
          </>
        )}
        {activeTab === 'plot' && (
          <>
            <Button size="xs" variant="secondary" onClick={onPlotViewModeChange} title="切換分卷骨架或純文字檢視">
              {plotViewMode === 'card' ? '切換純文字 / JSON' : '切換分卷骨架'}
            </Button>
            <span className="btn-divider" />
          </>
        )}
        <Button size="xs" variant="secondary" onClick={onRefresh} title="重新整理資料">
          重新整理
        </Button>
        <span className="btn-divider" />
        <Button size="xs" variant="primary" onClick={onSave} isLoading={isSaving} disabled={isSaving} title="儲存變更至資料庫">
          {saveSuccess ? '已儲存' : '儲存變更'}
        </Button>
      </div>
    </div>

    <div className="worldview-quick-card">
      <div className="quick-card-left">
        <div className="quick-card-title-row" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="quick-card-title clickable-title" onClick={onEditNovel} title="點擊編輯小說名稱、題材與文風" style={{ cursor: 'pointer' }}>
            {novel.title}
          </span>
          <button type="button" className="btn btn-ghost btn-xs edit-meta-btn" onClick={onEditNovel} title="重新編輯小說名稱、題材與文風設定" style={{ padding: '2px 6px', fontSize: '11px', color: 'var(--text-muted)' }}>
            <IconEdit size={12} />
            <span>編輯設定</span>
          </button>
        </div>
        <div className="quick-card-meta-line"><span className="meta-label">題材：</span><span className="meta-val">{novel.genre ? `【${novel.genre}】` : '未設定'}</span></div>
        <div className="quick-card-meta-line"><span className="meta-label">文風：</span><span className="meta-val">{novel.style || '未設定'}</span></div>
      </div>
      <div className="quick-card-right" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {onFontSizeChange && (
          <div className="font-size-stepper" title="調整中間區塊文字大小">
            <button type="button" className="stepper-btn" onClick={() => onFontSizeChange(Math.max(14, fontSize - 1))} disabled={fontSize <= 14} title="縮小文字 (A-)">A-</button>
            <span className="stepper-val">{fontSize}px</span>
            <button type="button" className="stepper-btn" onClick={() => onFontSizeChange(Math.min(24, fontSize + 1))} disabled={fontSize >= 24} title="放大文字 (A+)">A+</button>
          </div>
        )}
        <button type="button" className="btn btn-secondary btn-xs copy-content-btn" onClick={onCopyContent} title="一鍵複製本區文字">
          <IconCopy size={13} />
          <span>{copiedContent ? '已複製！' : '一鍵複製'}</span>
        </button>
      </div>
    </div>
  </>
);
