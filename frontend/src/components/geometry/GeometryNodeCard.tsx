import React from 'react';
import { GeometryNodeDto } from '../../types/geometry';
import { Badge } from '../common/Badge';
import { StatusDot } from '../common/StatusDot';

interface GeometryNodeCardProps {
  node: GeometryNodeDto;
  isSelected: boolean;
  isHighlighted?: boolean;
  onClick: () => void;
}

export const GeometryNodeCard: React.FC<GeometryNodeCardProps> = ({
  node,
  isSelected,
  isHighlighted = false,
  onClick,
}) => {
  const hasSemantic = Boolean(node.semantic);

  const getRoleVariant = (role: string): 'neutral' | 'accent' | 'success' | 'danger' | 'warning' => {
    switch (role) {
      case 'OPEN_THREAD':
        return 'accent';
      case 'CONVERGE':
        return 'warning';
      case 'PAYOFF':
        return 'success';
      case 'CHARACTER_SHIFT':
      case 'RELATIONSHIP_CHANGE':
        return 'accent';
      case 'ECHO':
        return 'warning';
      default:
        return 'neutral';
    }
  };

  return (
    <div
      className={`geometry-node-card ${isSelected ? 'selected' : ''} ${
        isHighlighted ? 'highlighted' : ''
      }`}
      onClick={onClick}
      id={`geometry-node-${node.node_id}`}
    >
      <div className="geometry-node-card-top">
        <span className="geometry-node-id">{node.node_id}</span>
        <Badge variant={getRoleVariant(node.structural_role)} size="sm">
          {node.structural_role}
        </Badge>
      </div>

      <div className="geometry-node-card-meta">
        <span>第 {node.chapter_start}{node.chapter_end !== node.chapter_start ? `-${node.chapter_end}` : ''} 章</span>
        <span>線程: {node.primary_thread || '全域'}</span>
      </div>

      <div className="geometry-node-card-foot">
        <StatusDot
          status={hasSemantic ? 'success' : 'neutral'}
          size="sm"
          title={hasSemantic ? '已注入文學語義' : '空拓撲 (semantic = NULL)'}
        />
        <span className="text-xs text-[var(--text-muted)]">
          {hasSemantic ? '已注入語義' : '待填充語義'}
        </span>
      </div>
    </div>
  );
};
