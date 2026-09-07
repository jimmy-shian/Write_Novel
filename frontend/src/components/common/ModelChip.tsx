import React from 'react';
import { IconCpu } from './Icons';

interface ModelChipProps {
  modelName: string;
  isSelected?: boolean;
  onSelect?: (modelName: string) => void;
  className?: string;
}

export const ModelChip: React.FC<ModelChipProps> = ({
  modelName,
  isSelected = false,
  onSelect,
  className = '',
}) => {
  return (
    <button
      type="button"
      className={`model-chip ${isSelected ? 'selected' : ''} ${className}`}
      onClick={() => onSelect?.(modelName)}
    >
      <IconCpu size={12} />
      <span>{modelName}</span>
    </button>
  );
};
