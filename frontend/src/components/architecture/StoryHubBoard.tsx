import React, { useState, useEffect } from 'react';
import { Novel, TemporalGraphSlice } from '../../types';
import { GeometryBoard } from '../geometry/GeometryBoard';
import { TemporalGraphBoard } from '../graph/TemporalGraphBoard';
import { NarrativeEngineBoard } from '../narrative/NarrativeEngineBoard';
import { IconLayers, IconGitBranch, IconCompass } from '../common/Icons';

export type StoryHubSubTab = 'geometry' | 'graph' | 'narrative';

interface StoryHubBoardProps {
  novel: Novel | null;
  novelId: string;
  activeChapterIndex: number;
  chapterContent: string;
  activeSubTab?: StoryHubSubTab;
  onSelectSubTab?: (subTab: StoryHubSubTab) => void;
  onNavigateToChapter?: (chapterIndex: number) => void;
  onLog?: (msg: string) => void;

  // Temporal Graphiti Props
  graphSlice: TemporalGraphSlice | null;
  isGraphLoading: boolean;
  isGraphExtracting: boolean;
  onRefreshGraph: () => void;
  onAddFact: (statement: string) => void;
  onInvalidateFact: (factId: string, supersededBy?: string) => void;
  onDeleteFact: (factId: string) => void;
  onExtractFromChapter: (content: string) => void;
}

export const StoryHubBoard: React.FC<StoryHubBoardProps> = ({
  novel,
  novelId,
  activeChapterIndex,
  chapterContent,
  activeSubTab = 'geometry',
  onSelectSubTab,
  onNavigateToChapter,
  onLog,
  graphSlice,
  isGraphLoading,
  isGraphExtracting,
  onRefreshGraph,
  onAddFact,
  onInvalidateFact,
  onDeleteFact,
  onExtractFromChapter,
}) => {
  const [currentSubTab, setCurrentSubTab] = useState<StoryHubSubTab>(activeSubTab);

  // 當外部傳入 activeSubTab（如透過頂欄 WorkspaceNavDropdown 選擇時）保持同步
  useEffect(() => {
    if (activeSubTab && activeSubTab !== currentSubTab) {
      setCurrentSubTab(activeSubTab);
    }
  }, [activeSubTab]);

  const handleTabChange = (tab: StoryHubSubTab) => {
    setCurrentSubTab(tab);
    if (onSelectSubTab) {
      onSelectSubTab(tab);
    }
  };

  return (
    <div className="architecture-board">
      {/* 頂部中樞導航欄（整合 幾何骨架 / 時序圖譜 / 推理引擎） */}
      <div className="architecture-hub-header compact">
        <div className="architecture-nav-tabs" role="tablist" aria-label="故事架構中樞導航">
          <button
            type="button"
            role="tab"
            aria-selected={currentSubTab === 'geometry'}
            className={`architecture-tab-btn ${currentSubTab === 'geometry' ? 'active' : ''}`}
            onClick={() => handleTabChange('geometry')}
            title="敘事幾何骨架圖"
          >
            <IconLayers size={14} />
            <span>幾何拓撲 (Geometry)</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={currentSubTab === 'graph'}
            className={`architecture-tab-btn ${currentSubTab === 'graph' ? 'active' : ''}`}
            onClick={() => handleTabChange('graph')}
            title="時序記憶圖譜"
          >
            <IconGitBranch size={14} />
            <span>時序圖譜 (Graphiti)</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={currentSubTab === 'narrative'}
            className={`architecture-tab-btn ${currentSubTab === 'narrative' ? 'active' : ''}`}
            onClick={() => handleTabChange('narrative')}
            title="敘事推理引擎"
          >
            <IconCompass size={14} />
            <span>推理引擎 (Story Engine 2.0)</span>
          </button>
        </div>
      </div>

      {/* 主工作區切換 */}
      <div className="architecture-hub-body">
        {currentSubTab === 'geometry' && (
          <GeometryBoard
            novelId={novelId}
            activeChapterIndex={activeChapterIndex}
            onNavigateToChapter={onNavigateToChapter}
            onLog={onLog}
          />
        )}

        {currentSubTab === 'graph' && (
          <TemporalGraphBoard
            graphSlice={graphSlice}
            chapterIndex={activeChapterIndex}
            chapterContent={chapterContent}
            isLoading={isGraphLoading}
            isExtracting={isGraphExtracting}
            onRefresh={onRefreshGraph}
            onAddFact={onAddFact}
            onInvalidateFact={onInvalidateFact}
            onDeleteFact={onDeleteFact}
            onExtractFromChapter={onExtractFromChapter}
          />
        )}

        {currentSubTab === 'narrative' && (
          <NarrativeEngineBoard
            novel={novel}
            activeChapterIndex={activeChapterIndex}
          />
        )}
      </div>
    </div>
  );
};
