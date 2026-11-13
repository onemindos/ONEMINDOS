// SPDX-License-Identifier: Apache-2.0
// Registers the service worker (public/sw.js) in a production build served over HTTPS or from
// localhost. Never in the demo (VITE_MOCK) or in development, where a cached shell would hide edits.
export function registerServiceWorker(enabled: boolean): void {
  if (!enabled || typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {
      /* the app works the same without it */
    });
  });
}
