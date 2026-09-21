import React, { useMemo, useState, useRef, useEffect } from 'react';
import { GeometryNodeDto, GeometryEdgeDto } from '../../types/geometry';
import { Badge } from '../common/Badge';
import { StatusDot } from '../common/StatusDot';
import { IconCompass } from '../common/Icons';

interface GeometryMarkmapCanvasProps {
  nodes: GeometryNodeDto[];
  edges?: GeometryEdgeDto[];
  selectedNodeId: string | null;
  activeChapterIndex?: number;
  onSelectNode: (nodeId: string) => void;
}

// 關聯邊樣式：與圖例一致（實線=因果 / 虛線=呼應合流對比 / 點線=角色關係）
const EDGE_STYLE: Record<string, { color: string; dash?: string }> = {
  SETS_UP: { color: '#2563eb' },
  PAYS_OFF: { color: '#059669' },
  ECHOES: { color: '#7c3aed', dash: '5 4' },
  CONVERGES: { color: '#d97706', dash: '5 4' },
  CONTRASTS: { color: '#db2777', dash: '5 4' },
  CHARACTER_ARC: { color: '#0891b2', dash: '2 3' },
  RELATIONSHIP_CHANGE: { color: '#ea580c', dash: '2 3' },
};

interface MarkmapLeafNode {
  id: string;
  node: GeometryNodeDto;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface MarkmapArcBranch {
  arcIndex: number;
  key: string;
  title: string;
  color: string;
  isCollapsed: boolean;
  leafNodes: MarkmapLeafNode[];
  x: number;
  y: number;
  width: number;
  height: number;
  totalHeight: number;
}

interface MarkmapVolumeGroup {
  volumeIndex: number;
  title: string;
  color: string;
  isCollapsed: boolean;
  branches: MarkmapArcBranch[];
  x: number;
  y: number;
  width: number;
  height: number;
  totalHeight: number;
}

const ARC_PALETTE = [
  '#2563eb', // Blue
  '#059669', // Emerald
  '#d97706', // Amber
  '#7c3aed', // Purple
  '#db2777', // Pink
  '#0891b2', // Cyan
  '#ea580c', // Orange
];

export const GeometryMarkmapCanvas: React.FC<GeometryMarkmapCanvasProps> = ({
  nodes,
  edges = [],
  selectedNodeId,
  activeChapterIndex,
  onSelectNode,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // 折疊狀態管理 (Volume & Arc)
  const [collapsedKeys, setCollapsedKeys] = useState<Set<string>>(new Set());
  // 關聯邊顯示開關（A→C/D、E→A 這類跨節點網絡）
  const [showEdges, setShowEdges] = useState(true);

  // 平移與縮放狀態 (Pan & Zoom)
  const [transform, setTransform] = useState<{ x: number; y: number; scale: number }>({
    x: 40,
    y: 40,
    scale: 1,
  });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef<{ startX: number; startY: number; initX: number; initY: number }>({
    startX: 0,
    startY: 0,
    initX: 40,
    initY: 40,
  });

  const toggleCollapse = (key: string) => {
    setCollapsedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleExpandAll = () => setCollapsedKeys(new Set());
  const handleCollapseAll = () => {
    const all = new Set<string>();
    nodes.forEach((n) => {
      all.add(`vol-${n.volume_index}`);
      all.add(`arc-${n.volume_index}-${n.arc_index}`);
    });
    setCollapsedKeys(all);
  };

  const handleResetView = () => {
    setTransform({ x: 40, y: 40, scale: 1 });
  };

  const handleZoom = (delta: number) => {
    cancelFlight();
    setTransform((prev) => {
      const newScale = Math.min(2.0, Math.max(0.4, prev.scale + delta));
      return { ...prev, scale: Number(newScale.toFixed(2)) };
    });
  };

  // 滑鼠拖曳畫布：按住空白處拖曳平移，點節點卡片/按鈕則不觸發
  const handleMouseDown = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    // 節點卡片、控制列、按鈕一律不啟動拖曳（保留點擊選取/收合行為）
    if (target.closest('.markmap-node-card, .markmap-leaf-card, .geometry-markmap-controls, button')) {
      return;
    }
    // 只響應左鍵
    if (e.button !== 0) return;
    cancelFlight();
    setIsDragging(true);
    dragStartRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initX: transform.x,
      initY: transform.y,
    };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    const dx = e.clientX - dragStartRef.current.startX;
    const dy = e.clientY - dragStartRef.current.startY;
    setTransform((prev) => ({
      ...prev,
      x: dragStartRef.current.initX + dx,
      y: dragStartRef.current.initY + dy,
    }));
  };

  const handleMouseUp = () => setIsDragging(false);

  // 鬆開在畫布外也要結束拖曳，避免卡死在 dragging 態
  useEffect(() => {
    if (!isDragging) return;
    const end = () => setIsDragging(false);
    window.addEventListener('mouseup', end);
    return () => window.removeEventListener('mouseup', end);
  }, [isDragging]);

  // 滾輪縮放：原生 non-passive 監聽，避免 React passive 警告並阻止外層捲動
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 0.08 : -0.08;
      handleZoom(zoomFactor);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  // 1. 構建階層樹並計算 Markmap 座標
  const { volumeGroups, totalCanvasHeight, totalCanvasWidth } = useMemo(() => {
    // 按 Volume -> Arc 分組
    const volMap = new Map<number, Map<number, GeometryNodeDto[]>>();
    nodes.forEach((n) => {
      if (!volMap.has(n.volume_index)) volMap.set(n.volume_index, new Map());
      const arcMap = volMap.get(n.volume_index)!;
      if (!arcMap.has(n.arc_index)) arcMap.set(n.arc_index, []);
      arcMap.get(n.arc_index)!.push(n);
    });

    const VOL_X = 20;
    const VOL_WIDTH = 140;
    const ARC_X = VOL_X + VOL_WIDTH + 80;
    const ARC_WIDTH = 130;
    const LEAF_X = ARC_X + ARC_WIDTH + 70;
    const LEAF_WIDTH = 230;
    const LEAF_HEIGHT = 36;
    const LEAF_GAP = 8;
    const ARC_GAP = 20;
    const VOL_GAP = 32;

    let currentY = 20;
    const groups: MarkmapVolumeGroup[] = [];

    const sortedVolEntries = [...volMap.entries()].sort((a, b) => a[0] - b[0]);

    for (const [volIdx, arcMap] of sortedVolEntries) {
      const volKey = `vol-${volIdx}`;
      const isVolCollapsed = collapsedKeys.has(volKey);
      const volStartY = currentY;

      const branches: MarkmapArcBranch[] = [];
      const sortedArcEntries = [...arcMap.entries()].sort((a, b) => a[0] - b[0]);

      for (let i = 0; i < sortedArcEntries.length; i++) {
        const [arcIdx, rawNodes] = sortedArcEntries[i];
        const arcKey = `arc-${volIdx}-${arcIdx}`;
        const isArcCollapsed = collapsedKeys.has(arcKey);
        const branchColor = ARC_PALETTE[(volIdx + arcIdx) % ARC_PALETTE.length];

        rawNodes.sort(
          (a, b) => a.sequence_index - b.sequence_index || a.chapter_start - b.chapter_start
        );

        let arcContentHeight = 36; // 自身卡片高
        const leafNodes: MarkmapLeafNode[] = [];

        if (!isVolCollapsed && !isArcCollapsed) {
          let leafY = currentY;
          for (const node of rawNodes) {
            leafNodes.push({
              id: node.node_id,
              node,
              x: LEAF_X,
              y: leafY,
              width: LEAF_WIDTH,
              height: LEAF_HEIGHT,
            });
            leafY += LEAF_HEIGHT + LEAF_GAP;
          }
          arcContentHeight = Math.max(36, leafNodes.length * (LEAF_HEIGHT + LEAF_GAP));
        }

        const branchY = currentY + (leafNodes.length > 0 ? (arcContentHeight - 36) / 2 : 0);

        branches.push({
          arcIndex: arcIdx,
          key: arcKey,
          title: `弧線 ${arcIdx}`,
          color: branchColor,
          isCollapsed: isArcCollapsed,
          leafNodes,
          x: ARC_X,
          y: branchY,
          width: ARC_WIDTH,
          height: 36,
          totalHeight: arcContentHeight,
        });

        if (!isVolCollapsed) {
          currentY += arcContentHeight + ARC_GAP;
        }
      }

      if (isVolCollapsed) {
        currentY += 44 + VOL_GAP;
      } else {
        currentY += VOL_GAP;
      }

      const volTotalHeight = Math.max(44, currentY - volStartY - VOL_GAP);
      const volY = volStartY + (volTotalHeight - 44) / 2;

      groups.push({
        volumeIndex: volIdx,
        title: `第 ${volIdx} 卷`,
        color: '#2563eb',
        isCollapsed: isVolCollapsed,
        branches,
        x: VOL_X,
        y: volY,
        width: VOL_WIDTH,
        height: 44,
        totalHeight: volTotalHeight,
      });
    }

    return {
      volumeGroups: groups,
      totalCanvasHeight: Math.max(600, currentY + 100),
      // 右側預留關聯邊迴圈寬度（+160），避免 E→A 類長距邊被裁掉
      totalCanvasWidth: LEAF_X + LEAF_WIDTH + 160,
    };
  }, [nodes, collapsedKeys]);

  // 點擊關聯邊的飛行定位狀態（同一條再點一次就飛回另一端，來回跑）
  const [edgeFocus, setEdgeFocus] = useState<{ key: string; atTarget: boolean } | null>(null);
  const flightRef = useRef<number | null>(null);

  // 飛行定位：平滑把指定葉節點送到視口中央（保持目前縮放）
  const flyToLeaf = (leaf: MarkmapLeafNode) => {
    const el = containerRef.current;
    if (flightRef.current != null) {
      cancelAnimationFrame(flightRef.current);
      flightRef.current = null;
    }
    const setFinal = (x: number, y: number) =>
      setTransform((prev) => ({ ...prev, x, y }));
    if (!el || el.clientWidth === 0 || el.clientHeight === 0) {
      return;
    }
    const scale = transform.scale;
    const destX = el.clientWidth / 2 - (leaf.x + leaf.width / 2) * scale;
    const destY = el.clientHeight / 2 - (leaf.y + leaf.height / 2) * scale;
    const fromX = transform.x;
    const fromY = transform.y;
    if (Math.abs(destX - fromX) < 1 && Math.abs(destY - fromY) < 1) return;
    const start = performance.now();
    const duration = 450;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const e = 1 - Math.pow(1 - t, 3);
      setFinal(fromX + (destX - fromX) * e, fromY + (destY - fromY) * e);
      if (t < 1) {
        flightRef.current = requestAnimationFrame(step);
      } else {
        flightRef.current = null;
      }
    };
    flightRef.current = requestAnimationFrame(step);
  };

