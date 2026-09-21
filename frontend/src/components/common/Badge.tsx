import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'neutral' | 'accent' | 'success' | 'danger' | 'warning';
  size?: 'sm' | 'md';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  size = 'md',
  className = '',
}) => {
  const variantClass = variant !== 'neutral' ? variant : '';
  const sizeClass = size === 'sm' ? 'badge-sm' : '';
  return <span className={`badge ${variantClass} ${sizeClass} ${className}`}>{children}</span>;
};
