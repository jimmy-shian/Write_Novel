import React, { useEffect, useState } from 'react';
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

export const GeometryContextModal: React.FC<GeometryContextModalProps> = ({
  isOpen,
  onClose,
  node,
  onFetchContext,
}) => {
  const [pkg, setPkg] = useState<NodeContextPackage | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !node) {
      setPkg(null);
      return;
    }
    let isMounted = true;
    setLoading(true);
    onFetchContext(node.node_id)
      .then((res) => {
        if (isMounted) setPkg(res);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, [isOpen, node, onFetchContext]);

  if (!isOpen || !node) return null;

  const fullPromptText = pkg
    ? `${pkg.geometry_overlay_text || ''}\n\n${pkg.cross_context_text || ''}`.trim()
    : `[幾何節點 ${node.node_id}] 結構角色: ${node.structural_role}，所屬章節: 第 ${node.chapter_start}-${node.chapter_end} 章`;

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

        {loading ? (
          <div className="p-8 text-center text-[var(--text-muted)]">
            編譯幾何結構義務與跨線約束中...
          </div>
        ) : (
          <>
            {/* Layer 3: Geometry Overlay */}
            <div className="space-y-2">
              <span className="font-bold text-sm text-[var(--text-primary)]">
                Layer 3: 幾何結構角色與敘事義務 (Geometry Overlay)
              </span>
              <CopyCard
                label="提示詞覆蓋區塊 (點擊一鍵複製)"
                value={pkg?.geometry_overlay_text || `結構角色: ${node.structural_role}`}
              />
            </div>

            {/* Layer 4: Cross-Relation Context */}
            {pkg?.cross_context_text && (
              <div className="space-y-2">
                <span className="font-bold text-sm text-[var(--text-primary)]">
                  Layer 4: 跨距線程交織與對照關聯 (Cross Context)
                </span>
                <CopyCard
                  label="跨線合流與主題對比約束"
                  value={pkg.cross_context_text}
                />
              </div>
            )}
          </>
        )}
      </div>
    </Modal>
  );
};
