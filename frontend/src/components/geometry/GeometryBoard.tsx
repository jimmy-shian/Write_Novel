import React, { useState, useEffect } from 'react';
import { useGeometry } from '../../hooks/useGeometry';
import { GeometryStatsBar } from './GeometryStatsBar';
import { GeometryFilterBar } from './GeometryFilterBar';
import { GeometryCanvas } from './GeometryCanvas';
import { GeometryNodeDetail } from './GeometryNodeDetail';
import { GeometryParamsModal } from './GeometryParamsModal';
import { GeometryContextModal } from './GeometryContextModal';
import { GeometryNodeDto, GeometryParams } from '../../types/geometry';
import { Button } from '../common/Button';
import { IconLayers, IconPlus } from '../common/Icons';
import { showToast } from '../common/Toast';

interface GeometryBoardProps {
  novelId: string;
  activeChapterIndex?: number;
  onNavigateToChapter?: (chapterIndex: number) => void;
  onLog?: (msg: string) => void;
}

export const GeometryBoard: React.FC<GeometryBoardProps> = ({
  novelId,
  activeChapterIndex,
  onNavigateToChapter,
  onLog,
}) => {
  const {
    graphData,
    stats,
    loading,
    isGenerating,
    error,
    selectedVolumeIndex,
    setSelectedVolumeIndex,
    selectedThreadId,
    setSelectedThreadId,
    selectedEdgeType,
    setSelectedEdgeType,
    onlyUnfilled,
    setOnlyUnfilled,
    selectedNodeId,
    setSelectedNodeId,
    selectedNode,
    selectedNodeEdges,
    filteredNodes,
    filteredEdges,
    edgeTypeCounts,
    loadGraph,
    generateGraph,
    fetchNodeContext,
  } = useGeometry(novelId, { activeChapterIndex });

  const [isParamsOpen, setIsParamsOpen] = useState(false);
  const [contextModalNode, setContextModalNode] = useState<GeometryNodeDto | null>(null);
  // 右側檢查器收合（拓撲專用）：預設收合以放大中間心智圖，點節點自動展開
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);

  // 選中節點時自動展開右側檢查器
  useEffect(() => {
    if (selectedNodeId) {
      setIsInspectorOpen(true);
    }
  }, [selectedNodeId]);

  const handleSelectNode = (nodeId: string) => {
    setSelectedNodeId(nodeId);
    setIsInspectorOpen(true);
  };

  const handleRegenerate = async (customParams?: Partial<GeometryParams>) => {
    try {
      await generateGraph(customParams || {});
      showToast('敘事幾何骨架生成完成！', 'success');
      if (onLog) {
        onLog(`[幾何骨架] 成功生成小說 ${novelId} 幾何拓撲骨架`);
      }
      setIsParamsOpen(false);
    } catch (err: any) {
      showToast(`幾何骨架生成失敗: ${err.message}`, 'danger');
    }
  };

  return (
    <div className="geometry-board">
      {/* 1. 上區塊：篩選 + 操作同一行（省 40px+ 垂直高度） */}
      {graphData?.has_geometry && (
        <GeometryFilterBar
          volumes={graphData.volumes || []}
          threads={graphData.threads || []}
          selectedVolumeIndex={selectedVolumeIndex}
          onSelectVolume={setSelectedVolumeIndex}
          selectedThreadId={selectedThreadId}
          onSelectThread={setSelectedThreadId}
          selectedEdgeType={selectedEdgeType}
          onSelectEdgeType={setSelectedEdgeType}
          onlyUnfilled={onlyUnfilled}
          onToggleOnlyUnfilled={setOnlyUnfilled}
          visibleCount={filteredNodes.length}
          totalCount={graphData.nodes?.length || 0}
          visibleEdgeCount={filteredEdges.length}
          totalEdgeCount={graphData.edges?.length || 0}
          edgeCountByType={edgeTypeCounts?.edgeCountByType}
          nodeCountByType={edgeTypeCounts?.nodeCountByType}
          loading={loading || isGenerating}
          hasGeometry={graphData?.has_geometry}
          onRefresh={() => loadGraph(true)}
          onOpenParams={() => setIsParamsOpen(true)}
          onRegenerate={() => handleRegenerate()}
        />
      )}

      {/* 2. 極簡統計晶片條（24px 單行） */}
      {graphData?.has_geometry && (
        <GeometryStatsBar
          stats={stats}
          targetChapters={graphData.params?.target_chapters || 800}
        />
      )}

      {/* 4. Main Body Canvas & Inspector Layout */}
      {error && (
        <div
          className="geometry-error-banner"
          role="alert"
          style={{
            margin: '8px 16px 0 16px',
            padding: '8px 12px',
            fontSize: 12,
            color: 'var(--color-danger, #e5484d)',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          載入敘事幾何骨架失敗：{error}（若後端尚未重啟至最新版，請重啟後端後按「重新整理」）
        </div>
      )}
      {!graphData?.has_geometry ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center facts-empty-hint">
          <div className="w-16 h-16 rounded-2xl bg-[var(--surface-subtle)] text-accent flex items-center justify-center mb-4 border border-[var(--border)]">
            <IconLayers size={32} />
          </div>
          <h3 className="empty-title mb-2">尚未產生結構圖</h3>
          <p className="empty-desc mb-6">
            敘事幾何結構（Geometry-First）在正文撰寫前，預先演算鋪設長距伏筆、多線合流與主題對比邊。
          </p>
          <Button
            variant="primary"
            onClick={() => setIsParamsOpen(true)}
            icon={<IconPlus size={14} />}
          >
            產生結構圖
          </Button>
        </div>
      ) : (
        <div className={`geometry-body-layout ${isInspectorOpen ? 'inspector-open' : 'inspector-closed'}`}>
          {/* Center: Mindmap Canvas（收合右側時自動滿版） */}
          <GeometryCanvas
            nodes={filteredNodes}
            edges={filteredEdges}
            selectedNodeId={selectedNodeId}
            activeChapterIndex={activeChapterIndex}
            onSelectNode={handleSelectNode}
          />

          {/* Right: Node Details Inspector（可收合） */}
          {isInspectorOpen ? (
            <GeometryNodeDetail
              node={selectedNode}
              edges={selectedNodeEdges}
              onPreviewContext={(node) => setContextModalNode(node)}
              onNavigateToChapter={onNavigateToChapter}
              onClose={() => setIsInspectorOpen(false)}
            />
          ) : (
            <button
              type="button"
              className="geometry-inspector-reopen"
              onClick={() => setIsInspectorOpen(true)}
              title="展開右側檢查器"
            >
              <span className="geometry-inspector-reopen-text">檢查器</span>
            </button>
          )}
        </div>
      )}

      {/* 5. Modals */}
      {isParamsOpen && (
        <GeometryParamsModal
          isOpen={isParamsOpen}
          onClose={() => setIsParamsOpen(false)}
          initialParams={graphData?.params}
          onConfirm={handleRegenerate}
          isLoading={isGenerating}
        />
      )}

      {contextModalNode && (
        <GeometryContextModal
          isOpen={Boolean(contextModalNode)}
          onClose={() => setContextModalNode(null)}
          node={contextModalNode}
          onFetchContext={fetchNodeContext}
        />
      )}
    </div>
  );
};
