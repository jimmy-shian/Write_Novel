import React, { useState } from 'react';
import { GeometryGraphResponse } from '../../types/geometry';
import { Button } from '../common/Button';
import { ConfirmModal } from '../common/ConfirmModal';
import { IconRefresh, IconSettings, IconPlus } from '../common/Icons';

interface GeometryHeaderProps {
  data: GeometryGraphResponse | null;
  selectedVolumeIndex: number | 'all';
  loading: boolean;
  onRefresh: () => void;
  onOpenParams: () => void;
  onRegenerate: () => void;
}

export const GeometryHeader: React.FC<GeometryHeaderProps> = ({
  data,
  selectedVolumeIndex,
  loading,
  onRefresh,
  onOpenParams,
  onRegenerate,
}) => {
  const [showConfirmRegen, setShowConfirmRegen] = useState(false);

  return (
    <div className="graph-board-header compact" aria-label="幾何骨架操作列">
      <div className="graph-board-actions">
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

        <Button
          variant="secondary"
          size="sm"
          onClick={onOpenParams}
          icon={<IconSettings size={14} />}
          title="調整幾何骨架參數"
        >
          幾何參數
        </Button>

        <Button
          variant="primary"
          size="sm"
          onClick={() => setShowConfirmRegen(true)}
          icon={<IconPlus size={14} />}
        >
          {data?.has_geometry ? '重新產生' : '產生結構圖'}
        </Button>
      </div>

      {showConfirmRegen && (
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
