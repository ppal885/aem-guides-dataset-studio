import { useCallback, useEffect, useState } from 'react';

export type PanelResizeOptions = {
  storageKey: string;
  defaultWidth: number;
  minWidth: number;
  maxWidth: number;
  /** When true, dragging left increases width (handle on panel's left edge). */
  invertDelta?: boolean;
};

function readStoredWidth(key: string, fallback: number, min: number, max: number): number {
  try {
    const v = localStorage.getItem(key);
    if (v) {
      const n = parseInt(v, 10);
      if (n >= min && n <= max) return n;
    }
  } catch {
    /* ignore */
  }
  return fallback;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function useHorizontalPanelResize({
  storageKey,
  defaultWidth,
  minWidth,
  maxWidth,
  invertDelta = false,
}: PanelResizeOptions) {
  const [width, setWidth] = useState(() =>
    readStoredWidth(storageKey, defaultWidth, minWidth, maxWidth)
  );
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, String(width));
    } catch {
      /* ignore */
    }
  }, [storageKey, width]);

  const resetWidth = useCallback(() => {
    setWidth(defaultWidth);
  }, [defaultWidth]);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setDragging(true);
      const startX = e.clientX;
      const startWidth = width;

      const onMouseMove = (ev: MouseEvent) => {
        let delta = ev.clientX - startX;
        if (invertDelta) delta = -delta;
        setWidth(clamp(startWidth + delta, minWidth, maxWidth));
      };

      const onMouseUp = () => {
        setDragging(false);
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };

      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    },
    [width, minWidth, maxWidth, invertDelta]
  );

  return { width, dragging, onMouseDown, resetWidth, setWidth };
}
