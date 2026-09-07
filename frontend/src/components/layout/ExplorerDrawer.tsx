import React, { useState, useMemo, useEffect } from 'react';
import { Novel, Chapter } from '../../types';
import { Button } from '../common/Button';
import { CustomSelect } from '../common/CustomSelect';
import { CreateNovelModal } from '../novel/CreateNovelModal';
import { ConfirmModal } from '../common/ConfirmModal';
import { ResetNovelModal } from '../novel/ResetNovelModal';
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
  onSelectNovel: (id: string) => void;
  onSelectChapter: (chapterIndex: number) => void;
  onCreateNovel: (title: string, genre: string, style: string, synopsis?: string) => Promise<any> | any;
  onDeleteNovel: (id: string) => void;
  onResetNovelContent?: (id: string) => Promise<void> | void;
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
  onSelectWorldviewTab,
  onSelectCharacter,
  onSelectVolume,
  onWorldviewAction,
  isOpenMobile,
  onCloseMobile,
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

  // Sub-tree toggle expansions
  const [expandWorldview, setExpandWorldview] = useState(true);
  const [expandTps, setExpandTps] = useState(false);
  const [showAllTps, setShowAllTps] = useState(false);
  const [expandSeeds, setExpandSeeds] = useState(false);
  const [showAllSeeds, setShowAllSeeds] = useState(false);
  const [expandChars, setExpandChars] = useState(true);
  const [showAllChars, setShowAllChars] = useState(false);
  const [expandVols, setExpandVols] = useState(true);
  const [expandedVolumeIndices, setExpandedVolumeIndices] = useState<number[]>([]);

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

  const handleConfirmReset = async () => {
    if (!activeNovel) return;
    setIsResetting(true);
    try {
      if (onResetNovelContent) {
        await onResetNovelContent(activeNovel.id);
      }
      setIsResetModalOpen(false);
    } finally {
      setIsResetting(false);
    }
  };

  const toggleVolumeChaptersExpand = (vIdx: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedVolumeIndices((prev) =>
      prev.includes(vIdx) ? prev.filter((i) => i !== vIdx) : [...prev, vIdx]
    );
  };

  return (
    <>
      <aside className={`explorer-drawer ${isOpenMobile ? 'mobile-open' : ''}`}>
        <div className="explorer-header">
          <div className="explorer-title-wrapper">
            <span className="explorer-tag-badge">[作品]</span>
            <span className="explorer-title">導航目錄</span>
          </div>
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
            />
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
            <div className="chapter-tree-list">
              {/* 1. Worldbuilding Node with Sub-branches */}
              <div>
                <div
                  className={`tree-item ${worldviewTab === 'worldview' ? 'active' : ''}`}
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
                  <span className="tree-item-meta">
                    {expandWorldview ? '▾' : '▸'}
                  </span>
                </div>

                {expandWorldview && (
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
                      {/* Turning Points Sub-branch */}
                      <div
                        className="tree-sub-header"
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
                          <span>{expandTps ? '▾' : '▸'} 重大轉折點 ({turningPointsList.length})</span>
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
                      {expandTps && turningPointsList.length > 0 && (
                        <div className="tree-sub-nested-list" style={{ paddingLeft: '14px' }}>
                          {(showAllTps ? turningPointsList : turningPointsList.slice(0, 15)).map((tp: any, tpIdx: number) => {
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
                          {turningPointsList.length > 15 && (
                            <div
                              className="tree-sub-item tree-expand-toggle text-accent cursor-pointer"
                              onClick={(e) => {
                                e.stopPropagation();
                                setShowAllTps((prev) => !prev);
                              }}
                            >
                              {showAllTps
                                ? '▴ 收合轉折點清單'
                                : `▾ 展開全部轉折點 (${turningPointsList.length} 處)`}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Foreshadowing Seeds Branch */}
                    <div className="tree-sub-group">
                      <div
                        className="tree-sub-header"
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
                          <span>{expandSeeds ? '▾' : '▸'} 伏筆種子庫 ({seedsList.length})</span>
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
                      {expandSeeds && seedsList.length > 0 && (
                        <div className="tree-sub-nested-list" style={{ paddingLeft: '14px' }}>
                          {(showAllSeeds ? seedsList : seedsList.slice(0, 15)).map((seed: any, sIdx: number) => {
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
                          {seedsList.length > 15 && (
                            <div
                              className="tree-sub-item tree-expand-toggle text-accent cursor-pointer"
                              onClick={(e) => {
                                e.stopPropagation();
                                setShowAllSeeds((prev) => !prev);
                              }}
                            >
                              {showAllSeeds
                                ? '▴ 收合伏筆種子清單'
                                : `▾ 展開全部伏筆 (${seedsList.length} 個)`}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
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
                      {parsedCharList.length > 0 ? `${parsedCharList.length} 人` : ''} {expandChars ? '▾' : '▸'}
                    </span>
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

                {expandChars && parsedCharList.length > 0 && (
                  <div className="tree-sub-list">
                    {(showAllChars ? parsedCharList : parsedCharList.slice(0, 12)).map((char: any, idx: number) => (
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
                    {parsedCharList.length > 12 && (
                      <div
                        className="tree-sub-item tree-expand-toggle text-accent cursor-pointer"
                        onClick={(e) => {
                          e.stopPropagation();
                          setShowAllChars((prev) => !prev);
                        }}
                      >
                        {showAllChars
                          ? '▴ 收合角色清單'
                          : `▾ 展開全部角色 (${parsedCharList.length} 位)`}
                      </div>
                    )}
                  </div>
                )}
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
                      {volumes.length > 0 ? `${volumes.length} 卷` : ''} {expandVols ? '▾' : '▸'}
                    </span>
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

                {expandVols && volumes.length > 0 && (
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
                            <span className="truncate">
                              {hasChapters && (
                                <span
                                  className="text-xs text-muted mr-1"
                                  onClick={(e) => toggleVolumeChaptersExpand(vIdx, e)}
                                >
                                  {isExpanded ? '▾' : '▸'}
                                </span>
                              )}
                              第 {vIdx} 卷: {vol.title || '篇卷'}
                            </span>
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
                          {hasChapters && isExpanded && (
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
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="chapter-tree-list">
              {chapters.length === 0 ? (
                <div className="empty-tree-hint">目前無章節，點擊上方按鈕建立</div>
              ) : (
                chapters.map((ch) => {
                  const isActive = ch.chapter_index === activeChapterIndex;
                  const words = ch.content ? ch.content.length : 0;
                  return (
                    <div
                      key={ch.chapter_index}
                      className={`tree-item ${isActive ? 'active' : ''}`}
                      onClick={() => {
                        onSelectChapter(ch.chapter_index);
                        if (isOpenMobile) onCloseMobile();
                      }}
                      role="button"
                      tabIndex={0}
                    >
                      <div className="tree-item-title">
                        <span className="tree-item-badge">
                          <IconFileText size={13} />
                        </span>
                        <span>第 {ch.chapter_index} 章</span>
                      </div>
                      <span className="tree-item-meta">{words} 字</span>
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

      {/* Standard Confirm Modal Card for Deletion */}
      {activeNovel && (
        <ConfirmModal
          isOpen={isDeleteModalOpen}
          onClose={() => setIsDeleteModalOpen(false)}
          onConfirm={handleDeleteConfirm}
          isLoading={isDeleting}
          title="刪除作品確認"
          message={`確定要刪除作品《${activeNovel.title}》嗎？此動作將刪除該小說的所有章節、世界觀、角色與分卷資料，且無法復原。`}
          confirmText="確認刪除"
          cancelText="取消"
          variant="danger"
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

