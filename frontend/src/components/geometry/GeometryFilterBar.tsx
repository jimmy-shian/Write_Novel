import React, { useState } from 'react';
import { GeometryVolumeDto, GeometryThreadDto } from '../../types/geometry';
import { CustomSelect, SelectOption } from '../common/CustomSelect';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';
import { ConfirmModal } from '../common/ConfirmModal';
import { IconRefresh, IconSettings, IconPlus } from '../common/Icons';

interface GeometryFilterBarProps {
  volumes: GeometryVolumeDto[];
  threads: GeometryThreadDto[];
  selectedVolumeIndex: number | 'all';
  onSelectVolume: (vol: number | 'all') => void;
  selectedThreadId: string | null;
  onSelectThread: (threadId: string | null) => void;
  selectedEdgeType: string | null;
  onSelectEdgeType: (edgeType: string | null) => void;
  onlyUnfilled: boolean;
  onToggleOnlyUnfilled: (val: boolean) => void;
  visibleCount: number;
  totalCount: number;
  visibleEdgeCount: number;
  totalEdgeCount: number;
  edgeCountByType?: Record<string, number>;
  nodeCountByType?: Record<string, number>;
  // 上方操作列合併（省一整行垂直高度）：由 Board 傳入
  loading?: boolean;
  hasGeometry?: boolean;
  onRefresh?: () => void;
  onOpenParams?: () => void;
  onRegenerate?: () => void;
}

const EDGE_TYPES = [
  { id: 'SETS_UP', label: '鋪設 (SETS_UP)' },
  { id: 'PAYS_OFF', label: '回收 (PAYS_OFF)' },
  { id: 'ECHOES', label: '呼應 (ECHOES)' },
  { id: 'CONVERGES', label: '合流 (CONVERGES)' },
  { id: 'CONTRASTS', label: '對比 (CONTRASTS)' },
  { id: 'CHARACTER_ARC', label: '角色弧光' },
  { id: 'RELATIONSHIP_CHANGE', label: '關係質變' },
];

export const GeometryFilterBar: React.FC<GeometryFilterBarProps> = ({
  volumes,
  threads,
  selectedVolumeIndex,
  onSelectVolume,
  selectedThreadId,
  onSelectThread,
  selectedEdgeType,
  onSelectEdgeType,
  onlyUnfilled,
  onToggleOnlyUnfilled,
  visibleCount,
  totalCount,
  visibleEdgeCount,
  totalEdgeCount,
  edgeCountByType = {},
  nodeCountByType = {},
  loading = false,
  hasGeometry = true,
  onRefresh,
  onOpenParams,
  onRegenerate,
}) => {
  const [showConfirmRegen, setShowConfirmRegen] = useState(false);
  const volumeOptions: SelectOption[] = [
    { value: 'all', label: '全部篇卷' },
    ...volumes.map((v) => ({
      value: String(v.volume_index),
      label: `第 ${v.volume_index} 卷`,
      subLabel: `第 ${v.chapter_start}-${v.chapter_end} 章`,
    })),
  ];

  const threadOptions: SelectOption[] = [
    { value: 'all', label: '全部線程' },
    ...threads.map((t) => ({
      value: t.thread_id,
      label: t.thread_id,
      subLabel: t.thread_type,
    })),
  ];

  // 邊類型改為下拉選單（原本 8 顆 Pill 太擠），每項帶「節點數 / 邊數」方便預覽篩選力度
  const edgeOptions: SelectOption[] = [
    {
      value: 'all',
      label: '全邊',
      subLabel: `${totalEdgeCount} 邊`,
    },
    ...EDGE_TYPES.map((et) => ({
      value: et.id,
      label: et.label,
      subLabel: `${nodeCountByType[et.id] ?? 0} 節點 · ${edgeCountByType[et.id] ?? 0} 邊`,
    })),
  ];

  return (
    <div className="geometry-filter-bar">
      <div className="geometry-filters-left">
        {/* 篇卷下拉選擇（使用 CustomSelect，套用 scaleY 動畫） */}
        <div className="geometry-filter-select-wrap">
          <CustomSelect
            value={selectedVolumeIndex === 'all' ? 'all' : String(selectedVolumeIndex)}
            options={volumeOptions}
            onChange={(val) => onSelectVolume(val === 'all' ? 'all' : Number(val))}
            placeholder="選擇篇卷..."
          />
        </div>

        {/* 線程篩選（使用 CustomSelect） */}
        <div className="geometry-filter-select-wrap">
          <CustomSelect
            value={selectedThreadId || 'all'}
            options={threadOptions}
            onChange={(val) => onSelectThread(val === 'all' ? null : val)}
            placeholder="篩選線程..."
          />
        </div>

        {/* 邊類型篩選（下拉選單，取代原本 8 顆 Pill，省橫向空間） */}
        <div className="geometry-filter-select-wrap geometry-filter-select-narrow">
          <CustomSelect
            value={selectedEdgeType || 'all'}
            options={edgeOptions}
            onChange={(val) => onSelectEdgeType(val === 'all' ? null : val)}
            placeholder="邊類型..."
          />
        </div>

        {/* 只看未填語義 Toggle */}
        <button
          type="button"
          className={`geometry-filter-pill-btn ${onlyUnfilled ? 'active' : ''}`}
          onClick={() => onToggleOnlyUnfilled(!onlyUnfilled)}
          title="只顯示 semantic 為空的待填充節點"
        >
          只看未填語義
        </button>
      </div>

      <div className="geometry-filter-counts" title={selectedEdgeType ? `已按邊類型 ${selectedEdgeType} 收斂節點（只保留有該類邊的節點）` : '未按邊類型收斂'}>
        顯示 <Badge variant="neutral" size="sm">{visibleCount} / {totalCount}</Badge> 個節點
        <span className="geometry-filter-counts-sep">·</span>
        <Badge variant="neutral" size="sm">{visibleEdgeCount} / {totalEdgeCount}</Badge> 條邊
      </div>

      {/* 右側：操作按鈕（與篩選列同一行，省垂直高度） */}
      {(onRefresh || onOpenParams || onRegenerate) && (
        <div className="geometry-filter-actions">
          {onRefresh && (
            <Button
              variant="secondary"
              size="sm"
              onClick={onRefresh}
              isLoading={loading}
              icon={<IconRefresh size={14} className={loading ? 'animate-spin' : ''} />}
              title="重新整理幾何骨架圖"
            >
              重新整理
            </Button>
          )}
          {onOpenParams && (
            <Button
              variant="secondary"
              size="sm"
              onClick={onOpenParams}
              icon={<IconSettings size={14} />}
              title="調整幾何骨架參數"
            >
              幾何參數
            </Button>
          )}
          {onRegenerate && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowConfirmRegen(true)}
              icon={<IconPlus size={14} />}
            >
              {hasGeometry ? '重新產生' : '產生結構圖'}
            </Button>
          )}
        </div>
      )}

      {showConfirmRegen && onRegenerate && (
        <ConfirmModal
          isOpen={showConfirmRegen}
          title="確定要重新產生幾何骨架圖？"
          message="重新產生將依據最新參數重構全書節點與 Motif 長距邊拓撲。既有的節點自訂語義將會被重置！"
          confirmText="確認重構"
          variant="danger"
          onClose={() => setShowConfirmRegen(false)}
          onConfirm={() => {
            setShowConfirmRegen(false);
            onRegenerate();
          }}
        />
      )}
    </div>
  );
};
