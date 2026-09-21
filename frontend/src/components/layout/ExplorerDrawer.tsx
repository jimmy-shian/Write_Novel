import React, { useState, useMemo, useEffect } from 'react';
import { Novel, Chapter } from '../../types';
import { Button } from '../common/Button';
import { CustomSelect } from '../common/CustomSelect';
import { CreateNovelModal } from '../novel/CreateNovelModal';
import { DeleteNovelModal } from '../novel/DeleteNovelModal';
import { ResetNovelModal } from '../novel/ResetNovelModal';
import { ExpansionSyncState } from '../../hooks/useExpansionSync';
import {
  IconFileText,
  IconGitBranch,
  IconBookOpen,
  IconUsers,
  IconLayers,
} from '../common/Icons';

interface ExplorerDrawerProps {
  novels: Novel[];
  activeNovelId: string | null;
  chapters: Chapter[];
  activeChapterIndex: number;
  activeView?: string;
  worldviewTab?: 'worldview' | 'characters' | 'plot';
  characters?: any;
  charactersRaw?: string;
  worldbuilding?: string;
  volumes?: any[];
  plot?: any;
  expansionSync?: ExpansionSyncState;
  onSelectWorldviewTab?: (tab: 'worldview' | 'characters' | 'plot') => void;
  onSelectCharacter?: (charName: string) => void;
  onSelectVolume?: (volumeIndex: number) => void;
  onWorldviewAction?: (action: {
    type: 'section' | 'character' | 'volume' | 'tp' | 'seed' | 'chapter_outline';
    id?: string | number;
    action?: 'add' | 'edit' | 'delete' | 'clean' | 'scroll';
    volIndex?: number;
    chIndex?: number;
  }) => void;
  isOpenMobile: boolean;
  onCloseMobile: () => void;
  isCollapsedDesktop?: boolean;
  onToggleCollapseDesktop?: () => void;
  isLoadingNovel?: boolean;
  onSelectNovel: (id: string) => void;
  onSelectChapter: (chapterIndex: number) => void;
  onCreateNovel: (title: string, genre: string, style: string, synopsis?: string) => Promise<any> | any;
  onDeleteNovel: (id: string) => void;
  onResetNovelContent?: (id: string, scopes?: string[]) => Promise<void> | void;
  onCreateChapter: () => void;
}

