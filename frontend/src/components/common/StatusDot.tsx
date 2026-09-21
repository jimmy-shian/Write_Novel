import React from 'react';

export interface StatusDotProps {
  status?: 'success' | 'warning' | 'danger' | 'neutral';
  size?: 'sm' | 'md';
  title?: string;
  className?: string;
}

export const StatusDot: React.FC<StatusDotProps> = ({
  status = 'neutral',
  size = 'md',
  title,
  className = '',
}) => {
  const sizeClass = size === 'sm' ? 'dot-sm' : '';
  return <span className={`status-dot ${status} ${sizeClass} ${className}`} title={title} />;
};
