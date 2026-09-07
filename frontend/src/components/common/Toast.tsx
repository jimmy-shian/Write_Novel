import React, { useState, useEffect } from 'react';
import { IconCheck, IconX, IconInfo } from './Icons';

export type ToastType = 'info' | 'success' | 'warning' | 'danger';

export interface ToastMessage {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

// Global listener for decoupled toast triggering without prop-drilling
type ToastListener = (toast: ToastMessage) => void;
const listeners: Set<ToastListener> = new Set();

export const showToast = (message: string, type: ToastType = 'info', duration: number = 3000) => {
  const toast: ToastMessage = {
    id: `${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
    message,
    type,
    duration,
  };
  listeners.forEach((fn) => fn(toast));
};

export const ToastContainer: React.FC = () => {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  useEffect(() => {
    const handleAddToast = (toast: ToastMessage) => {
      setToasts((prev) => [...prev, toast]);
      if (toast.duration && toast.duration > 0) {
        setTimeout(() => {
          setToasts((prev) => prev.filter((t) => t.id !== toast.id));
        }, toast.duration);
      }
    };

    listeners.add(handleAddToast);
    return () => {
      listeners.delete(handleAddToast);
    };
  }, []);

  const handleDismiss = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  if (toasts.length === 0) return null;

  return (
    <div className="toast-container" role="region" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast-item toast-${toast.type}`}>
          <span className="toast-icon">
            {toast.type === 'success' && <IconCheck size={14} />}
            {toast.type === 'danger' && <IconX size={14} />}
            {toast.type === 'warning' && <IconInfo size={14} />}
            {toast.type === 'info' && <IconInfo size={14} />}
          </span>
          <span className="toast-message">{toast.message}</span>
          <button
            type="button"
            className="toast-close-btn"
            onClick={() => handleDismiss(toast.id)}
            title="關閉"
          >
            <IconX size={12} />
          </button>
        </div>
      ))}
    </div>
  );
};
