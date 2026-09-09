import React, { useState } from 'react';
import { DirectorMessageItemProps } from './types';
import { Badge } from '../common/Badge';
import { IconCopy, IconCheck, IconSparkles, IconChevronDown, IconTrash } from '../common/Icons';
import { formatTaiwanTime } from '../../utils/time';

export const DirectorMessageItem: React.FC<DirectorMessageItemProps> = ({ record, onCopy, onDelete }) => {
  const [copied, setCopied] = useState(false);
  const [isThinkingOpen, setIsThinkingOpen] = useState(false);

  const handleCopy = () => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(record.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    }
    onCopy?.(record.content);
  };

  // Determine badge label and variant
  let badgeLabel = '創作訊息';
  let badgeVariant: 'accent' | 'neutral' | 'success' | 'danger' = 'neutral';

  if (record.message_type === 'director' || record.role === 'director' || (record.content && record.content.includes('【總監'))) {
    badgeLabel = '總監評斷';
    badgeVariant = 'accent';
  } else if (record.message_type === 'pipeline') {
    badgeLabel = '創作指令';
    badgeVariant = 'neutral';
  } else if (record.role === 'user') {
    badgeLabel = '導演引導';
    badgeVariant = 'accent';
  } else if (record.role === 'system' || (record.content && record.content.includes('【系統通報】'))) {
    badgeLabel = '系統通知';
    badgeVariant = 'danger';
  } else if (record.role === 'assistant') {
    badgeLabel = 'AI 回答';
    badgeVariant = 'neutral';
  }

  return (
    <div className={`copilot-message-card message-type-${record.message_type || 'chat'}`}>
      <div className="message-card-header">
        <div className="message-card-meta">
          <Badge variant={badgeVariant}>{badgeLabel}</Badge>
          <span className="message-card-time">{formatTaiwanTime(record.timestamp)}</span>
        </div>
        <div className="message-card-actions" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <button
            type="button"
            className="btn btn-ghost btn-xs message-copy-btn"
            onClick={handleCopy}
            title="複製內文"
          >
            {copied ? <IconCheck size={12} className="text-success" /> : <IconCopy size={12} />}
          </button>
          {onDelete && record.id !== undefined && (
            <button
              type="button"
              className="btn btn-ghost btn-xs message-delete-btn text-muted"
              onClick={() => {
                if (window.confirm('確定要刪除此則對話紀錄嗎？')) {
                  onDelete(record.id!);
                }
              }}
              title="刪除此則紀錄"
            >
              <IconTrash size={12} />
            </button>
          )}
        </div>
      </div>

      {record.thinking && (
        <div className={`message-thinking-wrapper ${isThinkingOpen ? 'open' : ''}`}>
          <button
            type="button"
            className="thinking-toggle-trigger"
            onClick={() => setIsThinkingOpen(!isThinkingOpen)}
          >
            <div className="thinking-trigger-left">
              <IconSparkles size={12} className="text-accent" />
              <span>AI 思考推理歷程</span>
            </div>
            <div className="thinking-arrow">
              <IconChevronDown size={12} />
            </div>
          </button>
          <div className="thinking-expand-content">
            <div className="thinking-inner-text">{record.thinking}</div>
          </div>
        </div>
      )}

      <div className="message-card-content">
        {record.content}
      </div>
    </div>
  );
};
