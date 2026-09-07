import React from 'react';
import { APP_VERSION } from '../../config/version';
import {
  IconFileText,
  IconGitBranch,
  IconBook,
  IconCpu,
  IconBookmark,
  IconSettings,
} from '../common/Icons';

export type ActiveView = 'editor' | 'diff' | 'graph' | 'worldview' | 'proposals' | 'terms';

interface ActivityRailProps {
  activeView: ActiveView;
  onSelectView: (view: ActiveView) => void;
  onOpenSettings: () => void;
}

export const ActivityRail: React.FC<ActivityRailProps> = ({
  activeView,
  onSelectView,
  onOpenSettings,
}) => {
  return (
    <nav className="activity-rail" aria-label="活動導航列">
      <div className="rail-group">
        <button
          type="button"
          className={`rail-btn ${activeView === 'editor' ? 'active' : ''}`}
          onClick={() => onSelectView('editor')}
          data-tooltip="章節編輯器"
          data-tooltip-pos="right"
          aria-label="章節編輯器"
        >
          <IconFileText size={18} />
          <span className="rail-btn-label">正文</span>
        </button>

        <button
          type="button"
          className={`rail-btn ${activeView === 'diff' ? 'active' : ''}`}
          onClick={() => onSelectView('diff')}
          data-tooltip="版本對比與審閱 (Diff)"
          data-tooltip-pos="right"
          aria-label="版本對比與審閱"
        >
          <IconGitBranch size={18} />
          <span className="rail-btn-label">審閱</span>
        </button>

        <button
          type="button"
          className={`rail-btn ${activeView === 'worldview' ? 'active' : ''}`}
          onClick={() => onSelectView('worldview')}
          data-tooltip="世界觀構建與角色聖經"
          data-tooltip-pos="right"
          aria-label="世界觀構建與角色聖經"
        >
          <IconBook size={18} />
          <span className="rail-btn-label">世界</span>
        </button>

        <button
          type="button"
          className={`rail-btn ${activeView === 'graph' ? 'active' : ''}`}
          onClick={() => onSelectView('graph')}
          data-tooltip="時序記憶圖譜 (Graphiti)"
          data-tooltip-pos="right"
          aria-label="時序記憶圖譜"
        >
          <IconCpu size={18} />
          <span className="rail-btn-label">圖譜</span>
        </button>

        <button
          type="button"
          className={`rail-btn ${activeView === 'terms' ? 'active' : ''}`}
          onClick={() => onSelectView('terms')}
          data-tooltip="故事專用術語庫 (Glossary)"
          data-tooltip-pos="right"
          aria-label="故事專用術語庫"
        >
          <IconBookmark size={18} />
          <span className="rail-btn-label">術語</span>
        </button>
      </div>

      <div className="rail-group">
        <button
          type="button"
          className="rail-btn"
          onClick={onOpenSettings}
          data-tooltip="系統與雲端參數設定"
          data-tooltip-pos="right"
          aria-label="系統設定"
        >
          <IconSettings size={18} />
          <span className="rail-btn-label">設定</span>
        </button>
        <span
          className="rail-version-tag"
          data-tooltip={`版本: v${APP_VERSION}`}
          data-tooltip-pos="right"
        >
          v{APP_VERSION.split('.')[0]}
        </span>
      </div>
    </nav>
  );
};