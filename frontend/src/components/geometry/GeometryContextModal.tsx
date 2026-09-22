import React, { useEffect, useMemo, useRef, useState } from 'react';
import { GeometryNodeDto, NodeContextPackage } from '../../types/geometry';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { CopyCard } from '../common/CopyCard';
import { Badge } from '../common/Badge';

interface GeometryContextModalProps {
  isOpen: boolean;
  onClose: () => void;
  node: GeometryNodeDto | null;
  onFetchContext: (nodeId: string) => Promise<NodeContextPackage | null>;
}

// 模組級快取：同節點二次點開秒開，不再打後端全圖編譯
const contextCache = new Map<string, NodeContextPackage>();

export function getCachedGeometryContext(nodeId: string): NodeContextPackage | null {
  return contextCache.get(nodeId) ?? null;
}

export function setCachedGeometryContext(nodeId: string, pkg: NodeContextPackage): void {
  // 簡單 LRU：超過 100 個節點清掉最舊的，避免長篇常駐爆記憶體
  if (!contextCache.has(nodeId) && contextCache.size >= 100) {
    const oldest = contextCache.keys().next().value;
    if (oldest) contextCache.delete(oldest);
  }
  contextCache.set(nodeId, pkg);
}

export const GeometryContextModal: React.FC<GeometryContextModalProps> = ({
  isOpen,
  onClose,
  node,
  onFetchContext,
}) => {
  const [pkg, setPkg] = useState<NodeContextPackage | null>(null);
  const [loading, setLoading] = useState(false);
  const requestIdRef = useRef(0);

  const nodeId = node?.node_id ?? null;

  useEffect(() => {
    if (!isOpen || !nodeId) return;
    const cached = contextCache.get(nodeId);
    if (cached) {
      setPkg(cached);
      setLoading(false);
      return;
    }
    // 無快取：先顯示客戶端 fallback（秒開），再背景補上後端編譯結果
    setPkg(null);
    setLoading(true);
    const requestId = ++requestIdRef.current;
    let cancelled = false;
    onFetchContext(nodeId)
      .then((res) => {
        if (cancelled || requestIdRef.current !== requestId || !res) return;
        setCachedGeometryContext(nodeId, res);
        setPkg(res);
      })
      .catch(() => {
        // 保持 fallback 文案，不閃白
      })
      .finally(() => {
        if (!cancelled && requestIdRef.current === requestId) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, nodeId, onFetchContext]);

  const fallbackText = useMemo(() => {
    if (!node) return '';
    return `[幾何節點 ${node.node_id}] 結構角色: ${node.structural_role}，所屬章節: 第 ${node.chapter_start}-${node.chapter_end} 章`;
  }, [node]);

  const geometryOverlayText = useMemo(
    () => pkg?.geometry_overlay_text || fallbackText,
    [pkg, fallbackText]
  );
  const crossContextText = useMemo(() => pkg?.cross_context_text || '', [pkg]);

  if (!isOpen || !node) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`節點 ${node.node_id} 上下文約束與敘事義務`}
      subtitle={`第 ${node.chapter_start}-${node.chapter_end} 章 · 結構角色: ${node.structural_role}`}
      size="lg"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            關閉
          </Button>
        </div>
      }
    >
      <div className="space-y-4 text-xs">
        <div className="flex items-center gap-2">
          <span>結構角色定位：</span>
          <Badge variant="accent">{node.structural_role}</Badge>
          <span className="text-[var(--text-muted)]">
            （約束當前章節寫作職責，嚴防情節偏航）
          </span>
        </div>

        {/* Layer 3: Geometry Overlay — 有 fallback 秒開，載入中只在卡片上方顯示小提示，不整塊閃爍 */}
        <div className="space-y-2">
          <span className="font-bold text-sm text-[var(--text-primary)]">
            Layer 3: 幾何結構角色與敘事義務 (Geometry Overlay)
            {loading && (
              <span className="ml-2 font-normal text-[11px] text-[var(--text-muted)]">
                編譯中…
              </span>
            )}
          </span>
          <CopyCard
            label="提示詞覆蓋區塊 (點擊一鍵複製)"
            value={geometryOverlayText}
          />
        </div>

        {/* Layer 4: Cross-Relation Context */}
        {crossContextText ? (
          <div className="space-y-2">
            <span className="font-bold text-sm text-[var(--text-primary)]">
              Layer 4: 跨距線程交織與對照關聯 (Cross Context)
            </span>
            <CopyCard
              label="跨線合流與主題對比約束"
              value={crossContextText}
            />
          </div>
        ) : (
          loading && (
            <div className="p-4 text-center text-[var(--text-muted)]">
              編譯幾何結構義務與跨線約束中...
            </div>
          )
        )}
      </div>
    </Modal>
  );
};