  // 使用者手動拖曳或縮放時中斷飛行
  const cancelFlight = () => {
    if (flightRef.current != null) {
      cancelAnimationFrame(flightRef.current);
      flightRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      if (flightRef.current != null) cancelAnimationFrame(flightRef.current);
    };
  }, []);

  // 2. 可見葉節點索引 + 真實關聯邊路徑（只畫兩端皆可見的邊）
  const { edgePaths, leafById } = useMemo(() => {
    const index = new Map<string, MarkmapLeafNode>();
    volumeGroups.forEach((vol) => {
      vol.branches.forEach((arc) => {
        arc.leafNodes.forEach((leaf) => {
          index.set(leaf.id, leaf);
        });
      });
    });
    const paths: { key: string; d: string; edge: GeometryEdgeDto }[] = [];
    if (showEdges) {
      const LOOP = 64; // 右側迴圈突出量
      edges.forEach((e) => {
        if (e.source === e.target) return;
        const s = index.get(e.source);
        const t = index.get(e.target);
        if (!s || !t) return; // 任一端被收合/篩選掉就不畫
        const sx = s.x + s.width;
        const sy = s.y + s.height / 2;
        const tx = t.x + t.width;
        const ty = t.y + t.height / 2;
        paths.push({
          key: e.edge_id || `${e.source}->${e.target}:${e.edge_type}`,
          d: `M ${sx} ${sy} C ${sx + LOOP} ${sy}, ${tx + LOOP} ${ty}, ${tx} ${ty}`,
          edge: e,
        });
      });
    }
    return { edgePaths: paths, leafById: index };
  }, [volumeGroups, edges, showEdges]);

  // 點關聯線：在 source/target 兩端來回飛行定位，並選中落點節點
  const handleEdgeClick = (e: React.MouseEvent, key: string, edge: GeometryEdgeDto) => {
    e.stopPropagation();
    const toTarget = edgeFocus?.key === key ? !edgeFocus.atTarget : true;
    const nodeId = toTarget ? edge.target : edge.source;
    const leaf = leafById.get(nodeId);
    if (!leaf) return;
    setEdgeFocus({ key, atTarget: toTarget });
    onSelectNode(leaf.node.node_id);
    flyToLeaf(leaf);
  };

  return (
    <div
      className={`geometry-markmap-container${isDragging ? ' markmap-dragging' : ''}`}
      ref={containerRef}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      style={{ cursor: isDragging ? 'grabbing' : undefined }}
    >
      {/* 浮動控制列 (Zoom, Pan Reset, Expand/Collapse) */}
      <div className="geometry-markmap-controls">
        <button
          type="button"
          className="markmap-control-btn"
          onClick={() => handleZoom(0.15)}
          title="放大 (+)"
        >
          +
        </button>
        <span className="markmap-zoom-label">{Math.round(transform.scale * 100)}%</span>
        <button
          type="button"
          className="markmap-control-btn"
          onClick={() => handleZoom(-0.15)}
          title="縮小 (-)"
        >
          -
        </button>
        <div className="markmap-control-divider" />
        <button
          type="button"
          className="markmap-control-btn"
          onClick={handleResetView}
          title="重置視圖視角"
        >
          <IconCompass size={13} />
        </button>
        <button
          type="button"
          className="markmap-control-pill-btn"
          onClick={handleExpandAll}
          title="全部展開"
        >
          全部展開
        </button>
        <button
          type="button"
          className="markmap-control-pill-btn"
          onClick={handleCollapseAll}
          title="全部收合"
        >
          全部收合
        </button>
        <div className="markmap-control-divider" />
        <button
          type="button"
          className={`markmap-control-pill-btn ${showEdges ? 'active' : ''}`}
          onClick={() => setShowEdges((v) => !v)}
          title={showEdges ? '隱藏節點間關聯邊（A→C/D、E→A 網絡）' : '顯示節點間關聯邊（A→C/D、E→A 網絡）'}
          aria-pressed={showEdges}
        >
          關聯邊{edges.length > 0 ? ` ${edgePaths.length}/${edges.length}` : ''}
        </button>
      </div>

      {/* SVG 繪製平滑三次貝茲曲線分支與 DOM 節點容器 */}
      <div
        className="geometry-markmap-stage"
        style={{
          transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
          transformOrigin: '0 0',
          width: totalCanvasWidth,
          height: totalCanvasHeight,
        }}
      >
        <svg
          className="geometry-markmap-svg"
          width={totalCanvasWidth}
          height={totalCanvasHeight}
        >
          <defs>
            <filter id="markmap-shadow" x="-10%" y="-10%" width="120%" height="120%">
              <feDropShadow dx="0" dy="2" stdDeviation="3" floodOpacity="0.06" />
            </filter>
            {Object.entries(EDGE_STYLE).map(([type, style]) => (
              <marker
                key={`arrow-${type}`}
                id={`markmap-arrow-${type}`}
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 9 5 L 0 9 z" fill={style.color} />
              </marker>
            ))}
            <marker
              id="markmap-arrow-DEFAULT"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 9 5 L 0 9 z" fill="#94a3b8" />
            </marker>
          </defs>

          {/* 繪製平滑三次貝茲曲線連線 */}
          {volumeGroups.map((vol) => {
            const volEndX = vol.x + vol.width;
            const volMidY = vol.y + vol.height / 2;

            return (
              <g key={`vol-g-${vol.volumeIndex}`}>
                {!vol.isCollapsed &&
                  vol.branches.map((arc) => {
                    const arcStartX = arc.x;
                    const arcMidY = arc.y + arc.height / 2;
                    const c1x = volEndX + (arcStartX - volEndX) * 0.55;
                    const c2x = arcStartX - (arcStartX - volEndX) * 0.45;

                    const arcEndX = arc.x + arc.width;

                    return (
                      <g key={`arc-g-${arc.key}`}>
                        {/* Vol -> Arc 連線 */}
                        <path
                          d={`M ${volEndX} ${volMidY} C ${c1x} ${volMidY}, ${c2x} ${arcMidY}, ${arcStartX} ${arcMidY}`}
                          fill="none"
                          stroke={arc.color}
                          strokeWidth="2"
                          strokeOpacity="0.8"
                          className="markmap-curve"
                        />

                        {/* Arc -> Leaf 連線 */}
                        {!arc.isCollapsed &&
                          arc.leafNodes.map((leaf) => {
                            const leafStartX = leaf.x;
                            const leafMidY = leaf.y + leaf.height / 2;
                            const lc1x = arcEndX + (leafStartX - arcEndX) * 0.55;
                            const lc2x = leafStartX - (leafStartX - arcEndX) * 0.45;

                            return (
                              <path
                                key={`leaf-path-${leaf.id}`}
                                d={`M ${arcEndX} ${arcMidY} C ${lc1x} ${arcMidY}, ${lc2x} ${leafMidY}, ${leafStartX} ${leafMidY}`}
                                fill="none"
                                stroke={arc.color}
                                strokeWidth="1.5"
                                strokeOpacity="0.5"
                                className="markmap-curve"
                              />
                            );
                          })}
                      </g>
                    );
                  })}
              </g>
              );
            })}

            {/* 真實關聯邊網絡（A→C/D、E→A）：右側迴圈曲線，方向箭頭指向 target */}
            {showEdges &&
              edgePaths.map(({ key, d, edge }) => {
                const style = EDGE_STYLE[edge.edge_type] || { color: '#94a3b8' };
                const isIncident =
                  selectedNodeId != null &&
                  (edge.source === selectedNodeId || edge.target === selectedNodeId);
                const dimOthers = selectedNodeId != null && !isIncident;
                const focused = edgeFocus?.key === key;
                return (
                  <path
                    key={`edge-${key}`}
                    d={d}
                    fill="none"
                    stroke={style.color}
                    strokeWidth={focused ? 2.8 : isIncident ? 2.4 : 1.3}
                    strokeOpacity={focused ? 1 : isIncident ? 0.95 : dimOthers ? 0.12 : 0.38}
                    strokeDasharray={style.dash || undefined}
                    markerEnd={`url(#markmap-arrow-${EDGE_STYLE[edge.edge_type] ? edge.edge_type : 'DEFAULT'})`}
                    className="markmap-curve markmap-edge-curve"
                    onClick={(ev) => handleEdgeClick(ev, key, edge)}
                  >
                    <title>{`${edge.source} → ${edge.target} · ${edge.edge_type}（點擊在兩端來回定位）`}</title>
                  </path>
                );
              })}
          </svg>

        {/* DOM 層級節點元素 (便於文字選取、點擊檢查、樣式客製化) */}
        {volumeGroups.map((vol) => {
          return (
            <React.Fragment key={`vol-nodes-${vol.volumeIndex}`}>
              {/* Level 0: Volume Root 節點 */}
              <div
                className="markmap-node-card markmap-volume-card"
                style={{
                  left: vol.x,
                  top: vol.y,
                  width: vol.width,
                  height: vol.height,
                }}
              >
                <div className="markmap-volume-title">{vol.title}</div>
                <button
                  type="button"
                  className={`markmap-toggle-dot ${vol.isCollapsed ? 'collapsed' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleCollapse(`vol-${vol.volumeIndex}`);
                  }}
                  title={vol.isCollapsed ? '展開此卷' : '收合此卷'}
                >
                  {vol.isCollapsed ? '+' : '−'}
                </button>
              </div>

              {/* Level 1: Arc 故事弧分支 */}
              {!vol.isCollapsed &&
                vol.branches.map((arc) => (
                  <React.Fragment key={`arc-nodes-${arc.key}`}>
                    <div
                      className="markmap-node-card markmap-arc-card"
                      style={{
                        left: arc.x,
                        top: arc.y,
                        width: arc.width,
                        height: arc.height,
                        borderColor: arc.color,
                      }}
                    >
                      <span
                        className="markmap-arc-color-tag"
                        style={{ background: arc.color }}
                      />
                      <span className="markmap-arc-title">{arc.title}</span>
                      <button
                        type="button"
                        className={`markmap-toggle-dot ${arc.isCollapsed ? 'collapsed' : ''}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleCollapse(arc.key);
                        }}
                        title={arc.isCollapsed ? '展開此弧線' : '收合此弧線'}
                        style={{ borderColor: arc.color, color: arc.color }}
                      >
                        {arc.isCollapsed ? '+' : '−'}
                      </button>
                    </div>

                    {/* Level 2: 章節事件 Leaf 節點 */}
                    {!arc.isCollapsed &&
                      arc.leafNodes.map((leaf) => {
                        const isSelected = selectedNodeId === leaf.node.node_id;
                        const isHighlighted =
                          Boolean(activeChapterIndex) &&
                          activeChapterIndex! >= leaf.node.chapter_start &&
                          activeChapterIndex! <= leaf.node.chapter_end;
                        const hasSemantic = Boolean(leaf.node.semantic);

                        return (
                          <div
                            key={`leaf-item-${leaf.id}`}
                            className={`markmap-leaf-card ${isSelected ? 'selected' : ''} ${
                              isHighlighted ? 'highlighted' : ''
                            }`}
                            style={{
                              left: leaf.x,
                              top: leaf.y,
                              width: leaf.width,
                              height: leaf.height,
                            }}
                            onClick={() => onSelectNode(leaf.node.node_id)}
                            title={`${leaf.node.node_id} · 第 ${leaf.node.chapter_start}${
                              leaf.node.chapter_end !== leaf.node.chapter_start
                                ? `-${leaf.node.chapter_end}`
                                : ''
                            } 章 · ${leaf.node.primary_thread || '全域'}`}
                          >
                            <StatusDot
                              status={hasSemantic ? 'success' : 'neutral'}
                              size="sm"
                              title={hasSemantic ? '已填入文學語義' : '空幾何拓撲節點'}
                            />
                            <span className="markmap-node-id">{leaf.node.node_id}</span>
                            <span className="markmap-node-chapter">
                              第 {leaf.node.chapter_start}
                              {leaf.node.chapter_end !== leaf.node.chapter_start
                                ? `-${leaf.node.chapter_end}`
                                : ''}{' '}
                              章
                            </span>
                            <Badge variant="neutral" size="sm">
                              {leaf.node.structural_role}
                            </Badge>
                          </div>
                        );
                      })}
                  </React.Fragment>
                ))}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