export const ExplorerDrawer: React.FC<ExplorerDrawerProps> = ({
  novels,
  activeNovelId,
  chapters,
  activeChapterIndex,
  activeView,
  worldviewTab = 'worldview',
  characters,
  charactersRaw,
  worldbuilding,
  volumes = [],
  plot,
  expansionSync,
  onSelectWorldviewTab,
  onSelectCharacter,
  onSelectVolume,
  onWorldviewAction,
  isOpenMobile,
  onCloseMobile,
  isCollapsedDesktop = false,
  onToggleCollapseDesktop,
  isLoadingNovel = false,
  onSelectNovel,
  onSelectChapter,
  onCreateNovel,
  onDeleteNovel,
  onResetNovelContent,
  onCreateChapter,
}) => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isResetModalOpen, setIsResetModalOpen] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [treeOrChaptersOverride, setTreeOrChaptersOverride] = useState<'tree' | 'chapters' | null>(null);

  // Sub-tree toggle expansions (delegated to expansionSync if provided, else fallback to local state)
  const [localExpandWorldview, setLocalExpandWorldview] = useState(true);
  const [localExpandTps, setLocalExpandTps] = useState(true);
  const [localShowAllTps, setLocalShowAllTps] = useState(false);
  const [localExpandSeeds, setLocalExpandSeeds] = useState(false);
  const [localShowAllSeeds, setLocalShowAllSeeds] = useState(false);
  const [localExpandChars, setLocalExpandChars] = useState(true);
  const [localShowAllChars, setLocalShowAllChars] = useState(false);
  const [localExpandVols, setLocalExpandVols] = useState(true);
  const [localExpandedVolumeIndices, setLocalExpandedVolumeIndices] = useState<number[]>([]);

  const expandWorldview = expansionSync ? expansionSync.expandWorldview : localExpandWorldview;
  const setExpandWorldview = expansionSync ? expansionSync.setExpandWorldview : setLocalExpandWorldview;

  const expandTps = expansionSync ? expansionSync.expandTps : localExpandTps;
  const setExpandTps = expansionSync ? expansionSync.setExpandTps : setLocalExpandTps;

  const showAllTps = expansionSync ? expansionSync.showAllTps : localShowAllTps;
  const setShowAllTps = expansionSync ? expansionSync.setShowAllTps : setLocalShowAllTps;

  const expandSeeds = expansionSync ? expansionSync.expandSeeds : localExpandSeeds;
  const setExpandSeeds = expansionSync ? expansionSync.setExpandSeeds : setLocalExpandSeeds;

  const showAllSeeds = expansionSync ? expansionSync.showAllSeeds : localShowAllSeeds;
  const setShowAllSeeds = expansionSync ? expansionSync.setShowAllSeeds : setLocalShowAllSeeds;

  const expandChars = expansionSync ? expansionSync.expandChars : localExpandChars;
  const setExpandChars = expansionSync ? expansionSync.setExpandChars : setLocalExpandChars;

  const showAllChars = expansionSync ? expansionSync.showAllChars : localShowAllChars;
  const setShowAllChars = expansionSync ? expansionSync.setShowAllChars : setLocalShowAllChars;

  const expandVols = expansionSync ? expansionSync.expandVols : localExpandVols;
  const setExpandVols = expansionSync ? expansionSync.setExpandVols : setLocalExpandVols;

  const expandedVolumeIndices = expansionSync ? expansionSync.expandedVolumeIndices : localExpandedVolumeIndices;
  const setExpandedVolumeIndices = expansionSync ? expansionSync.setExpandedVolumeIndices : setLocalExpandedVolumeIndices;

  const tpLimit = showAllTps ? undefined : Math.max(15, expansionSync?.visibleTpCount || 15);
  const seedLimit = showAllSeeds ? undefined : Math.max(15, expansionSync?.visibleSeedCount || 15);
  const charLimit = showAllChars ? undefined : Math.max(12, expansionSync?.visibleCharCount || 12);


  // Floating Context Menu
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    items: { label: string; danger?: boolean; onClick: () => void }[];
  } | null>(null);

  useEffect(() => {
    const handleCloseMenu = () => setContextMenu(null);
    if (contextMenu) {
      document.addEventListener('click', handleCloseMenu);
      document.addEventListener('contextmenu', handleCloseMenu);
    }
    return () => {
      document.removeEventListener('click', handleCloseMenu);
      document.removeEventListener('contextmenu', handleCloseMenu);
    };
  }, [contextMenu]);

  const openContextMenu = (
    e: React.MouseEvent,
    items: { label: string; danger?: boolean; onClick: () => void }[]
  ) => {
    e.preventDefault();
    e.stopPropagation();
    const x = Math.min(e.clientX, window.innerWidth - 170);
    const y = Math.min(e.clientY, window.innerHeight - (items.length * 32 + 20));
    setContextMenu({ x, y, items });
  };

  const activeNovel = novels.find((n) => n.id === activeNovelId);

  // Parse characters list for the dynamic tree
  const parsedCharList = useMemo(() => {
    if (Array.isArray(characters)) return characters;
    if (characters && Array.isArray(characters.characters)) return characters.characters;
    if (charactersRaw) {
      try {
        const data = JSON.parse(charactersRaw);
        if (Array.isArray(data)) return data;
        if (data && Array.isArray(data.characters)) return data.characters;
        if (typeof data === 'object' && data !== null) {
          return Object.values(data).filter((i: any) => i && i.name);
        }
      } catch {
        // raw text
      }
    }
    return [];
  }, [characters, charactersRaw]);

  // Parse worldbuilding turning points and seeds
  const { turningPointsList, seedsList } = useMemo(() => {
    if (!worldbuilding) return { turningPointsList: [], seedsList: [] };
    try {
      const data = JSON.parse(worldbuilding);
      return {
        turningPointsList: Array.isArray(data?.key_turning_points) ? data.key_turning_points : [],
        seedsList: Array.isArray(data?.foreshadowing_seeds) ? data.foreshadowing_seeds : [],
      };
    } catch {
      return { turningPointsList: [], seedsList: [] };
    }
  }, [worldbuilding]);

  // Determine whether to show the dynamic outline tree or chapter list
  const showDynamicTree =
    treeOrChaptersOverride !== null
      ? treeOrChaptersOverride === 'tree'
      : activeView === 'worldview';

  const handleDeleteConfirm = async () => {
    if (!activeNovel) return;
    setIsDeleting(true);
    try {
      await onDeleteNovel(activeNovel.id);
      setIsDeleteModalOpen(false);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleConfirmReset = async (scopes: string[]) => {
    if (!activeNovel) return;
    setIsResetting(true);
    try {
      if (onResetNovelContent) {
        await onResetNovelContent(activeNovel.id, scopes);
      }
      setIsResetModalOpen(false);
    } finally {
      setIsResetting(false);
    }
  };

  const toggleVolumeChaptersExpand = (vIdx: number, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (expansionSync) {
      expansionSync.toggleVolumeChaptersExpand(vIdx);
    } else {
      setLocalExpandedVolumeIndices((prev) =>
        prev.includes(vIdx) ? prev.filter((i) => i !== vIdx) : [...prev, vIdx]
      );
    }
  };

  // Memoize full chapter list merged from volumes (chapters_outline), plot outlines, and written chapters
  const displayChapters = useMemo(() => {
    const chapterMap = new Map<number, {
      chapter_index: number;
      title?: string;
      isGenerated: boolean;
      word_count: number;
      content?: string;
      summary?: string;
      volume_index?: number;
      volume_title?: string;
    }>();

    // 1. Ingest planned outline chapters from volumes
    if (Array.isArray(volumes)) {
      volumes.forEach((vol: any, vIdx: number) => {
        const volumeIndex = vol.volume_index ?? vIdx + 1;
        const volumeTitle = vol.title || `第 ${volumeIndex} 卷`;
        const outlines = Array.isArray(vol.chapters_outline)
          ? vol.chapters_outline
          : Array.isArray(vol.chapters)
          ? vol.chapters
          : [];
        outlines.forEach((ch: any, cIdx: number) => {
          const chNum = Number(ch.chapter_index ?? cIdx + 1);
          if (isNaN(chNum) || chNum <= 0) return;
          const rawTitle = ch.chapter_title || ch.title || '';
          const cleanTitle = rawTitle.replace(/^第\s*\d+\s*章([：:\s]*)/, '').trim() || rawTitle;
          chapterMap.set(chNum, {
            chapter_index: chNum,
            title: cleanTitle || undefined,
            isGenerated: false,
            word_count: 0,
            summary: ch.chapter_summary || ch.summary || '',
            volume_index: volumeIndex,
            volume_title: volumeTitle,
          });
        });
      });
    }

    // 2. Ingest from plot if available
    if (plot && Array.isArray(plot.chapters)) {
      plot.chapters.forEach((ch: any, cIdx: number) => {
        const chNum = Number(ch.chapter_index ?? cIdx + 1);
        if (isNaN(chNum) || chNum <= 0) return;
        if (!chapterMap.has(chNum)) {
          const rawTitle = ch.chapter_title || ch.title || '';
          const cleanTitle = rawTitle.replace(/^第\s*\d+\s*章([：:\s]*)/, '').trim() || rawTitle;
          chapterMap.set(chNum, {
            chapter_index: chNum,
            title: cleanTitle || undefined,
            isGenerated: false,
            word_count: 0,
            summary: ch.chapter_summary || ch.summary || '',
            volume_index: ch.volume_index,
            volume_title: ch.volume_title,
          });
        }
      });
    }

    // 3. Overlay written chapters from chapters table
    if (Array.isArray(chapters)) {
      chapters.forEach((ch) => {
        const chNum = Number(ch.chapter_index);
        if (isNaN(chNum) || chNum <= 0) return;
        const hasContent = Boolean(ch.content && ch.content.trim().length > 0);
        const words = hasContent ? ch.content.length : 0;
        const existing = chapterMap.get(chNum);
        if (existing) {
          existing.isGenerated = hasContent;
          existing.word_count = words;
          existing.content = ch.content;
          if (ch.title && !existing.title) {
            existing.title = ch.title;
          }
        } else {
          chapterMap.set(chNum, {
            chapter_index: chNum,
            title: ch.title,
            isGenerated: hasContent,
            word_count: words,
            content: ch.content,
          });
        }
      });
    }

    return Array.from(chapterMap.values()).sort((a, b) => a.chapter_index - b.chapter_index);
  }, [volumes, plot, chapters]);

  // 桌面端收合態：只剩一條可點展開的窄條（與右側導演室對稱）
  if (isCollapsedDesktop) {
    return (
      <aside className={`explorer-drawer desktop-collapsed ${isOpenMobile ? 'mobile-open' : ''}`}>
        <button
          type="button"
          className="explorer-expand-trigger-btn"
          onClick={onToggleCollapseDesktop}
          title="展開"
          aria-label="展開"
        >
          <span className="explorer-vertical-label">[作品] 導航目錄</span>
        </button>
      </aside>
    );
  }

  return (
    <>
      <aside className={`explorer-drawer ${isOpenMobile ? 'mobile-open' : ''}`}>
        <div className="explorer-header">
          {onToggleCollapseDesktop ? (
            <button
              type="button"
              className="explorer-title-wrapper explorer-title-toggle"
              onClick={onToggleCollapseDesktop}
              title="收合"
              aria-label="收合"
            >
              <span className="explorer-tag-badge">[作品]</span>
              <span className="explorer-title">導航目錄</span>
            </button>
          ) : (
            <div className="explorer-title-wrapper">
              <span className="explorer-tag-badge">[作品]</span>
              <span className="explorer-title">導航目錄</span>
            </div>
          )}
          <div className="explorer-actions">
            <Button
              size="xs"
              variant="secondary"
              onClick={() => setIsCreateModalOpen(true)}
              title="建立新小說"
            >
              + 新建
            </Button>
            {activeNovel && (
              <Button
                size="xs"
                variant="ghost"
                className="text-danger hover:bg-danger-subtle"
                onClick={() => setIsResetModalOpen(true)}
                title="清空當前小說的生成內容，回到初始設定狀態"
              >
                清空生成
              </Button>
            )}
            {isOpenMobile && (
              <Button
                size="xs"
                variant="ghost"
                onClick={onCloseMobile}
                title="關閉面板"
              >
                關閉
              </Button>
            )}
          </div>
        </div>

        <div className="explorer-content">
          {/* Novel Selector */}
          <div className="novel-selector-section">
            <CustomSelect
              value={activeNovelId || ''}
              options={novels.map((novel) => ({
                value: novel.id,
                label: novel.title,
                subLabel: novel.genre,
              }))}
              placeholder={novels.length === 0 ? '(尚未建立小說)' : '請選擇作品...'}
              onChange={(id) => onSelectNovel(id)}
              className="novel-select-custom"
              loading={isLoadingNovel}
            />
            {isLoadingNovel && (
              <div className="explorer-loading-indicator">
                <span className="select-spinner" />
                <span>切換載入中...</span>
              </div>
            )}
          </div>

          {/* Section Header with Dynamic Toggle */}
          <div className="explorer-section-title-wrapper">
            <span className="explorer-section-title">
              {showDynamicTree ? '全書架構樹' : '章節目錄'}
            </span>
            <div className="flex items-center gap-1">
              <Button
                size="xs"
                variant="ghost"
                onClick={() => setTreeOrChaptersOverride(showDynamicTree ? 'chapters' : 'tree')}
                title={showDynamicTree ? '切換為章節目錄' : '切換為全書架構樹'}
                className="flex items-center gap-1"
              >
                {showDynamicTree ? (
                  <>
                    <IconFileText size={13} />
                    <span>章節目錄</span>
                  </>
                ) : (
                  <>
                    <IconGitBranch size={13} />
                    <span>架構樹</span>
                  </>
                )}
              </Button>
              {!showDynamicTree && (
                <Button
                  size="xs"
                  variant="ghost"
                  onClick={onCreateChapter}
                  title="新增章節"
                >
                  + 新章
                </Button>
              )}
            </div>
          </div>

          {/* Body: Either Dynamic Worldview Outline Tree OR Chapter List */}
          {showDynamicTree ? (
            <div className={`chapter-tree-list ${isLoadingNovel ? 'editor-content-fade is-loading' : 'editor-content-fade'}`}>
              {/* 1. Worldbuilding Node with Sub-branches */}
              <div>
                <div
                  className={`tree-item ${worldviewTab === 'worldview' ? 'active' : ''} ${expandWorldview ? 'open' : ''}`}
                  onClick={() => {
                    onSelectWorldviewTab?.('worldview');
                    setExpandWorldview((prev) => !prev);
                  }}
                  onContextMenu={(e) =>
                    openContextMenu(e, [
                      {
                        label: '+ 新增轉折點',
                        onClick: () => onWorldviewAction?.({ type: 'tp', action: 'add' }),
                      },
                      {
                        label: '+ 新增伏筆種子',
                        onClick: () => onWorldviewAction?.({ type: 'seed', action: 'add' }),
                      },
                      {
                        label: '清除空白轉折與伏筆',
                        danger: true,
                        onClick: () => onWorldviewAction?.({ type: 'section', id: 'clean-empty' }),
                      },
                    ])
                  }
                  role="button"
                  tabIndex={0}
                >
                  <div className="tree-item-title">
                    <span className="tree-item-badge">
                      <IconBookOpen size={13} />
                    </span>
                    <span>世界觀構建</span>
                  </div>
                  <span className={`tree-arrow ${expandWorldview ? 'open' : ''}`}>
                    ▾
                  </span>
                </div>

                <div className={`tree-accordion-collapsible ${expandWorldview ? 'open' : ''}`}>
                  <div className="tree-accordion-inner">
                    <div className="tree-sub-list">
                      {/* Pipeline Prompt */}
                      <div
                        className="tree-sub-item cursor-pointer"
                        onClick={() => {
                          onSelectWorldviewTab?.('worldview');
                          onWorldviewAction?.({ type: 'section', id: 'wb-card-prompt' });
                          if (isOpenMobile) onCloseMobile();
                        }}
                      >
                        <span className="truncate">故事簡述 / 大綱靈感</span>
                      </div>

                      {/* Theme & Conflict */}
                      <div
                        className="tree-sub-item cursor-pointer"
                        onClick={() => {
                          onSelectWorldviewTab?.('worldview');
                          onWorldviewAction?.({ type: 'section', id: 'wb-card-theme' });
                          if (isOpenMobile) onCloseMobile();
                        }}
                      >
                        <span>核心主題與主要衝突</span>
                      </div>

                      {/* Rules & Power System */}
                      <div
                        className="tree-sub-item cursor-pointer"
                        onClick={() => {
                          onSelectWorldviewTab?.('worldview');
                          onWorldviewAction?.({ type: 'section', id: 'wb-card-rules' });
                          if (isOpenMobile) onCloseMobile();
                        }}
                      >
                        <span>世界觀法則與修煉體系</span>
                      </div>

                      {/* Macro Outline */}
                      <div
                        className="tree-sub-item cursor-pointer"
                        onClick={() => {
                          onSelectWorldviewTab?.('worldview');
                          onWorldviewAction?.({ type: 'section', id: 'wb-card-macro' });
                          if (isOpenMobile) onCloseMobile();
                        }}
                      >
                        <span>全書宏觀主線大綱</span>
                      </div>

                      {/* Key Turning Points Branch */}
                      <div className="tree-sub-group">
                        <div
                          className={`tree-sub-header ${expandTps ? 'open' : ''}`}
                          onClick={() => setExpandTps((prev) => !prev)}
                          onContextMenu={(e) =>
                            openContextMenu(e, [
                              {
                                label: '+ 新增轉折點',
                                onClick: () => onWorldviewAction?.({ type: 'tp', action: 'add' }),
                              },
                              {
                                label: '清除空白轉折點',
                                danger: true,
                                onClick: () => onWorldviewAction?.({ type: 'tp', action: 'clean' }),
                              },
                            ])
                          }
                        >
                          <div className="tree-sub-header-left">
                            <span className={`tree-arrow ${expandTps ? 'open' : ''}`}>▾</span>
                            <span>重大轉折點 ({turningPointsList.length})</span>
                          </div>
                          <button
                            type="button"
                            className="tree-action-btn"
                            title="新增轉折點 (+)"
                            onClick={(e) => {
                              e.stopPropagation();
                              onWorldviewAction?.({ type: 'tp', action: 'add' });
                              if (isOpenMobile) onCloseMobile();
                            }}
                          >
                            +
                          </button>
                        </div>
                        <div className={`tree-accordion-collapsible ${expandTps && turningPointsList.length > 0 ? 'open' : ''}`}>
                          <div className="tree-accordion-inner">
                            <div className="tree-sub-nested-list" style={{ paddingLeft: '14px' }}>
                              {(showAllTps ? turningPointsList : turningPointsList.slice(0, tpLimit)).map((tp: any, tpIdx: number) => {
                                const name = tp.turning_point_name || tp.name || `轉折點 #${tpIdx + 1}`;
                                return (
                                  <div
                                    key={tpIdx}
                                    className="tree-sub-item cursor-pointer"
                                    onClick={() => {
                                      onSelectWorldviewTab?.('worldview');
                                      onWorldviewAction?.({ type: 'tp', id: tpIdx, action: 'scroll' });
                                      if (isOpenMobile) onCloseMobile();
                                    }}
                                    onContextMenu={(e) =>
                                      openContextMenu(e, [
                                        {
                                          label: '定位轉折卡片',
                                          onClick: () => onWorldviewAction?.({ type: 'tp', id: tpIdx, action: 'scroll' }),
                                        },
                                        {
                                          label: '編輯此轉折點',
                                          onClick: () => onWorldviewAction?.({ type: 'tp', id: tpIdx, action: 'edit' }),
                                        },
                                        {
                                          label: '刪除此轉折點',
                                          danger: true,
                                          onClick: () => onWorldviewAction?.({ type: 'tp', id: tpIdx, action: 'delete' }),
                                        },
                                      ])
                                    }
                                  >
                                    <span className="truncate">
                                      ⚡ <span className="text-muted mr-1 font-mono">#{tpIdx + 1}</span>{name}
                                    </span>
                                  </div>
                                );
                              })}
                              {turningPointsList.length > (tpLimit || 15) && !showAllTps && (
                                <div
                                  className="tree-sub-item tree-expand-toggle text-accent cursor-pointer"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (expansionSync) {
                                      expansionSync.toggleShowAllTps(turningPointsList.length);
                                    } else {
                                      setShowAllTps(true);
                                    }
                                  }}
                                >
                                  ▾ 展開全部轉折點 ({turningPointsList.length} 處)
                                </div>
                              )}
                              {showAllTps && turningPointsList.length > 15 && (
                                <div
                                  className="tree-sub-item tree-expand-toggle text-accent cursor-pointer"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (expansionSync) {
                                      expansionSync.toggleShowAllTps();
                                    } else {
                                      setShowAllTps(false);
                                    }
                                  }}
                                >
                                  ▴ 收合轉折點清單
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Foreshadowing Seeds Branch */}
                      <div className="tree-sub-group">
                        <div
                          className={`tree-sub-header ${expandSeeds ? 'open' : ''}`}
                          onClick={() => setExpandSeeds((prev) => !prev)}
                          onContextMenu={(e) =>
                            openContextMenu(e, [
                              {
                                label: '+ 新增伏筆種子',
                                onClick: () => onWorldviewAction?.({ type: 'seed', action: 'add' }),
                              },
                              {
                                label: '清除空白伏筆種子',
                                danger: true,
                                onClick: () => onWorldviewAction?.({ type: 'seed', action: 'clean' }),
                              },
                            ])
                          }
                        >
                          <div className="tree-sub-header-left">
                            <span className={`tree-arrow ${expandSeeds ? 'open' : ''}`}>▾</span>
                            <span>伏筆種子庫 ({seedsList.length})</span>
                          </div>
                          <button
                            type="button"
                            className="tree-action-btn"
                            title="新增伏筆種子 (+)"
                            onClick={(e) => {
                              e.stopPropagation();
                              onWorldviewAction?.({ type: 'seed', action: 'add' });
                              if (isOpenMobile) onCloseMobile();
                            }}
                          >
                            +
                          </button>
                        </div>
                        <div className={`tree-accordion-collapsible ${expandSeeds && seedsList.length > 0 ? 'open' : ''}`}>
                          <div className="tree-accordion-inner">
                            <div className="tree-sub-nested-list" style={{ paddingLeft: '14px' }}>
                              {(showAllSeeds ? seedsList : seedsList.slice(0, seedLimit)).map((seed: any, sIdx: number) => {
                                const name = seed.name || `伏筆 #${sIdx + 1}`;
                                return (
                                  <div
                                    key={sIdx}
                                    className="tree-sub-item cursor-pointer"
                                    onClick={() => {
                                      onSelectWorldviewTab?.('worldview');
                                      onWorldviewAction?.({ type: 'seed', id: sIdx, action: 'scroll' });
                                      if (isOpenMobile) onCloseMobile();
                                    }}
                                    onContextMenu={(e) =>
                                      openContextMenu(e, [
                                        {
                                          label: '定位伏筆卡片',
                                          onClick: () => onWorldviewAction?.({ type: 'seed', id: sIdx, action: 'scroll' }),
                                        },
                                        {
                                          label: '編輯此伏筆',
                                          onClick: () => onWorldviewAction?.({ type: 'seed', id: sIdx, action: 'edit' }),
                                        },
                                        {
                                          label: '刪除此伏筆',
                                          danger: true,
                                          onClick: () => onWorldviewAction?.({ type: 'seed', id: sIdx, action: 'delete' }),
                                        },
                                      ])
                                    }
                                  >
                                    <span className="truncate">
                                      🌱 <span className="text-muted mr-1 font-mono">#{sIdx + 1}</span>{name}
                                    </span>
                                  </div>
                                );
                              })}
                              {seedsList.length > (seedLimit || 15) && !showAllSeeds && (
                                <div
                                  className="tree-sub-item tree-expand-toggle text-accent cursor-pointer"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (expansionSync) {
                                      expansionSync.toggleShowAllSeeds(seedsList.length);
                                    } else {
                                      setShowAllSeeds(true);
                                    }
                                  }}
                                >
                                  ▾ 展開全部伏筆 ({seedsList.length} 個)
                                </div>
                              )}
                              {showAllSeeds && seedsList.length > 15 && (
                                <div
                                  className="tree-sub-item tree-expand-toggle text-accent cursor-pointer"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (expansionSync) {
                                      expansionSync.toggleShowAllSeeds();
                                    } else {
                                      setShowAllSeeds(false);
                                    }
                                  }}
                                >
                                  ▴ 收合伏筆種子清單
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* 2. Character Bible Node with + button and Collapsible Children */}
              <div>
                <div
                  className={`tree-item ${worldviewTab === 'characters' ? 'active' : ''}`}
                  onClick={() => {
                    onSelectWorldviewTab?.('characters');
                    setExpandChars((prev) => !prev);
                  }}
                  onContextMenu={(e) =>
                    openContextMenu(e, [
                      {
                        label: '+ 新增角色',
                        onClick: () => onWorldviewAction?.({ type: 'character', action: 'add' }),
                      },
                      {
                        label: '清除空白角色',
                        danger: true,
                        onClick: () => onWorldviewAction?.({ type: 'character', action: 'clean' }),
                      },
                    ])
                  }
                  role="button"
                  tabIndex={0}
                >
                  <div className="tree-item-title">
                    <span className="tree-item-badge">
                      <IconUsers size={13} />
                    </span>
                    <span>角色聖經</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="tree-item-meta">
                      {parsedCharList.length > 0 ? `${parsedCharList.length} 人` : ''}
                    </span>
                    <span className={`tree-arrow ${expandChars ? 'open' : ''}`}>▾</span>
                    <button
                      type="button"
                      className="tree-action-btn"
                      title="新增角色 (+)"
                      onClick={(e) => {
                        e.stopPropagation();
                        onWorldviewAction?.({ type: 'character', action: 'add' });
                        if (isOpenMobile) onCloseMobile();
                      }}
                    >
                      +
                    </button>
                  </div>
                </div>

                <div className={`tree-accordion-collapsible ${expandChars && parsedCharList.length > 0 ? 'open' : ''}`}>
                  <div className="tree-accordion-inner">
                    <div className="tree-sub-list">
                      {(showAllChars ? parsedCharList : parsedCharList.slice(0, charLimit)).map((char: any, idx: number) => (
                        <div
                          key={char.name || idx}
                          className="tree-sub-item cursor-pointer"
                          onClick={() => {
                            onSelectWorldviewTab?.('characters');
                            onSelectCharacter?.(char.name);
                            if (isOpenMobile) onCloseMobile();
                          }}
                          onContextMenu={(e) =>
                            openContextMenu(e, [
                              {
                                label: `定位《${char.name}》`,
                                onClick: () => onSelectCharacter?.(char.name),
                              },
                              {
                                label: '編輯角色',
                                onClick: () => onWorldviewAction?.({ type: 'character', id: char.name, action: 'edit' }),
                              },
                              {
                                label: '刪除角色',
                                danger: true,
                                onClick: () => onWorldviewAction?.({ type: 'character', id: char.name, action: 'delete' }),
                              },
                            ])
                          }
                        >
                          <span className="truncate">{char.name}</span>
                          {char.role && <span className="text-xs text-muted">[{char.role}]</span>}
                        </div>
                      ))}
                      {parsedCharList.length > (charLimit || 12) && !showAllChars && (
                        <div
                          className="tree-sub-item tree-expand-toggle text-accent cursor-pointer"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (expansionSync) {
                              expansionSync.toggleShowAllChars(parsedCharList.length);
                            } else {
                              setShowAllChars(true);
                            }
                          }}
                        >
                          ▾ 展開全部角色 ({parsedCharList.length} 位)
                        </div>
                      )}
                      {showAllChars && parsedCharList.length > 12 && (
                        <div
                          className="tree-sub-item tree-expand-toggle text-accent cursor-pointer"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (expansionSync) {
                              expansionSync.toggleShowAllChars();
                            } else {
                              setShowAllChars(false);
                            }
                          }}
                        >
                          ▴ 收合角色清單
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* 3. Volumes Skeleton Node with + button and Collapsible Chapter Outlines */}
              <div>
                <div
                  className={`tree-item ${worldviewTab === 'plot' ? 'active' : ''}`}
                  onClick={() => {
                    onSelectWorldviewTab?.('plot');
                    setExpandVols((prev) => !prev);
                  }}
                  onContextMenu={(e) =>
                    openContextMenu(e, [
                      {
                        label: '+ 新增分卷',
                        onClick: () => onWorldviewAction?.({ type: 'volume', action: 'add' }),
                      },
                      {
                        label: '清除空白分卷',
                        danger: true,
                        onClick: () => onWorldviewAction?.({ type: 'volume', action: 'clean' }),
                      },
                    ])
                  }
                  role="button"
                  tabIndex={0}
                >
                  <div className="tree-item-title">
                    <span className="tree-item-badge">
                      <IconLayers size={13} />
                    </span>
                    <span>分卷骨架與大綱</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="tree-item-meta">
                      {volumes.length > 0 ? `${volumes.length} 卷` : ''}
                    </span>
                    <span className={`tree-arrow ${expandVols ? 'open' : ''}`}>▾</span>
                    <button
                      type="button"
                      className="tree-action-btn"
                      title="新增分卷 (+)"
                      onClick={(e) => {
                        e.stopPropagation();
                        onWorldviewAction?.({ type: 'volume', action: 'add' });
                        if (isOpenMobile) onCloseMobile();
                      }}
                    >
                      +
                    </button>
                  </div>
                </div>

                <div className={`tree-accordion-collapsible ${expandVols && volumes.length > 0 ? 'open' : ''}`}>
                  <div className="tree-accordion-inner">
                    <div className="tree-sub-list">
                      {volumes.map((vol: any, idx: number) => {
                        const vIdx = vol.volume_index ?? idx + 1;
                        const hasChapters = Array.isArray(vol.chapters_outline) && vol.chapters_outline.length > 0;
                        const isExpanded = expandedVolumeIndices.includes(vIdx);

                        return (
                          <div key={vol.id || idx} className="tree-volume-branch">
                            <div
                              className="tree-sub-item cursor-pointer flex items-center justify-between"
                              onClick={() => {
                                onSelectWorldviewTab?.('plot');
                                onSelectVolume?.(vIdx);
                                if (hasChapters) {
                                  toggleVolumeChaptersExpand(vIdx);
                                }
                                if (isOpenMobile) onCloseMobile();
                              }}
                              onContextMenu={(e) =>
                                openContextMenu(e, [
                                  {
                                    label: `+ 為第 ${vIdx} 卷新增章綱`,
                                    onClick: () => onWorldviewAction?.({ type: 'chapter_outline', action: 'add', volIndex: vIdx }),
                                  },
                                  {
                                    label: `定位第 ${vIdx} 卷卡片`,
                                    onClick: () => onSelectVolume?.(vIdx),
                                  },
                                  {
                                    label: '編輯分卷',
                                    onClick: () => onWorldviewAction?.({ type: 'volume', id: vIdx, action: 'edit' }),
                                  },
                                  {
                                    label: '刪除此卷',
                                    danger: true,
                                    onClick: () => onWorldviewAction?.({ type: 'volume', id: vIdx, action: 'delete' }),
                                  },
                                ])
                              }
                            >
                              <div className="flex items-center gap-1.5 truncate">
                                {hasChapters && (
                                  <span className={`tree-arrow-side ${isExpanded ? 'open' : ''}`}>
                                    ▸
                                  </span>
                                )}
                                <span className="truncate">第 {vIdx} 卷: {vol.title || '篇卷'}</span>
                              </div>
                              <button
                                type="button"
                                className="tree-action-btn"
                                title={`為第 ${vIdx} 卷新增章綱 (+)`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onWorldviewAction?.({ type: 'chapter_outline', action: 'add', volIndex: vIdx });
                                  if (isOpenMobile) onCloseMobile();
                                }}
                              >
                                +
                              </button>
                            </div>

                            {/* Nested Chapter Outline list under volume */}
                            {hasChapters && (
                              <div className={`tree-accordion-collapsible ${isExpanded ? 'open' : ''}`}>
                                <div className="tree-accordion-inner">
                                  <div className="tree-sub-nested-list" style={{ paddingLeft: '16px' }}>
                                    {vol.chapters_outline.map((ch: any, cIdx: number) => {
                                      const chNum = ch.chapter_index ?? cIdx + 1;
                                      const rawTitle = ch.chapter_title || `第 ${chNum} 章`;
                                      const cleanTitle = rawTitle.replace(/^第\s*\d+\s*章([：:\s]*)/, '').trim() || rawTitle;
                                      return (
                                        <div
                                          key={chNum}
                                          className="tree-sub-item cursor-pointer text-xs"
                                          onClick={() => {
                                            onSelectWorldviewTab?.('plot');
                                            onWorldviewAction?.({ type: 'chapter_outline', id: chNum, volIndex: vIdx, chIndex: chNum, action: 'scroll' });
                                            if (isOpenMobile) onCloseMobile();
                                          }}
                                          onContextMenu={(e) =>
                                            openContextMenu(e, [
                                              {
                                                label: `定位第 ${chNum} 章細綱`,
                                                onClick: () => onWorldviewAction?.({ type: 'chapter_outline', id: chNum, volIndex: vIdx, chIndex: chNum, action: 'scroll' }),
                                              },
                                              {
                                                label: '編輯章綱',
                                                onClick: () => onWorldviewAction?.({ type: 'chapter_outline', id: chNum, volIndex: vIdx, chIndex: chNum, action: 'edit' }),
                                              },
                                              {
                                                label: '刪除此章綱',
                                                danger: true,
                                                onClick: () => onWorldviewAction?.({ type: 'chapter_outline', id: chNum, volIndex: vIdx, chIndex: chNum, action: 'delete' }),
                                              },
                                            ])
                                          }
                                        >
                                          <span className="truncate">第 {chNum} 章: {cleanTitle}</span>
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className={`chapter-tree-list ${isLoadingNovel ? 'editor-content-fade is-loading' : 'editor-content-fade'}`}>
              {displayChapters.length === 0 ? (
                <div className="empty-tree-hint">目前無章節與大綱，點擊上方按鈕建立</div>
              ) : (
                displayChapters.map((ch) => {
                  const isActive = ch.chapter_index === activeChapterIndex;
                  const hasCustomTitle = Boolean(ch.title && ch.title !== `第 ${ch.chapter_index} 章`);
                  return (
                    <div
                      key={ch.chapter_index}
                      className={`tree-item ${ch.isGenerated ? '' : 'tree-item-unwritten'} ${isActive ? 'active' : ''}`}
                      onClick={() => {
                        onSelectChapter(ch.chapter_index);
                        if (isOpenMobile) onCloseMobile();
                      }}
                      role="button"
                      tabIndex={0}
                      title={
                        ch.summary
                          ? `第 ${ch.chapter_index} 章細綱: ${ch.summary}`
                          : hasCustomTitle
                          ? `第 ${ch.chapter_index} 章: ${ch.title} ${ch.isGenerated ? `(${ch.word_count} 字)` : '(待生成)'}`
                          : `第 ${ch.chapter_index} 章 ${ch.isGenerated ? `(${ch.word_count} 字)` : '(待生成)'}`
                      }
                    >
                      <div className="tree-item-title truncate">
                        <span className={`tree-item-badge ${ch.isGenerated ? '' : 'tree-item-badge-dashed'}`}>
                          <IconFileText size={13} />
                        </span>
                        <span className="truncate">
                          第 {ch.chapter_index} 章{hasCustomTitle ? `: ${ch.title}` : ''}
                        </span>
                      </div>
                      {ch.isGenerated ? (
                        <span className="tree-item-meta">{ch.word_count} 字</span>
                      ) : (
                        <span className="tree-item-meta unwritten-badge">待生成</span>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}
          {/* Delete Novel Button at bottom of explorer */}
          {activeNovel && (
            <div className="explorer-footer">
              <Button
                size="xs"
                variant="ghost"
                className="text-muted delete-novel-btn"
                onClick={() => setIsDeleteModalOpen(true)}
                data-tooltip="永久刪除整部作品（需二次確認）"
              >
                刪除本作品
              </Button>
            </div>
          )}
        </div>

        {/* Floating Context Menu */}
        {contextMenu && (
          <div
            className="tree-context-menu"
            style={{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }}
          >
            {contextMenu.items.map((item, idx) => (
              <button
                key={idx}
                type="button"
                className={`tree-context-item ${item.danger ? 'danger' : ''}`}
                onClick={() => {
                  item.onClick();
                  setContextMenu(null);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
      </aside>

      {/* Create Novel Dedicated Modal Card */}
      <CreateNovelModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSubmit={async (title, genre, style, synopsis) => {
          await onCreateNovel(title, genre, style, synopsis);
        }}
      />

      {/* Delete Novel Double-Check Modal (same modular interface as Reset) */}
      {activeNovel && (
        <DeleteNovelModal
          isOpen={isDeleteModalOpen}
          onClose={() => setIsDeleteModalOpen(false)}
          onConfirm={handleDeleteConfirm}
          novelTitle={activeNovel.title}
          isLoading={isDeleting}
        />
      )}

      {/* Reset Novel Content Double-Check Modal */}
      {activeNovel && (
        <ResetNovelModal
          isOpen={isResetModalOpen}
          onClose={() => setIsResetModalOpen(false)}
          onConfirm={handleConfirmReset}
          novelTitle={activeNovel.title}
          isLoading={isResetting}
        />
      )}
    </>
  );
};

