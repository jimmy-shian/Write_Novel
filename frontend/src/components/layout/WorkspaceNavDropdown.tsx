import React, { useState, useRef, useEffect } from 'react';
import { ActiveView } from './ActivityRail';

export type WorldviewSubTab = 'worldview' | 'characters' | 'plot';

interface WorkspaceNavDropdownProps {
  activeView: ActiveView;
  worldviewTab?: WorldviewSubTab;
  onSelectView: (view: ActiveView, subTab?: WorldviewSubTab) => void;
  className?: string;
}

interface NavItem {
  id: string;
  label: string;
  view: ActiveView;
  subTab?: WorldviewSubTab;
}

interface NavGroup {
  id: string;
  title: string;
  items: NavItem[];
}

export const WorkspaceNavDropdown: React.FC<WorkspaceNavDropdownProps> = ({
  activeView,
  worldviewTab = 'worldview',
  onSelectView,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // 選單文字與「AI 導演總控室」完全一致對齊：世界觀構建 / 分卷結構 / 卷章細綱 / 正文撰寫 / 審閱修訂
  const navGroups: NavGroup[] = [
    {
      id: 'outline',
      title: '架構與大綱',
      items: [
        { id: 'worldview', label: '世界觀構建', view: 'worldview', subTab: 'worldview' },
        { id: 'volumes', label: '分卷結構', view: 'worldview', subTab: 'plot' },
        { id: 'volume_skeleton', label: '卷章細綱', view: 'worldview', subTab: 'plot' },
      ],
    },
    {
      id: 'writing',
      title: '正文與審閱',
      items: [
        { id: 'writer', label: '正文撰寫', view: 'editor' },
        { id: 'editor', label: '審閱修訂', view: 'diff' },
      ],
    },
  ];

  const getCurrentLabel = () => {
    if (activeView === 'editor') return '正文撰寫';
    if (activeView === 'diff') return '審閱修訂';
    if (activeView === 'worldview') {
      if (worldviewTab === 'plot') return '分卷結構 / 卷章細綱';
      return '世界觀構建';
    }
    return '正文撰寫';
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent | TouchEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('touchstart', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  const handleSelect = (item: NavItem) => {
    onSelectView(item.view, item.subTab);
    setIsOpen(false);
  };

  const isItemActive = (item: NavItem) => {
    if (item.view !== activeView) return false;
    if (item.view === 'worldview') {
      return item.subTab === worldviewTab;
    }
    return true;
  };

  return (
    <div
      ref={containerRef}
      className={`custom-select topbar-view-select ${isOpen ? 'open' : ''} ${className}`}
    >
      <div
        className="select-trigger"
        onClick={() => setIsOpen((prev) => !prev)}
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
      >
        <span className="select-trigger-text">
          <span className="select-main-label">{getCurrentLabel()}</span>
        </span>
        <div className="arrow" aria-hidden="true" />
      </div>

      <div className="select-options topbar-view-options" role="listbox">
        {navGroups.map((group) => (
          <div key={group.id} className="topbar-option-group">
            <div className="topbar-group-title">{group.title}</div>
            {group.items.map((item) => {
              const active = isItemActive(item);
              return (
                <div
                  key={item.id}
                  className={`option ${active ? 'selected' : ''}`}
                  onClick={() => handleSelect(item)}
                  role="option"
                  aria-selected={active}
                >
                  <span className="option-label">{item.label}</span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};
