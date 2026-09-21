import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

/**
 * GlobalTooltip — 全域自訂 tooltip，行為對齊原生 title：
 *
 * 1. 事件委派：在 document 上監聽 mouseover / focusin，任何掛有
 *    data-tooltip 的元素（含動態渲染）都會自動生效，不需逐處接線。
 * 2. Portal 到 document.body + position: fixed：
 *    tooltip 不再是觸發元素的偽元素子節點，因此：
 *    - 不會被任何祖先的 overflow: hidden / auto / scroll 裁切
 *    - 不受祖先堆疊上下文（z-index / transform / filter）壓蓋
 * 3. 視窗邊界翻轉與夾限：預設方向放不下時自動翻到對側，
 *    並夾在視窗安全區內，永不超出螢幕。
 *
 * 既有標記完全相容：
 *    data-tooltip="提示文字"
 *    data-tooltip-pos="top | bottom | left | right"（預設 top）
 * 支援 "\n" 換行（white-space: pre-line）。
 */

type TooltipPos = 'top' | 'bottom' | 'left' | 'right';

const GAP = 8; // tooltip 與觸發元素的間距
const VIEWPORT_PAD = 8; // 距視窗邊緣的安全距離
const SHOW_DELAY_MS = 250; // 與舊版 CSS transition-delay 一致

interface TipContent {
  text: string;
  pos: TooltipPos;
}

interface TipPlacement {
  x: number;
  y: number;
  pos: TooltipPos;
}

function readPos(el: Element): TooltipPos {
  const v = el.getAttribute('data-tooltip-pos');
  return v === 'bottom' || v === 'left' || v === 'right' ? v : 'top';
}

export function GlobalTooltip() {
  const [tip, setTip] = useState<TipContent | null>(null);
  const [placement, setPlacement] = useState<TipPlacement | null>(null);
  const [visible, setVisible] = useState(false);

  const targetRef = useRef<HTMLElement | null>(null);
  const tipNodeRef = useRef<HTMLDivElement | null>(null);
  const timerRef = useRef<number | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const hide = useCallback(() => {
    clearTimer();
    targetRef.current = null;
    setVisible(false);
    setTip(null);
    setPlacement(null);
  }, [clearTimer]);

  const scheduleShow = useCallback(
    (el: HTMLElement) => {
      const text = el.getAttribute('data-tooltip');
      if (!text) {
        hide();
        return;
      }
      clearTimer();
      targetRef.current = el;
      setTip({ text, pos: readPos(el) });
      setVisible(false); // 先隱藏，待 useLayoutEffect 量測後定位再顯示
      timerRef.current = window.setTimeout(() => setVisible(true), SHOW_DELAY_MS);
    },
    [clearTimer, hide],
  );

  // 事件委派（掛在 document，capture 以涵蓋 stopPropagation 的子樹）
  useEffect(() => {
    const findTarget = (node: EventTarget | null): HTMLElement | null => {
      if (!(node instanceof Element)) return null;
      const el = node.closest?.('[data-tooltip]') as HTMLElement | null;
      return el && el.getAttribute('data-tooltip') ? el : null;
    };

    const onOver = (e: MouseEvent) => {
      const el = findTarget(e.target);
      if (!el) return;
      // 已在追蹤同一元素（例如移入其子節點）則不重排
      if (targetRef.current === el && (tip || timerRef.current !== null)) return;
      scheduleShow(el);
    };
    const onOut = (e: MouseEvent) => {
      if (!targetRef.current) return;
      const related = e.relatedTarget as Element | null;
      if (!related || !related.contains || !targetRef.current.contains(related)) {
        if (related && related.closest?.('[data-tooltip]') === targetRef.current) return;
        hide();
      }
    };
    const onFocusIn = (e: FocusEvent) => {
      const el = findTarget(e.target);
      if (el) scheduleShow(el);
    };
    const onFocusOut = () => {
      if (targetRef.current) hide();
    };
    const onDown = () => {
      if (targetRef.current) hide(); // 按下即隱藏，貼近原生行為
    };
    const onScroll = (e: Event) => {
      // position: fixed 不隨內部捲動移動，捲動時直接隱藏（原生亦如此）
      if (targetRef.current && e.target instanceof Node) hide();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') hide();
    };
    const onBlurWin = () => hide();

    document.addEventListener('mouseover', onOver, true);
    document.addEventListener('mouseout', onOut, true);
    document.addEventListener('focusin', onFocusIn, true);
    document.addEventListener('focusout', onFocusOut, true);
    document.addEventListener('mousedown', onDown, true);
    document.addEventListener('scroll', onScroll, true);
    document.addEventListener('keydown', onKey);
    window.addEventListener('blur', onBlurWin);
    return () => {
      document.removeEventListener('mouseover', onOver, true);
      document.removeEventListener('mouseout', onOut, true);
      document.removeEventListener('focusin', onFocusIn, true);
      document.removeEventListener('focusout', onFocusOut, true);
      document.removeEventListener('mousedown', onDown, true);
      document.removeEventListener('scroll', onScroll, true);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('blur', onBlurWin);
    };
  }, [hide, scheduleShow, tip]);

  // 量測 + 定位（含翻轉與視窗夾限）
  useLayoutEffect(() => {
    if (!tip) return;
    const el = targetRef.current;
    const node = tipNodeRef.current;
    if (!el || !node) return;

    const r = el.getBoundingClientRect();
    const tw = node.offsetWidth;
    const th = node.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let pos = tip.pos;
    // 空間不足時翻到對側
    if (pos === 'top' && r.top - th - GAP < VIEWPORT_PAD && r.bottom + th + GAP <= vh - VIEWPORT_PAD) pos = 'bottom';
    else if (pos === 'bottom' && r.bottom + th + GAP > vh - VIEWPORT_PAD && r.top - th - GAP >= VIEWPORT_PAD) pos = 'top';
    else if (pos === 'right' && r.right + tw + GAP > vw - VIEWPORT_PAD && r.left - tw - GAP >= VIEWPORT_PAD) pos = 'left';
    else if (pos === 'left' && r.left - tw - GAP < VIEWPORT_PAD && r.right + tw + GAP <= vw - VIEWPORT_PAD) pos = 'right';

    let x: number;
    let y: number;
    if (pos === 'top' || pos === 'bottom') {
      const cx = r.left + r.width / 2;
      x = Math.min(Math.max(cx, tw / 2 + VIEWPORT_PAD), vw - tw / 2 - VIEWPORT_PAD);
      y = pos === 'top' ? r.top - GAP : r.bottom + GAP;
    } else {
      const cy = r.top + r.height / 2;
      y = Math.min(Math.max(cy, th / 2 + VIEWPORT_PAD), vh - th / 2 - VIEWPORT_PAD);
      x = pos === 'left' ? r.left - GAP : r.right + GAP;
    }
    setPlacement({ x, y, pos });
  }, [tip]);

  if (!tip || typeof document === 'undefined') return null;

  const transform =
    placement?.pos === 'bottom'
      ? 'translate(-50%, 0)'
      : placement?.pos === 'top'
        ? 'translate(-50%, -100%)'
        : placement?.pos === 'left'
          ? 'translate(-100%, -50%)'
          : 'translate(0, -50%)';

  return createPortal(
    <div
      ref={tipNodeRef}
      role="tooltip"
      className={`global-tooltip${visible && placement ? ' global-tooltip-visible' : ''}`}
      style={
        placement
          ? { left: placement.x, top: placement.y, transform }
          : { left: -9999, top: -9999, visibility: 'hidden' }
      }
    >
      {tip.text}
    </div>,
    document.body,
  );
}

export default GlobalTooltip;