import React, { useLayoutEffect, useState, useEffect, useCallback } from 'react';
import { STAGE_GUIDE_STEPS } from './stageGuide';

interface StageGuideTourProps {
  open: boolean;
  step: number;
  onStepChange: (step: number) => void;
  onDone: () => void;
}

interface HighlightRect {
  x: number;
  y: number;
  w: number;
  h: number;
  found: boolean;
}

const PAD = 6;

export const StageGuideTour: React.FC<StageGuideTourProps> = ({
  open,
  step,
  onStepChange,
  onDone,
}) => {
  const total = STAGE_GUIDE_STEPS.length;
  const current = STAGE_GUIDE_STEPS[Math.min(step, total - 1)];
  const [rect, setRect] = useState<HighlightRect | null>(null);

  const measure = useCallback(() => {
    if (!current?.selector) {
      setRect(null);
      return;
    }
    const el = document.querySelector(current.selector) as HTMLElement | null;
    if (!el) {
      setRect(null);
      return;
    }
    try {
      el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } catch {
      /* 忽略 */
    }
    const r = el.getBoundingClientRect();
    setRect({
      x: Math.max(r.left - PAD, 4),
      y: Math.max(r.top - PAD, 4),
      w: Math.min(r.width + PAD * 2, window.innerWidth - 8),
      h: r.height + PAD * 2,
      found: true,
    });
  }, [current]);

  useLayoutEffect(() => {
    if (!open) return;
    measure();
  }, [open, step, measure]);

  useEffect(() => {
    if (!open) return;
    const onResize = () => measure();
    window.addEventListener('resize', onResize, true);
    window.addEventListener('scroll', onResize, true);
    return () => {
      window.removeEventListener('resize', onResize, true);
      window.removeEventListener('scroll', onResize, true);
    };
  }, [open, measure]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onDone();
      } else if (e.key === 'ArrowRight') {
        onStepChange(Math.min(step + 1, total - 1));
      } else if (e.key === 'ArrowLeft') {
        onStepChange(Math.max(step - 1, 0));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, step, total, onStepChange, onDone]);

  if (!open || !current) return null;

  const isLast = step === total - 1;
  const showRing = rect?.found;

  // Popover 位置：目標下方有空間就放下方，否則放上方，否則置中
  let popStyle: React.CSSProperties = {};
  if (showRing && rect) {
    const below = window.innerHeight - (rect.y + rect.h);
    if (below > 250) {
      popStyle = { left: Math.min(rect.x, window.innerWidth - 330), top: rect.y + rect.h + 10 };
    } else if (rect.y > 260) {
      popStyle = { left: Math.min(rect.x, window.innerWidth - 330), bottom: window.innerHeight - rect.y + 10 };
    } else {
      popStyle = { left: '50%', bottom: 24, transform: 'translateX(-50%)' };
    }
  }

  const goNext = () => {
    if (isLast) {
      onDone();
    } else {
      onStepChange(step + 1);
    }
  };

  return (
    <div className="stage-guide-root" role="dialog" aria-label="階段導覽">
      {/* 全屏阻擋層（吃掉背景點擊） */}
      <div className="stage-guide-catcher" onClick={(e) => e.stopPropagation()} />
      {/* 高亮鏤空環 */}
      {showRing && rect && (
        <div
          className="stage-guide-highlight"
          style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h }}
        />
      )}
      {/* 說明卡 */}
      <div
        className={`stage-guide-popover ${!showRing ? 'centered' : ''}`}
        style={showRing ? popStyle : undefined}
      >
        <div className="stage-guide-progress">
          <span>
            {step + 1} / {total}
          </span>
          <button type="button" className="stage-guide-skip" onClick={onDone}>
            跳過導覽
          </button>
        </div>
        <h4 className="stage-guide-title">{current.title}</h4>
        <p className="stage-guide-desc">{current.desc}</p>
        {current.tip && <p className="stage-guide-tip">{current.tip}</p>}
        <div className="stage-guide-actions">
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            onClick={() => onStepChange(Math.max(step - 1, 0))}
            disabled={step === 0}
          >
            上一步
          </button>
          <button type="button" className="btn btn-primary btn-xs" onClick={goNext}>
            {isLast ? '完成（不再自動顯示）' : '下一步'}
          </button>
        </div>
      </div>
    </div>
  );
};
