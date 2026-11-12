// SPDX-License-Identifier: Apache-2.0
// Fixture stand-in for window.__TAURI__ so the popover can be previewed in a browser.
// The status fixture uses the shape the Rust core returned from a local dev gateway
// (pending action requested by the Hermes agent); nodes, updates and backups are fixture
// values, because a dev gateway without NATS reports no nodes and the update and backup
// routes are not served yet.
(() => {
  const q = new URLSearchParams(location.search);
  const scene = q.get('scene') || 'status';
  if (q.get('theme')) document.documentElement.dataset.theme = q.get('theme');
  // Same size as the tray window (tauri.conf.json), whatever the browser window is.
  const frame = document.createElement('style');
  frame.textContent = 'html,body{width:380px;height:640px;overflow:hidden} .shell{height:640px}';
  document.head.append(frame);
  const now = Math.floor(Date.now() / 1000);
  const status = {
    box_id: 'a1b2c3d4e5f6', reachable: true, error: null, name: 'Home box', version: '0.1.0',
    nodes_total: 3, nodes_online: 3,
    pending: [
      { id: 'e104c3e9', kind: 'app.install', target: 'home-assistant', requested_by: 'hermes', expires_at: '2026-11-20T00:00:00Z' },
    ],
    updates: { nodes_reporting: 3, available: 1, security: false },
    backups: { health: 'verified', last_success_at: new Date((now - 3 * 3600) * 1000).toISOString() },
    fetched_at: now - 4,
  };
  const boxes = {
    status: [{ id: 'a1b2c3d4e5f6', name: 'Home box', url: 'https://onemind.local:8080', insecure: false, has_token: true, status }],
    calm: [{ id: 'a1b2c3d4e5f6', name: 'Home box', url: 'https://onemind.local:8080', insecure: false, has_token: true,
      status: { ...status, pending: [], updates: null, backups: null } }],
    down: [{ id: 'a1b2c3d4e5f6', name: 'Home box', url: 'http://onemind.local:8080', insecure: true, has_token: true,
      status: { ...status, reachable: false, error: 'unreachable', pending: [], fetched_at: now - 200 } }],
  }[scene] || [];
  const found = [{ name: 'Home box', url: 'http://onemind.local:8080', instance_id: 'demo', via: 'mdns' }];
  const handlers = {
    list_boxes: () => boxes,
    discover: () => new Promise((r) => setTimeout(() => r(found), 300)),
    pair: () => Promise.reject(scene === 'pair-error' ? 'unauthorized' : 'needs_https'),
  };
  window.__TAURI__ = {
    core: { invoke: async (cmd, args) => (handlers[cmd] ? handlers[cmd](args) : null) },
    event: { listen: async () => () => {} },
  };
  if (scene === 'pair-error') {
    // After load, type a token and press Pair so the error state is visible.
    window.addEventListener('load', () => setTimeout(() => {
      const inputs = document.querySelectorAll('input');
      const tok = [...inputs].find((i) => i.type === 'password');
      if (tok) { tok.value = 'x'; tok.dispatchEvent(new Event('input')); }
      [...document.querySelectorAll('button')].find((b) => b.textContent === 'Pair')?.click();
      setTimeout(() => { const m = document.getElementById('view'); m.scrollTop = m.scrollHeight; }, 300);
    }, 700));
  }
})();
