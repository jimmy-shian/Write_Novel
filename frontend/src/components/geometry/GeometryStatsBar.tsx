import React from 'react';
import { GeometryStats } from '../../types/geometry';
import { StatusDot } from '../common/StatusDot';

interface GeometryStatsBarProps {
  stats: GeometryStats | null;
  targetChapters?: number;
}

export const GeometryStatsBar: React.FC<GeometryStatsBarProps> = ({ stats, targetChapters = 800 }) => {
  if (!stats) return null;

  const progressPercent = Math.round((stats.filling_progress || 0) * 100);
  const density = targetChapters > 0 ? (stats.node_count / targetChapters).toFixed(2) : '0';

  return (
    <div className="geometry-stats-bar">
      <div className="geometry-stats-items">
        <div className="geometry-stat-item">
          <StatusDot status="success" size="sm" />
          <span>節點總數: <strong>{stats.node_count}</strong></span>
        </div>

        <div className="geometry-stat-item">
          <StatusDot status="warning" size="sm" />
          <span>結構邊: <strong>{stats.edge_count}</strong></span>
        </div>

        <div className="geometry-stat-item">
          <StatusDot status="neutral" size="sm" />
          <span>線程數: <strong>{stats.thread_count}</strong></span>
        </div>

        <div className="geometry-stat-item">
          <span>密度: <strong>{density}</strong> 節點/章</span>
        </div>
      </div>

      <div className="geometry-progress-wrap">
        <span className="geometry-stat-item">語義填充: <strong>{progressPercent}%</strong></span>
        <div className="geometry-progress-bar" title={`已填進度: ${progressPercent}%`}>
          <div
            className="geometry-progress-fill"
            style={{ '--fill-width': `${Math.min(100, Math.max(0, progressPercent))}%` } as React.CSSProperties}
          />
        </div>
      </div>
    </div>
  );
};
