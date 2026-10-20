import { useEffect, useMemo, useRef, type RefObject } from "react";

/* Ported from DeepSeek Harness (packages/client/ui-workspace/src/client/rows/
   Rows.tsx, MIT License, © 2026 DeepSeek). */

/** Overflow this small hides nothing worth reading; moving it reads as jitter. */
const MIN_TITLE_REVEAL_PX = 8;

/** Crawl speed: slow enough to read the text as it passes. */
const TITLE_MARQUEE_PX_PER_MS = 0.03;

/** Scroll the title and publish the fade-mask hooks `data-scrolled` (left fade)
 *  and `data-clipped` (right fade) that the row title styles read. */
function placeTitle(title: HTMLElement, left: number, range: number): void {
  if (typeof title.scrollTo === "function") title.scrollTo({ left, behavior: "instant" });
  else title.scrollLeft = left;
  if (left > 0) title.dataset.scrolled = "";
  else delete title.dataset.scrolled;
  if (left < range) title.dataset.clipped = "";
  else delete title.dataset.clipped;
}

function restTitle(title: HTMLElement): void {
  if (typeof title.scrollTo === "function") title.scrollTo({ left: 0, behavior: "instant" });
  else title.scrollLeft = 0;
  delete title.dataset.scrolled;
  delete title.dataset.clipped;
}

/**
 * Marquee a one-line title wider than its cell while its row is hovered: it
 * crawls at a constant speed until the far end is in view and rests there;
 * leaving snaps it back to the start. Reduced motion jumps straight to the end.
 * @returns pointer enter/leave handlers for the row.
 */
export function useTitleMarquee(title: RefObject<HTMLElement>): {
  enter: () => void;
  leave: () => void;
} {
  const frame = useRef(0);
  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  return useMemo(
    () => ({
      enter: () => {
        const el = title.current;
        if (!el) return;
        const range = el.scrollWidth - el.clientWidth;
        if (range <= MIN_TITLE_REVEAL_PX) return;
        if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
          placeTitle(el, range, range);
          return;
        }
        cancelAnimationFrame(frame.current);
        let previous: number | undefined;
        let position = 0;
        const step = (now: number) => {
          position += previous === undefined ? 0 : (now - previous) * TITLE_MARQUEE_PX_PER_MS;
          previous = now;
          placeTitle(el, Math.min(position, range), range);
          if (position < range) frame.current = requestAnimationFrame(step);
        };
        frame.current = requestAnimationFrame(step);
      },
      leave: () => {
        cancelAnimationFrame(frame.current);
        if (title.current) restTitle(title.current);
      },
    }),
    [title],
  );
}
