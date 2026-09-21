import React, { useMemo, useState } from 'react';
import { GeometryNodeDto, GeometryEdgeDto } from '../../types/geometry';
import { GeometryNodeCard } from './GeometryNodeCard';
import { GeometryMarkmapCanvas } from './GeometryMarkmapCanvas';
import { Badge } from '../common/Badge';
import { StatusDot } from '../common/StatusDot';

interface GeometryCanvasProps {
  nodes: GeometryNodeDto[];
  edges: GeometryEdgeDto[];
  selectedNodeId: string | null;
  activeChapterIndex?: number;
  onSelectNode: (nodeId: string) => void;
}

type ViewMode = 'markmap' | 'tree' | 'swimlane';

export const GeometryCanvas: React.FC<GeometryCanvasProps> = ({
  nodes,
  edges,
  selectedNodeId,
  activeChapterIndex,
  onSelectNode,
}) => {
  // 預設為心智圖 (markmap) 檢視
  const [viewMode, setViewMode] = useState<ViewMode>('markmap');
  const [collapsedArcs, setCollapsedArcs] = useState<Set<string>>(new Set());
  const [legendOpen, setLegendOpen] = useState(false);

  // 將節點按 篇卷 (Volume) 與 故事弧 (Arc) 分組展示為泳道
  const groupedArcs = useMemo(() => {
    const groups: { [key: string]: GeometryNodeDto[] } = {};
    nodes.forEach((n) => {
      const key = `卷 ${n.volume_index} · 弧線 ${n.arc_index}`;
      if (!groups[key]) groups[key] = [];
      groups[key].push(n);
    });
    // 每組內按 sequence / 章節排序，瀏覽更順
    for (const k of Object.keys(groups)) {
      groups[k].sort(
        (a, b) => a.sequence_index - b.sequence_index || a.chapter_start - b.chapter_start
      );
    }
    return groups;
  }, [nodes]);

  // Tree 用：卷 -> 弧 -> 節點 二層結構
  const treeByVolume = useMemo(() => {
    const vols: { volume_index: number; arcs: { arc_index: number; key: string; nodes: GeometryNodeDto[] }[] }[] = [];
    const volMap = new Map<number, Map<number, GeometryNodeDto[]>>();
    nodes.forEach((n) => {
      if (!volMap.has(n.volume_index)) volMap.set(n.volume_index, new Map());
      const arcMap = volMap.get(n.volume_index)!;
      if (!arcMap.has(n.arc_index)) arcMap.set(n.arc_index, []);
      arcMap.get(n.arc_index)!.push(n);
    });
    [...volMap.entries()]
      .sort((a, b) => a[0] - b[0])
      .forEach(([vol, arcMap]) => {
        const arcs = [...arcMap.entries()]
          .sort((a, b) => a[0] - b[0])
          .map(([arcIdx, list]) => {
            list.sort(
              (a, b) => a.sequence_index - b.sequence_index || a.chapter_start - b.chapter_start
            );
            return {
              arc_index: arcIdx,
              key: `卷 ${vol} · 弧線 ${arcIdx}`,
              nodes: list,
            };
          });
        vols.push({ volume_index: vol, arcs });
      });
    return vols;
  }, [nodes]);

  const arcKeys = useMemo(() => Object.keys(groupedArcs), [groupedArcs]);
  const allCollapsed = arcKeys.length > 0 && arcKeys.every((k) => collapsedArcs.has(k));

  const toggleArc = (key: string) => {
    setCollapsedArcs((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const setAllCollapsed = (collapsed: boolean) => {
    if (collapsed) setCollapsedArcs(new Set(arcKeys));
    else setCollapsedArcs(new Set());
  };

  const isNodeHighlighted = (node: GeometryNodeDto) =>
    Boolean(activeChapterIndex) &&
    activeChapterIndex! >= node.chapter_start &&
    activeChapterIndex! <= node.chapter_end;

  const renderTreeRow = (node: GeometryNodeDto) => {
    const isSelected = selectedNodeId === node.node_id;
    const isHighlighted = isNodeHighlighted(node);
    const hasSemantic = Boolean(node.semantic);
    return (
      <div
        key={node.node_id}
        className={`geometry-tree-row ${isSelected ? 'selected' : ''} ${isHighlighted ? 'highlighted' : ''}`}
        onClick={() => onSelectNode(node.node_id)}
        role="treeitem"
        aria-selected={isSelected}
        title={`${node.node_id} · 第 ${node.chapter_start}${node.chapter_end !== node.chapter_start ? `-${node.chapter_end}` : ''} 章 · ${node.primary_thread || '全域'}`}
      >
        <span className="geometry-tree-toggle-dummy" aria-hidden="true" />
        <StatusDot
          status={hasSemantic ? 'success' : 'neutral'}
          size="sm"
          title={hasSemantic ? '已注入文學語義' : '空拓撲 (semantic = NULL)'}
        />
        <span className="geometry-node-id">{node.node_id}</span>
        <span className="geometry-tree-row-chapter">
          第 {node.chapter_start}{node.chapter_end !== node.chapter_start ? `-${node.chapter_end}` : ''} 章
        </span>
        <span className="geometry-tree-row-thread">{node.primary_thread || '全域'}</span>
        <Badge variant="neutral" size="sm">{node.structural_role}</Badge>
        {!hasSemantic && <span className="geometry-tree-row-unfilled">待填充</span>}
      </div>
    );
  };

  return (
    <div className="geometry-canvas-container">
      {/* 工具列：檢視模式切換 (Markmap / 樹狀清單 / 泳道卡片) + 全部展開/收合 + 圖例收合 */}
      <div className="geometry-canvas-toolbar">
        <div className="geometry-view-toggle" role="tablist" aria-label="檢視模式">
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'markmap'}
            className={`geometry-view-toggle-btn ${viewMode === 'markmap' ? 'active' : ''}`}
            onClick={() => setViewMode('markmap')}
            title="心智圖：卷→弧→節點分支圖＋真實關聯邊網絡（A→C/D、E→A），空白拖曳、滾輪縮放"
          >
            心智圖
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'tree'}
            className={`geometry-view-toggle-btn ${viewMode === 'tree' ? 'active' : ''}`}
            onClick={() => setViewMode('tree')}
            title="樹狀：卷 › 弧 › 節點縱向清單，適合逐章順讀定位；點弧標題收合，點行選中"
          >
            樹狀
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'swimlane'}
            className={`geometry-view-toggle-btn ${viewMode === 'swimlane' ? 'active' : ''}`}
            onClick={() => setViewMode('swimlane')}
            title="泳道：每弧一條橫向卡片帶，適合對比同弧內多節點；橫滑瀏覽，點卡片選中"
          >
            泳道
          </button>
        </div>

        {viewMode !== 'markmap' && (
          <button
            type="button"
            className="geometry-filter-pill-btn"
            onClick={() => setAllCollapsed(!allCollapsed)}
          >
            {allCollapsed ? '全部展開' : '全部收合'}
          </button>
        )}

        <button
          type="button"
          className="geometry-filter-pill-btn"
          onClick={() => setLegendOpen((v) => !v)}
          aria-expanded={legendOpen}
          title="顯示 / 隱藏拓撲邊圖例"
        >
          {legendOpen ? '隱藏圖例' : '圖例'}
        </button>

        <span className="geometry-canvas-toolbar-hint">
          {viewMode === 'markmap'
            ? '心智圖：分支＋關聯邊網絡 · 空白拖曳 · 滾輪縮放 · 點圓圈收合 · 點關聯線來回跳轉'
            : viewMode === 'tree'
            ? '樹狀：卷 › 弧 › 節點縱向清單，點弧標題逐層收合，點行選中節點'
            : '泳道：每弧一條橫向卡片帶，橫滑瀏覽同弧節點，點卡片選中'}
        </span>
      </div>

      {/* 邊線圖例 (預設收合，省垂直空間) */}
      {legendOpen && (
        <div className="geometry-legend-bar geometry-legend-bar-open">
          <span>拓撲邊圖例：</span>
          <Badge variant="accent" size="sm">實線: SETS_UP / PAYS_OFF (因果鋪墊/高潮兌現)</Badge>
          <Badge variant="warning" size="sm">虛線: ECHOES / CONVERGES / CONTRASTS (呼應/合流/對比)</Badge>
          <Badge variant="success" size="sm">點線: CHARACTER_ARC / RELATIONSHIP (角色弧/關係質變)</Badge>
        </div>
      )}

      {/* 畫布視圖 */}
      {nodes.length === 0 ? (
        <div className="p-8 text-center text-xs text-[var(--text-muted)]">
          當前篩選條件下無符合的幾何節點
        </div>
      ) : viewMode === 'markmap' ? (
        /* Markmap 心智圖視圖（含真實關聯邊網絡） */
        <GeometryMarkmapCanvas
          nodes={nodes}
          edges={edges}
          selectedNodeId={selectedNodeId}
          activeChapterIndex={activeChapterIndex}
          onSelectNode={onSelectNode}
        />
      ) : viewMode === 'swimlane' ? (
        /* 泳道卡片視圖 */
        Object.entries(groupedArcs).map(([arcTitle, arcNodes]) => {
          const collapsed = collapsedArcs.has(arcTitle);
          return (
            <div key={arcTitle} className="geometry-swimlane">
              <button
                type="button"
                className="geometry-swimlane-header geometry-swimlane-header-btn"
                onClick={() => toggleArc(arcTitle)}
                aria-expanded={!collapsed}
                title={collapsed ? '展開此弧線' : '收合此弧線'}
              >
                <span className="geometry-swimlane-title">
                  <span className="geometry-collapse-caret" aria-hidden="true">
                    {collapsed ? '▸' : '▾'}
                  </span>
                  {arcTitle}
                </span>
                <span className="text-xs text-[var(--text-muted)]">
                  共 {arcNodes.length} 個節點
                </span>
              </button>

              {!collapsed && (
                <div className="geometry-nodes-track">
                  {arcNodes.map((node) => (
                    <GeometryNodeCard
                      key={node.node_id}
                      node={node}
                      isSelected={selectedNodeId === node.node_id}
                      isHighlighted={isNodeHighlighted(node)}
                      onClick={() => onSelectNode(node.node_id)}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })
      ) : (
        /* 樹狀視圖：卷 › 弧 › 節點，縱向緊湊清單 */
        <div className="geometry-tree" role="tree" aria-label="幾何節點樹">
          {treeByVolume.map((vol) => {
            const volNodeCount = vol.arcs.reduce((s, a) => s + a.nodes.length, 0);
            return (
              <div key={vol.volume_index} className="geometry-tree-volume">
                <div className="geometry-tree-volume-header">
                  <span className="geometry-tree-volume-title">
                    ▾ 第 {vol.volume_index} 卷
                  </span>
                  <span className="text-xs text-[var(--text-muted)]">
                    {vol.arcs.length} 弧 · {volNodeCount} 節點
                  </span>
                </div>
                {vol.arcs.map((arc) => {
                  const collapsed = collapsedArcs.has(arc.key);
                  return (
                    <div key={arc.key} className="geometry-tree-arc">
                      <button
                        type="button"
                        className="geometry-tree-arc-header"
                        onClick={() => toggleArc(arc.key)}
                        aria-expanded={!collapsed}
                        title={collapsed ? '展開此弧線' : '收合此弧線'}
                      >
                        <span className="geometry-collapse-caret" aria-hidden="true">
                          {collapsed ? '▸' : '▾'}
                        </span>
                        <span className="geometry-tree-arc-title">弧線 {arc.arc_index}</span>
                        <span className="text-xs text-[var(--text-muted)]">
                          {arc.nodes.length} 個節點
                        </span>
                      </button>
                      {!collapsed && (
                        <div className="geometry-tree-rows" role="group">
                          {arc.nodes.map(renderTreeRow)}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
