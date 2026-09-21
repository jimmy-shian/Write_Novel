import React, { useEffect } from 'react';
import { IconX } from './Icons';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl';
  size?: 'sm' | 'md' | 'lg' | 'xl';
  closeOnOverlayClick?: boolean;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  subtitle,
  children,
  footer,
  maxWidth,
  size,
  closeOnOverlayClick = true,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

    const effectiveWidth = maxWidth || size;
    return (
      <div
        className="modal-overlay"
        onClick={closeOnOverlayClick ? onClose : undefined}
      >
        <div
          className={`modal-card ${effectiveWidth ? `modal-${effectiveWidth}` : ''}`}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="modal-header">
            <div>
              <h3 className="modal-title">{title}</h3>
              {subtitle && <div className="text-xs text-[var(--text-muted)] mt-0.5">{subtitle}</div>}
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-xs modal-close-btn"
              onClick={onClose}
              aria-label="關閉對話框"
            >
              <IconX size={16} />
            </button>
          </div>
          <div className="modal-body">{children}</div>
          {footer && <div className="modal-footer">{footer}</div>}
        </div>
      </div>
    );
};
