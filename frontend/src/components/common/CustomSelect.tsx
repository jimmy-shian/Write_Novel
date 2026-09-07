import React, { useState, useRef, useEffect, useCallback } from 'react';

export interface SelectOption {
  value: string;
  label: string;
  subLabel?: string;
}

interface CustomSelectProps {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  id?: string;
}

export const CustomSelect: React.FC<CustomSelectProps> = ({
  value,
  options,
  onChange,
  placeholder = '請選擇...',
  className = '',
  disabled = false,
  id,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((opt) => opt.value === value);

  const handleToggle = useCallback(() => {
    if (!disabled) {
      setIsOpen((prev) => !prev);
    }
  }, [disabled]);

  const handleSelect = useCallback(
    (optValue: string) => {
      onChange(optValue);
      setIsOpen(false);
    },
    [onChange]
  );

  // Click outside listener (matching document reference)
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent | TouchEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('touchstart', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [isOpen]);

  // Keyboard accessibility
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;

    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setIsOpen((prev) => !prev);
    } else if (e.key === 'Escape') {
      setIsOpen(false);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
      } else {
        const currentIndex = options.findIndex((opt) => opt.value === value);
        const nextIndex = (currentIndex + 1) % options.length;
        if (options[nextIndex]) {
          onChange(options[nextIndex].value);
        }
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
      } else {
        const currentIndex = options.findIndex((opt) => opt.value === value);
        const prevIndex = (currentIndex - 1 + options.length) % options.length;
        if (options[prevIndex]) {
          onChange(options[prevIndex].value);
        }
      }
    }
  };

  return (
    <div
      ref={containerRef}
      id={id}
      className={`custom-select ${isOpen ? 'open' : ''} ${disabled ? 'disabled' : ''} ${className}`}
      onKeyDown={handleKeyDown}
    >
      <div
        className="select-trigger"
        onClick={handleToggle}
        tabIndex={disabled ? -1 : 0}
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        title={selectedOption ? `${selectedOption.label}${selectedOption.subLabel ? ` (${selectedOption.subLabel})` : ''}` : undefined}
      >
        <span className="select-trigger-text">
          {selectedOption ? (
            <>
              <span className="select-main-label marquee-on-hover">{selectedOption.label}</span>
              {selectedOption.subLabel && (
                <span className="select-sub-label"> ({selectedOption.subLabel})</span>
              )}
            </>
          ) : (
            <span className="select-placeholder">{placeholder}</span>
          )}
        </span>
        <div className="arrow" aria-hidden="true" />
      </div>

      <div className="select-options" role="listbox">
        {options.length === 0 ? (
          <div className="option empty-option">(無可用選項)</div>
        ) : (
          options.map((opt) => {
            const isSelected = opt.value === value;
            const fullTitle = `${opt.label}${opt.subLabel ? ` (${opt.subLabel})` : ''}`;
            return (
              <div
                key={opt.value}
                className={`option ${isSelected ? 'selected' : ''}`}
                onClick={() => handleSelect(opt.value)}
                role="option"
                aria-selected={isSelected}
                title={fullTitle}
              >
                <span className="option-label marquee-on-hover">{opt.label}</span>
                {opt.subLabel && (
                  <span className="option-sub-label">({opt.subLabel})</span>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};