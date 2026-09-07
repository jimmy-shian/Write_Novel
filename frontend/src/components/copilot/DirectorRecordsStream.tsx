import React, { useState, useMemo, useRef, useEffect } from 'react';
import { DirectorRecordsStreamProps, RecordFilterType } from './types';
import { DirectorMessageItem } from './DirectorMessageItem';
import { Button } from '../common/Button';
import { IconRefresh, IconTrash, IconMessageSquare } from '../common/Icons';

export const DirectorRecordsStream: React.FC<DirectorRecordsStreamProps> = ({
  records,
  isLoading,
  onRefresh,
  onClear,
}) => {
  const [filter, setFilter] = useState<RecordFilterType>('all');
  const bottomRef = useRef<HTMLDivElement>(null);

  const filteredRecords = useMemo(() => {
    if (!records || records.length === 0) return [];
    if (filter === 'all') return records;
    if (filter === 'director') {
      return records.filter(
        (r) =>
          r.message_type === 'director' ||
          r.role === 'director' ||
          (r.content && r.content.includes('【總監'))
      );
    }
    if (filter === 'pipeline') {
      return records.filter(
        (r) =>
          r.message_type === 'pipeline' ||
          (r.content && (r.content.includes('自主寫作') || r.content.includes('章節') || r.content.includes('骨架')))
      );
    }
    if (filter === 'system') {
      return records.filter(
        (r) => r.role === 'system' || (r.content && r.content.includes('【系統通報】'))
      );
    }
    return records;
  }, [records, filter]);

  // Counts for filter pills
  const counts = useMemo(() => {
    if (!records) return { all: 0, director: 0, pipeline: 0, system: 0 };
    return {
      all: records.length,
      director: records.filter(
        (r) =>
          r.message_type === 'director' ||
          r.role === 'director' ||
          (r.content && r.content.includes('【總監'))
      ).length,
      pipeline: records.filter(
        (r) =>
          r.message_type === 'pipeline' ||
          (r.content && (r.content.includes('自主寫作') || r.content.includes('章節') || r.content.includes('骨架')))
      ).length,
      system: records.filter(
        (r) => r.role === 'system' || (r.content && r.content.includes('【系統通報】'))
      ).length,
    };
  }, [records]);

  // Scroll to bottom when records length changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [records.length]);

  return (
    <div className="copilot-records-container">
      {/* Toolbar: Filters & Actions */}
      <div className="copilot-records-toolbar">
        <div className="copilot-records-filters">
          <button
            type="button"
            className={`filter-pill-btn ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            全部 ({counts.all})
          </button>
          <button
            type="button"
            className={`filter-pill-btn ${filter === 'director' ? 'active' : ''}`}
            onClick={() => setFilter('director')}
          >
            總監評斷 ({counts.director})
          </button>
          <button
            type="button"
            className={`filter-pill-btn ${filter === 'pipeline' ? 'active' : ''}`}
            onClick={() => setFilter('pipeline')}
          >
            創作指令 ({counts.pipeline})
          </button>
          {counts.system > 0 && (
            <button
              type="button"
              className={`filter-pill-btn ${filter === 'system' ? 'active' : ''}`}
              onClick={() => setFilter('system')}
            >
              系統 ({counts.system})
            </button>
          )}
        </div>

        <div className="copilot-records-actions">
          <Button
            variant="ghost"
            size="xs"
            onClick={onRefresh}
            isLoading={isLoading}
            icon={<IconRefresh size={12} />}
            title="從資料庫重新整理最新紀錄"
          >
            重新整理
          </Button>
          <Button
            variant="ghost"
            size="xs"
            onClick={onClear}
            icon={<IconTrash size={12} />}
            title="清空對話紀錄"
          >
            清空
          </Button>
        </div>
      </div>

      {/* Messages Stream */}
      <div className="copilot-records-stream">
        {filteredRecords.length === 0 ? (
          <div className="copilot-records-empty">
            <IconMessageSquare size={24} className="text-muted" />
            <p>目前尚無符合篩選條件的總監評斷或指令紀錄</p>
            <span className="empty-subtext">執行寫作或審閱時，總監的通報、評斷與指令將即時儲存並在此列出。</span>
          </div>
        ) : (
          filteredRecords.map((rec, idx) => (
            <DirectorMessageItem key={rec.id ?? idx} record={rec} />
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};
