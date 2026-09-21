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

  // 面板高度上限：永遠預留至少 280px 給上方工作區（頂欄 + 編輯區），
  // 避免拖太高把主要內容擠到消失。
  const getMaxDockHeight = () =>
    Math.min(800, Math.max(300, window.innerHeight - 280));

  // Freely adjustable dock height (persisted in localStorage)
  const [dockHeight, setDockHeight] = useState<number>(() => {
    const saved = localStorage.getItem('bottom_dock_height');
    const parsed = saved ? parseInt(saved, 10) : 220;
    if (isNaN(parsed) || parsed < 100) return 220;
    return Math.min(parsed, getMaxDockHeight());
  });
  const [isDragging, setIsDragging] = useState(false);

  const isDraggingRef = useRef(false);
  const startYRef = useRef(0);
  const startHeightRef = useRef(220);

  useEffect(() => {
    document.documentElement.style.setProperty('--bottom-dock-height', `${dockHeight}px`);
  }, [dockHeight]);

  // 使用 Pointer Events + setPointerCapture：
  // 按下後事件鎖定在手柄元素上，即使游標移出視窗或掠過其他元素也不會斷線，
  // 徹底避免 mousemove 被攔截 / 離開視窗即失效等問題。
  const handleResizerPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
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

    const el = e.currentTarget;
    try {
      el.setPointerCapture(e.pointerId);
    } catch {
      /* 某些環境不支援 capture，退回 window 事件仍可作用 */
    }

    const onPointerMove = (moveEvent: PointerEvent) => {
      if (!isDraggingRef.current) return;
      const deltaY = startYRef.current - moveEvent.clientY;
      const maxHeight = getMaxDockHeight();
      const newHeight = Math.max(100, Math.min(maxHeight, startHeightRef.current + deltaY));
      setDockHeight(newHeight);
      document.documentElement.style.setProperty('--bottom-dock-height', `${newHeight}px`);
      localStorage.setItem('bottom_dock_height', String(newHeight));
    };

    const onPointerUp = () => {
      isDraggingRef.current = false;
      setIsDragging(false);
      try {
        el.releasePointerCapture(e.pointerId);
      } catch {
        /* 已釋放或從未捕獲，忽略 */
      }
      el.removeEventListener('pointermove', onPointerMove);
      el.removeEventListener('pointerup', onPointerUp);
      el.removeEventListener('pointercancel', onPointerUp);
    };

    el.addEventListener('pointermove', onPointerMove);
    el.addEventListener('pointerup', onPointerUp);
    el.addEventListener('pointercancel', onPointerUp);
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
    // 高度變化不追底：縮放面板只改變可視範圍，不新增內容，無需捲動；
    // 拖曳中一律不搶捲動，避免跟手勢打架造成亂跳。
    if (isOpen && !isDraggingRef.current) {
      scrollToBottom();
    }
  }, [logs, isOpen, activeTab]);

  return (
    <footer
      className={`bottom-dock ${isOpen ? 'dock-open' : 'dock-collapsed'} ${isDragging ? 'dock-resizing' : ''}`}
      style={isOpen ? { height: `${dockHeight}px` } : undefined}
    >
      {/* Top Resizer Handle */}
      <div
        className="dock-resizer"
        onPointerDown={handleResizerPointerDown}
        data-dock-resizer="v3-pointer-capture"
        data-tooltip="拖曳以自由調整面板高度"
        data-tooltip-pos="bottom"
      >
        <div className="dock-resizer-line" />
      </div>

      <div className="dock-header" onClick={handleToggle}>
        <div className="dock-header-left">
          <IconTerminal size={14} className="text-muted" />
          <span
            className="dock-title"
            data-tooltip={isOpen ? '點擊收起執行日誌面板' : '點擊展開執行日誌面板'}
            data-tooltip-pos="bottom"
          >
            執行日誌與狀態 {logs.length > 0 && `(${logs.length})`}
          </span>
          {isOpen && (
            <div className="dock-tabs" onClick={(e) => e.stopPropagation()}>
              <button
                type="button"
                className={`dock-tab-btn ${activeTab === 'stream' ? 'active' : ''}`}
                onClick={() => setActiveTab('stream')}
                data-tooltip="即時串流日誌輸出"
                data-tooltip-pos="bottom"
              >
                串流日誌
              </button>
              {autoStatusText && (
                <button
                  type="button"
                  className={`dock-tab-btn ${activeTab === 'status' ? 'active' : ''}`}
                  onClick={() => setActiveTab('status')}
                  data-tooltip="自主寫作進度狀態"
                  data-tooltip-pos="bottom"
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
              data-tooltip="清除日誌"
              data-tooltip-pos="bottom"
            >
              <IconTrash size={12} />
              <span>清除</span>
            </button>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-xs text-muted"
            onClick={handleToggle}
            data-tooltip={isOpen ? '收起面板' : '展開面板'}
            data-tooltip-pos="bottom"
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
