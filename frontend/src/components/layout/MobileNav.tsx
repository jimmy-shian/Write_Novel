import React from 'react';
import { IconBook, IconFileText, IconCpu } from '../common/Icons';

interface MobileNavProps {
  isExplorerOpen: boolean;
  isCopilotOpen: boolean;
  onToggleExplorer: () => void;
  onToggleCopilot: () => void;
  onFocusEditor: () => void;
}

export const MobileNav: React.FC<MobileNavProps> = ({
  isExplorerOpen,
  isCopilotOpen,
  onToggleExplorer,
  onToggleCopilot,
  onFocusEditor,
}) => {
  const isEditorActive = !isExplorerOpen && !isCopilotOpen;

  return (
    <nav className="mobile-nav" aria-label="行動版導航">
      <button
        type="button"
        className={`mobile-nav-item ${isExplorerOpen ? 'active' : ''}`}
        onClick={onToggleExplorer}
        data-tooltip="開啟作品目錄"
        data-tooltip-pos="top"
        aria-label="開啟作品目錄"
      >
        <IconBook size={18} />
        <span>目錄</span>
      </button>

      <button
        type="button"
        className={`mobile-nav-item ${isEditorActive ? 'active' : ''}`}
        onClick={onFocusEditor}
        data-tooltip="回到正文編輯"
        data-tooltip-pos="top"
        aria-label="回到正文編輯"
      >
        <IconFileText size={18} />
        <span>正文</span>
      </button>

      <button
        type="button"
        className={`mobile-nav-item ${isCopilotOpen ? 'active' : ''}`}
        onClick={onToggleCopilot}
        data-tooltip="開啟 AI 導演對話"
        data-tooltip-pos="top"
        aria-label="開啟 AI 導演對話"
      >
        <IconCpu size={18} />
        <span>導演</span>
      </button>
    </nav>
  );
};
