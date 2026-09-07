import React from 'react';

interface StatusDotProps {
  status?: 'success' | 'warning' | 'danger' | 'neutral';
  title?: string;
  className?: string;
}

export const StatusDot: React.FC<StatusDotProps> = ({
  status = 'neutral',
  title,
  className = '',
}) => {
  return <span className={`status-dot ${status} ${className}`} title={title} />;
};
