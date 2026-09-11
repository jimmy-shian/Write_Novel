import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ActiveView } from './ActivityRail';
import {
  IconFileText,
  IconGitBranch,
  IconSparkles,
  IconBook,
  IconUsers,
  IconLayers,
  IconCpu,
  IconBookmark,
  IconChevronDown,
  IconCheck,
} from '../common/Icons';

export type WorldviewSubTab = 'worldview' | 'characters' | 'plot';

interface WorkspaceNavDropdownProps {
  activeView: ActiveView;
  worldviewTab?: WorldviewSubTab;
  onSelectView: (view: ActiveView, subTab?: WorldviewSubTab) => void;
  onOpenTerms?: () => void;
  className?: string;
}

interface NavItem {
  id: string;
  view: ActiveView;
  subTab?: WorldviewSubTab;
  label: string;
  desc: string;
  icon: React.ReactNode;
}

interface NavGroup {
  id: string;
  title: string;
  tag: string;
  items: NavItem[];
  isCollapsible?: boolean;
}

export const WorkspaceNavDropdown: React.FC<WorkspaceNavDropdownProps> = ({
  activeView,
  worldviewTab = 'worldview',
  onSelectView,
  onOpenTerms,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isOutlineExpanded, setIsOutlineExpanded] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  const navGroups: NavGroup[] = [
    {
      id: 'writing',
      title: '正文與編修',
      tag: '✍️',
      items: [
        {
          id: 'editor',
          view: 'editor',
          label: '章節編輯器',
          desc: '逐章正文撰寫與靈感創作',
          icon: <IconFileText size={14} />,
        },
        {
          id: 'diff',
          view: 'diff',
          label: '審閱修訂對比',
          desc: '版本差異比對與段落修訂審核',
          icon: <IconGitBranch size={14} />,
        },
        {
          id: 'proposals',
          view: 'proposals',
          label: 'AI 修改提案',
          desc: '審閱建議與段落潤色審批',
          icon: <IconSparkles size={14} />,
        },
      ],
    },
    {
      id: 'outline',
      title: '全書架構與大綱',
      tag: '🗺️',
      isCollapsible: true,
      items: [
        {
          id: 'worldview-settings',
          view: 'worldview',
          subTab: 'worldview',
          label: '世界觀設定',
          desc: '宇宙法則、勢力與修煉體系',
          icon: <IconBook size={14} />,
        },
        {
          id: 'worldview-characters',
          view: 'worldview',
          subTab: 'characters',
          label: '角色聖經',
          desc: '人物小傳、性格慾望與關係網',
          icon: <IconUsers size={14} />,
        },
        {
          id: 'worldview-plot',
          view: 'worldview',
          subTab: 'plot',
          label: '分卷結構與細綱',
          desc: '宏觀主線卷構與 50 章逐章情節綱要',
          icon: <IconLayers size={14} />,
        },
      ],
    },
    {
      id: 'knowledge',
      title: '故事記憶與設定',
      tag: '🧠',
      items: [
        {
          id: 'graph',
          view: 'graph',
          label: '時序記憶圖譜',
          desc: 'Graphiti 實體提取與事件因果樹',
          icon: <IconCpu size={14} />,
        },
        {
          id: 'terms',
          view: 'terms',
          label: '故事專用術語庫',
          desc: '作品專屬名詞、設定與全域詞典',
          icon: <IconBookmark size={14} />,
        },
      ],
    },
  ];

  // Determine current active display info
  const getCurrentInfo = () => {
    if (activeView === 'editor') {
      return { groupTag: '✍️', groupTitle: '正文', label: '章節編輯器', icon: <IconFileText size={13} /> };
    }
    if (activeView === 'diff') {
      return { groupTag: '✍️', groupTitle: '編修', label: '審閱修訂對比', icon: <IconGitBranch size={13} /> };
    }
    if (activeView === 'proposals') {
      return { groupTag: '✍️', groupTitle: '編修', label: 'AI 修改提案', icon: <IconSparkles size={13} /> };
    }
    if (activeView === 'worldview') {
      if (worldviewTab === 'characters') {
        return { groupTag: '🗺️', groupTitle: '架構', label: '角色聖經', icon: <IconUsers size={13} /> };
      }
      if (worldviewTab === 'plot') {
        return { groupTag: '🗺️', groupTitle: '架構', label: '分卷與細綱', icon: <IconLayers size={13} /> };
      }
      return { groupTag: '🗺️', groupTitle: '架構', label: '世界觀設定', icon: <IconBook size={13} /> };
    }
    if (activeView === 'graph') {
      return { groupTag: '🧠', groupTitle: '記憶', label: '時序記憶圖譜', icon: <IconCpu size={13} /> };
    }
    if (activeView === 'terms') {
      return { groupTag: '🧠', groupTitle: '設定', label: '故事術語庫', icon: <IconBookmark size={13} /> };
    }
    return { groupTag: '✍️', groupTitle: '導航', label: '切換視圖', icon: <IconFileText size={13} /> };
  };

  const currentInfo = getCurrentInfo();

  // Close on outside click
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

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  const handleItemClick = (item: NavItem) => {
    if (item.view === 'terms') {
      if (onOpenTerms) {
        onOpenTerms();
      } else {
        onSelectView('terms');
      }
    } else {
      onSelectView(item.view, item.subTab);
    }
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
    <div className={`workspace-nav-dropdown-wrapper ${className}`} ref={containerRef}>
      {/* Trigger Button */}
      <button
        type="button"
        className={`workspace-nav-trigger ${isOpen ? 'active' : ''}`}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="true"
        aria-expanded={isOpen}
        title="點擊展開工作區階層導航選單"
      >
        <div className="trigger-left">
          <span className="trigger-icon">{currentInfo.icon}</span>
          <span className="trigger-group-badge">{currentInfo.groupTitle}</span>
          <span className="trigger-divider">/</span>
          <span className="trigger-label">{currentInfo.label}</span>
        </div>
        <div className={`trigger-arrow ${isOpen ? 'open' : ''}`}>
          <IconChevronDown size={12} />
        </div>
      </button>

      {/* Hierarchical Dropdown Panel */}
      {isOpen && (
        <div className="workspace-nav-menu-panel" role="menu">
          {navGroups.map((group) => {
            const isCollapsible = !!group.isCollapsible;
            const isExpanded = !isCollapsible || isOutlineExpanded;

            return (
              <div key={group.id} className="nav-group-section">
                {/* Group Header */}
                <div
                  className={`nav-group-header ${isCollapsible ? 'collapsible' : ''}`}
                  onClick={
                    isCollapsible
                      ? (e) => {
                          e.stopPropagation();
                          setIsOutlineExpanded((prev) => !prev);
                        }
                      : undefined
                  }
                  title={isCollapsible ? (isExpanded ? '點擊收合子項目' : '點擊展開子項目') : undefined}
                >
                  <div className="nav-group-header-left">
                    <span className="nav-group-emoji">{group.tag}</span>
                    <span className="nav-group-name">{group.title}</span>
                  </div>
                  {isCollapsible && (
                    <div className="nav-group-expand-hint">
                      <span className="expand-hint-text">{isExpanded ? '收合' : '展開子項目'}</span>
                      <div className={`expand-arrow ${isExpanded ? 'open' : ''}`}>
                        <IconChevronDown size={11} />
                      </div>
                    </div>
                  )}
                </div>

                {/* Group Items / Sub-items */}
                {isExpanded && (
                  <div className={`nav-group-items ${isCollapsible ? 'sub-tree' : ''}`}>
                    {group.items.map((item) => {
                      const active = isItemActive(item);
                      return (
                        <button
                          key={item.id}
                          type="button"
                          className={`nav-menu-item ${active ? 'active' : ''}`}
                          onClick={() => handleItemClick(item)}
                          role="menuitem"
                        >
                          <div className="item-icon-wrapper">{item.icon}</div>
                          <div className="item-text-wrapper">
                            <span className="item-title">{item.label}</span>
                            <span className="item-desc">{item.desc}</span>
                          </div>
                          {active && (
                            <span className="item-check-badge">
                              <IconCheck size={12} />
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
