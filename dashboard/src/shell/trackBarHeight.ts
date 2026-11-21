// SPDX-License-Identifier: Apache-2.0
// Track an element's height into a CSS variable without a ResizeObserver loop error.
//
// Why: a ResizeObserver callback that changes layout (setting a CSS variable the page's grid uses)
// makes the browser deliver new notifications in the same frame. WebKit then raises "ResizeObserver
// loop completed with undelivered notifications" as a page error. The fix is to do the write in the
// next animation frame (outside the observer's delivery), once per frame, and only when the value changed.
export function trackBarHeight(bar: HTMLElement, root: HTMLElement, variable: string): () => void {
  if (typeof ResizeObserver === 'undefined') return () => {};
  let frame = 0;
  let last = '';
  const write = () => {
    frame = 0;
    const next = `${bar.offsetHeight}px`;
    if (next === last) return;
    last = next;
    root.style.setProperty(variable, next);
  };
  const ro = new ResizeObserver(() => {
    if (frame) cancelAnimationFrame(frame);
    frame = requestAnimationFrame(write);
  });
  ro.observe(bar);
  return () => {
    ro.disconnect();
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
  };
}
