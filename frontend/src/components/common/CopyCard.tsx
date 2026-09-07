import React, { useState } from 'react';
import { copyToClipboard } from '../../utils/clipboard';
import { IconCopy, IconCheck } from './Icons';

interface CopyCardProps {
  label: string;
  value: string;
  hint?: string;
  className?: string;
}

export const CopyCard: React.FC<CopyCardProps> = ({
  label,
  value,
  hint = '點擊複製',
  className = '',
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const success = await copyToClipboard(value);
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div
      className={`copy-card ${className}`}
      onClick={handleCopy}
      role="button"
      tabIndex={0}
      title="點擊複製到剪貼簿"
    >
      <div className="copy-card-info">
        <span className="copy-card-key">{label}</span>
        <span className="copy-card-val">{value}</span>
      </div>
      <div className="copy-card-action">
        {copied ? (
          <span className="copy-card-copied">
            <IconCheck size={14} className="text-success" />
            <span className="copy-card-hint">已複製</span>
          </span>
        ) : (
          <span className="copy-card-normal">
            <IconCopy size={14} className="text-muted" />
            <span className="copy-card-hint">{hint}</span>
          </span>
        )}
      </div>
    </div>
  );
};
