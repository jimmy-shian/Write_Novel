import React, { useState } from 'react';
import { GeometryParams, GeometryComplexityLevel } from '../../types/geometry';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';

interface GeometryParamsModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialParams?: GeometryParams;
  onConfirm: (params: Partial<GeometryParams>) => void;
  isLoading?: boolean;
}

const COMPLEXITY_LEVELS: { id: GeometryComplexityLevel; label: string; desc: string }[] = [
  { id: 'SPARSE', label: '簡約 (SPARSE)', desc: '每章約 1.5 節點，主副線清晰' },
  { id: 'STANDARD', label: '標準 (STANDARD)', desc: '每章約 2.2 節點，標準多線節奏' },
  { id: 'DENSE', label: '高密度 (DENSE)', desc: '每章約 2.8 節點，強交織與高潮接續' },
  { id: 'VERY_DENSE', label: '極致交織 (VERY_DENSE)', desc: '每章約 3.5 節點，群像與多重伏筆' },
];

export const GeometryParamsModal: React.FC<GeometryParamsModalProps> = ({
  isOpen,
  onClose,
  initialParams,
  onConfirm,
  isLoading = false,
}) => {
  const [targetChapters, setTargetChapters] = useState(initialParams?.target_chapters || 800);
  const [volumeCount, setVolumeCount] = useState(initialParams?.volume_count || 16);
  const [complexity, setComplexity] = useState<string>(initialParams?.complexity || 'DENSE');
  const [mainThreadCount, setMainThreadCount] = useState(initialParams?.main_thread_count || 4);
  const [subplotCount, setSubplotCount] = useState(initialParams?.subplot_count || 12);
  const [characterArcCount, setCharacterArcCount] = useState(initialParams?.character_arc_count || 8);
  const [relationshipArcCount, setRelationshipArcCount] = useState(initialParams?.relationship_arc_count || 6);
  const [thematicThreadCount, setThematicThreadCount] = useState(initialParams?.thematic_thread_count || 4);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onConfirm({
      target_chapters: targetChapters,
      volume_count: volumeCount,
      complexity,
      main_thread_count: mainThreadCount,
      subplot_count: subplotCount,
      character_arc_count: characterArcCount,
      relationship_arc_count: relationshipArcCount,
      thematic_thread_count: thematicThreadCount,
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="敘事幾何拓撲參數設定"
      subtitle="手動微調長篇小說幾何骨架、線程密度與長距伏筆約束配置"
      size="md"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={isLoading}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} isLoading={isLoading}>
            套用並重新產生
          </Button>
        </div>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4 text-xs">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[var(--text-muted)] mb-1">目標全書章數：</label>
            <input
              type="number"
              min={10}
              max={3000}
              className="w-full p-2 rounded bg-[var(--surface-subtle)] border border-[var(--border)] text-xs text-[var(--text-primary)]"
              value={targetChapters}
              onChange={(e) => setTargetChapters(Number(e.target.value))}
            />
          </div>

          <div>
            <label className="block text-[var(--text-muted)] mb-1">規劃總篇卷數：</label>
            <input
              type="number"
              min={1}
              max={60}
              className="w-full p-2 rounded bg-[var(--surface-subtle)] border border-[var(--border)] text-xs text-[var(--text-primary)]"
              value={volumeCount}
              onChange={(e) => setVolumeCount(Number(e.target.value))}
            />
          </div>
        </div>

        <div>
          <label className="block text-[var(--text-muted)] mb-1">幾何複雜度 (Complexity)：</label>
          <div className="grid grid-cols-2 gap-2">
            {COMPLEXITY_LEVELS.map((lvl) => (
              <button
                key={lvl.id}
                type="button"
                className={`p-2.5 rounded border text-left transition-all ${
                  complexity === lvl.id
                    ? 'border-[var(--accent)] bg-[var(--accent-subtle)]'
                    : 'border-[var(--border)] bg-[var(--surface-subtle)] hover:border-[var(--accent)]'
                }`}
                onClick={() => setComplexity(lvl.id)}
              >
                <div className="font-semibold text-xs text-[var(--text-primary)]">{lvl.label}</div>
                <div className="text-[11px] text-[var(--text-muted)]">{lvl.desc}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="border-t border-[var(--border-subtle)] pt-3">
          <span className="block font-semibold mb-2 text-[var(--text-primary)]">線程數量配置 (Thread Counts)</span>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[var(--text-muted)] mb-1">主要線程 (Main Threads):</label>
              <input
                type="number"
                min={1}
                max={12}
                className="w-full p-2 rounded bg-[var(--surface-subtle)] border border-[var(--border)] text-xs text-[var(--text-primary)]"
                value={mainThreadCount}
                onChange={(e) => setMainThreadCount(Number(e.target.value))}
              />
            </div>

            <div>
              <label className="block text-[var(--text-muted)] mb-1">次要支線 (Subplots):</label>
              <input
                type="number"
                min={1}
                max={30}
                className="w-full p-2 rounded bg-[var(--surface-subtle)] border border-[var(--border)] text-xs text-[var(--text-primary)]"
                value={subplotCount}
                onChange={(e) => setSubplotCount(Number(e.target.value))}
              />
            </div>

            <div>
              <label className="block text-[var(--text-muted)] mb-1">角色成長弧 (Character Arcs):</label>
              <input
                type="number"
                min={1}
                max={20}
                className="w-full p-2 rounded bg-[var(--surface-subtle)] border border-[var(--border)] text-xs text-[var(--text-primary)]"
                value={characterArcCount}
                onChange={(e) => setCharacterArcCount(Number(e.target.value))}
              />
            </div>

            <div>
              <label className="block text-[var(--text-muted)] mb-1">人際關係線 (Relationship Arcs):</label>
              <input
                type="number"
                min={1}
                max={16}
                className="w-full p-2 rounded bg-[var(--surface-subtle)] border border-[var(--border)] text-xs text-[var(--text-primary)]"
                value={relationshipArcCount}
                onChange={(e) => setRelationshipArcCount(Number(e.target.value))}
              />
            </div>
          </div>
        </div>
      </form>
    </Modal>
  );
};
