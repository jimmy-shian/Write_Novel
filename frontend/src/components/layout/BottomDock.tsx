import React, { useState, useRef, useEffect } from 'react';
import { IconTerminal, IconChevronLeft, IconChevronRight, IconTrash } from '../common/Icons';

interface BottomDockProps {
  logs: string[];
  autoStatusText?: string;
  onClearLogs?: () => void;
  isOpen?: boolean;
  onToggleOpen?: () => void;
}

export const BottomDock: React.FC<BottomDockProps> = ({
  logs,
  autoStatusText,
  onClearLogs,
  isOpen: controlledIsOpen,
  onToggleOpen,
}) => {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const isOpen = controlledIsOpen !== undefined ? controlledIsOpen : internalIsOpen;

  // Freely adjustable dock height (persisted in localStorage)
  const [dockHeight, setDockHeight] = useState<number>(() => {
    const saved = localStorage.getItem('bottom_dock_height');
    const parsed = saved ? parseInt(saved, 10) : 220;
    return parsed >= 100 && parsed <= 800 ? parsed : 220;
  });
  const [isDragging, setIsDragging] = useState(false);

  const isDraggingRef = useRef(false);
  const startYRef = useRef(0);
  const startHeightRef = useRef(220);

  useEffect(() => {
    document.documentElement.style.setProperty('--bottom-dock-height', `${dockHeight}px`);
  }, [dockHeight]);

  const handleMouseDownResizer = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();

    // If collapsed, open it
    if (!isOpen) {
      if (onToggleOpen) onToggleOpen();
      else setInternalIsOpen(true);
    }

    isDraggingRef.current = true;
    setIsDragging(true);
    startYRef.current = e.clientY;
    startHeightRef.current = dockHeight;

    const onMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const deltaY = startYRef.current - moveEvent.clientY;
      const maxHeight = Math.min(800, Math.floor(window.innerHeight * 0.85));
      const newHeight = Math.max(100, Math.min(maxHeight, startHeightRef.current + deltaY));
      setDockHeight(newHeight);
      document.documentElement.style.setProperty('--bottom-dock-height', `${newHeight}px`);
      localStorage.setItem('bottom_dock_height', String(newHeight));
    };

    const onMouseUp = () => {
      isDraggingRef.current = false;
      setIsDragging(false);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const handleToggle = () => {
    if (isDraggingRef.current) return;
    if (onToggleOpen) {
      onToggleOpen();
    } else {
      setInternalIsOpen((prev) => !prev);
    }
  };

  const [activeTab, setActiveTab] = useState<'stream' | 'status'>('stream');
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollBottomRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (scrollBottomRef.current) {
      scrollBottomRef.current.scrollIntoView({ behavior: 'auto', block: 'end' });
    } else if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [logs, isOpen, activeTab, dockHeight]);

  return (
    <footer
      className={`bottom-dock ${isOpen ? 'dock-open' : 'dock-collapsed'} ${isDragging ? 'dock-resizing' : ''}`}
      style={isOpen ? { height: `${dockHeight}px` } : undefined}
    >
      {/* Top Resizer Handle */}
      <div
        className="dock-resizer"
        onMouseDown={handleMouseDownResizer}
        title="拖曳以自由調整面板高度"
      >
        <div className="dock-resizer-line" />
      </div>

      <div className="dock-header" onClick={handleToggle}>
        <div className="dock-header-left">
          <IconTerminal size={14} className="text-muted" />
          <span className="dock-title">
            執行日誌與狀態 {logs.length > 0 && `(${logs.length})`}
          </span>
          {isOpen && (
            <div className="dock-tabs" onClick={(e) => e.stopPropagation()}>
              <button
                type="button"
                className={`dock-tab-btn ${activeTab === 'stream' ? 'active' : ''}`}
                onClick={() => setActiveTab('stream')}
              >
                串流日誌
              </button>
              {autoStatusText && (
                <button
                  type="button"
                  className={`dock-tab-btn ${activeTab === 'status' ? 'active' : ''}`}
                  onClick={() => setActiveTab('status')}
                >
                  自主進度
                </button>
              )}
            </div>
          )}
        </div>

        <div className="dock-header-right" onClick={(e) => e.stopPropagation()}>
          {isOpen && onClearLogs && (
            <button
              type="button"
              className="btn btn-ghost btn-xs text-muted"
              onClick={onClearLogs}
              title="清除日誌"
            >
              <IconTrash size={12} />
              <span>清除</span>
            </button>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-xs text-muted"
            onClick={handleToggle}
            title={isOpen ? '收起面板' : '展開面板'}
          >
            <span className="dock-toggle-label">{isOpen ? '收起' : '展開'}</span>
          </button>
        </div>
      </div>

      {isOpen && (
        <div className="dock-body" ref={scrollRef}>
          {activeTab === 'stream' ? (
            logs.length === 0 ? (
              <div className="dock-empty-hint">暫無日誌輸出。觸發 AI 生成或自主寫作時將即時顯示。</div>
            ) : (
              logs.map((log, index) => (
                <div key={index} className="dock-log-line">
                  {log}
                </div>
              ))
            )
          ) : (
            <div className="dock-status-container">
              <pre className="dock-status-pre">{autoStatusText || '暫無自主寫作進度'}</pre>
            </div>
          )}
          <div ref={scrollBottomRef} className="dock-scroll-anchor" />
        </div>
      )}
    </footer>
  );
};
