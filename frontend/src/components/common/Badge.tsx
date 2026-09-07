import React from 'react';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'neutral' | 'accent' | 'success' | 'danger';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  className = '',
}) => {
  const variantClass = variant !== 'neutral' ? variant : '';
  return <span className={`badge ${variantClass} ${className}`}>{children}</span>;
};
