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
      >
        <IconBook size={18} />
        <span>目錄</span>
      </button>

      <button
        type="button"
        className={`mobile-nav-item ${isEditorActive ? 'active' : ''}`}
        onClick={onFocusEditor}
      >
        <IconFileText size={18} />
        <span>正文</span>
      </button>

      <button
        type="button"
        className={`mobile-nav-item ${isCopilotOpen ? 'active' : ''}`}
        onClick={onToggleCopilot}
      >
        <IconCpu size={18} />
        <span>導演</span>
      </button>
    </nav>
  );
};
