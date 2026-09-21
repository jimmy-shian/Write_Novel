import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  geometryApi,
  GeometryGraphResponse,
  GeometryStats,
  GeometryParams,
  GeometryNodeDto,
  GeometryEdgeDto,
  NodeContextPackage,
} from '../api/geometry';
import { NARRATIVE_REFRESH_EVENT, ChapterContentUpdatedDetail } from '../utils/narrativeRefresh';

export interface UseGeometryOptions {
  activeChapterIndex?: number;
}

export function useGeometry(novelId: string | null, options: UseGeometryOptions = {}) {
  const [graphData, setGraphData] = useState<GeometryGraphResponse | null>(null);
  const [stats, setStats] = useState<GeometryStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters & selection
  const [selectedVolumeIndex, setSelectedVolumeIndex] = useState<number | 'all'>(1);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [selectedEdgeType, setSelectedEdgeType] = useState<string | null>(null);
  const [onlyUnfilled, setOnlyUnfilled] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  const clearPoll = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  useEffect(() => {
    return () => clearPoll();
  }, []);

  const loadGraph = useCallback(
    async (showLoading = true) => {
      if (!novelId) {
        setGraphData(null);
        setStats(null);
        return;
      }
      if (showLoading) setLoading(true);
      setError(null);
      try {
        const res = await geometryApi.getGeometry(novelId);
        setGraphData(res);
        setStats(res.stats);

        // 如果目前選取的 volume 不在可用卷清單中，自動設為第 1 卷或 'all'
        if (res.volumes && res.volumes.length > 0) {
          const hasVol = res.volumes.some((v) => v.volume_index === selectedVolumeIndex);
          if (!hasVol && selectedVolumeIndex !== 'all') {
            setSelectedVolumeIndex(res.volumes[0].volume_index);
          }
        }
      } catch (err: any) {
        setError(err?.message || '載入敘事幾何骨架失敗');
      } finally {
        if (showLoading) setLoading(false);
      }
    },
    [novelId, selectedVolumeIndex]
  );

  useEffect(() => {
    loadGraph(true);
  }, [novelId]);

  // 清空生成後自動重載樹：後端已連動刪除 geometry_* 六表，前端快取若不重載會殘留舊樹。
  // App.tsx 在清空完成後會廣播 reset-content 事件，此處收到屬於當前作品的通知即靜默重載並清除選取。
  useEffect(() => {
    if (!novelId) return;
    const listener = (e: Event) => {
      const detail = (e as CustomEvent<ChapterContentUpdatedDetail>).detail;
      if (!detail || detail.novelId !== novelId) return;
      if (detail.reason !== 'reset-content') return;
      setSelectedNodeId(null);
      setSelectedThreadId(null);
      setSelectedEdgeType(null);
      loadGraph(false);
    };
    window.addEventListener(NARRATIVE_REFRESH_EVENT, listener);
    return () => window.removeEventListener(NARRATIVE_REFRESH_EVENT, listener);
  }, [novelId, loadGraph]);

  // 當傳入 activeChapterIndex 時，嘗試反向選取對應章節的幾何節點
  useEffect(() => {
    if (!options.activeChapterIndex || !graphData?.nodes) return;
    const target = graphData.nodes.find(
      (n) =>
        options.activeChapterIndex! >= n.chapter_start &&
        options.activeChapterIndex! <= n.chapter_end
    );
    if (target) {
      setSelectedNodeId(target.node_id);
      if (selectedVolumeIndex !== 'all' && target.volume_index !== selectedVolumeIndex) {
        setSelectedVolumeIndex(target.volume_index);
      }
    }
  }, [options.activeChapterIndex, graphData]);

  // 重新產生拓撲骨架
  const generateGraph = useCallback(
    async (params: Partial<GeometryParams>) => {
      if (!novelId) return;
      setIsGenerating(true);
      setError(null);
      try {
        await geometryApi.generate(novelId, params);
        await loadGraph(false);
      } catch (err: any) {
        setError(err?.message || '重新生成幾何骨架失敗');
        throw err;
      } finally {
        setIsGenerating(false);
      }
    },
    [novelId, loadGraph]
  );

  // 取得節點 Context 包裹
  const fetchNodeContext = useCallback(
    async (nodeId: string): Promise<NodeContextPackage | null> => {
      if (!novelId || !nodeId) return null;
      try {
        return await geometryApi.getNodeContext(novelId, nodeId);
      } catch (err) {
        console.warn('載入節點 Context 失敗，退回客戶端預覽', err);
        return null;
      }
    },
    [novelId]
  );

  // 篩選後的可視節點（量級防爆：限制單卷或線程篩選）
  // 注意：邊類型也會收斂節點 — 只保留至少有一條該類型邊（且另一端也在卷/線程/語義篩選內）的節點，
  // 否則「鋪設/合流」切換時右側 136/1601 完全不會動。
  const baseFilteredNodes = useMemo<GeometryNodeDto[]>(() => {
    if (!graphData?.nodes) return [];
    return graphData.nodes.filter((node) => {
      if (selectedVolumeIndex !== 'all' && node.volume_index !== selectedVolumeIndex) {
        return false;
      }
      if (selectedThreadId && node.primary_thread !== selectedThreadId) {
        return false;
      }
      if (onlyUnfilled && Boolean(node.semantic)) {
        return false;
      }
      return true;
    });
  }, [graphData?.nodes, selectedVolumeIndex, selectedThreadId, onlyUnfilled]);

  const baseNodeIdSet = useMemo(() => {
    return new Set(baseFilteredNodes.map((n) => n.node_id));
  }, [baseFilteredNodes]);

  const filteredNodes = useMemo<GeometryNodeDto[]>(() => {
    if (!selectedEdgeType) return baseFilteredNodes;
    if (!graphData?.edges) return baseFilteredNodes;
    const incident = new Set<string>();
    for (const e of graphData.edges) {
      if (e.edge_type !== selectedEdgeType) continue;
      // 只要當前篩選範圍內的節點有作為 source 或 target 參與該類型邊（包含跨卷鋪設、跨卷合流）即保留
      if (baseNodeIdSet.has(e.source)) {
        incident.add(e.source);
      }
      if (baseNodeIdSet.has(e.target)) {
        incident.add(e.target);
      }
    }
    return baseFilteredNodes.filter((n) => incident.has(n.node_id));
  }, [baseFilteredNodes, baseNodeIdSet, graphData?.edges, selectedEdgeType]);

  const visibleNodeIdSet = useMemo(() => {
    return new Set(filteredNodes.map((n) => n.node_id));
  }, [filteredNodes]);

  // 篩選後的可視邊：若未選擇邊類型，顯示兩端皆在可視節點的邊；
  // 若已選定特定邊類型，則顯示至少有一端在可視節點範圍內的該類型邊（或兩端皆在全域有效節點）
  const filteredEdges = useMemo<GeometryEdgeDto[]>(() => {
    if (!graphData?.edges) return [];
    return graphData.edges.filter((edge) => {
      if (selectedEdgeType) {
        if (edge.edge_type !== selectedEdgeType) return false;
        // 至少一端在當前可視節點中
        return visibleNodeIdSet.has(edge.source) || visibleNodeIdSet.has(edge.target);
      }
      return visibleNodeIdSet.has(edge.source) && visibleNodeIdSet.has(edge.target);
    });
  }, [graphData?.edges, visibleNodeIdSet, selectedEdgeType]);

  // 各邊類型在「目前卷/線程/語義篩選下」的邊數 + 關聯節點數，供下拉選單顯示計數
  const edgeTypeCounts = useMemo(() => {
    const edgeCountByType: Record<string, number> = {};
    const nodeSetByType: Record<string, Set<string>> = {};
    if (graphData?.edges) {
      for (const e of graphData.edges) {
        const srcIn = baseNodeIdSet.has(e.source);
        const tgtIn = baseNodeIdSet.has(e.target);
        // 只要任一端在當前篩選卷/線程內，就算作與該範圍相關的邊
        if (!srcIn && !tgtIn) continue;
        edgeCountByType[e.edge_type] = (edgeCountByType[e.edge_type] || 0) + 1;
        if (!nodeSetByType[e.edge_type]) nodeSetByType[e.edge_type] = new Set<string>();
        if (srcIn) nodeSetByType[e.edge_type].add(e.source);
        if (tgtIn) nodeSetByType[e.edge_type].add(e.target);
      }
    }
    const nodeCountByType: Record<string, number> = {};
    for (const [k, v] of Object.entries(nodeSetByType)) nodeCountByType[k] = v.size;
    return { edgeCountByType, nodeCountByType };
  }, [graphData?.edges, baseNodeIdSet]);

  // 當前選取的節點
  const selectedNode = useMemo<GeometryNodeDto | null>(() => {
    if (!selectedNodeId || !graphData?.nodes) return null;
    return graphData.nodes.find((n) => n.node_id === selectedNodeId) || null;
  }, [selectedNodeId, graphData?.nodes]);

  // 當前選取節點的關聯邊 (Incoming & Outgoing)
  const selectedNodeEdges = useMemo(() => {
    if (!selectedNodeId || !graphData?.edges) {
      return { incoming: [], outgoing: [] };
    }
    const incoming = graphData.edges.filter((e) => e.target === selectedNodeId);
    const outgoing = graphData.edges.filter((e) => e.source === selectedNodeId);
    return { incoming, outgoing };
  }, [selectedNodeId, graphData?.edges]);

  return {
    graphData,
    stats: stats || graphData?.stats || null,
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
    baseFilteredNodes,
    edgeTypeCounts,
    loadGraph,
    generateGraph,
    fetchNodeContext,
  };
}
