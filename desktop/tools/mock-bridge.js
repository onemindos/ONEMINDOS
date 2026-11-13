// SPDX-License-Identifier: Apache-2.0
// Fixture stand-in for window.__TAURI__ so the popover can be previewed in a browser.
// Scenes: status, calm, down, pair-error, approval, approval-passkey, inbox.
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
      { id: 'e104c3e9', kind: 'app.install', target: 'home-assistant', requested_by: 'hermes', expires_at: '2026-11-20T00:00:00Z', risk: 'sensitive' },
    ],
    me: { id: 'person:owner', kind: 'person', role: 'owner', passkeys: 0, can_approve: true },
    // §12.14 inbox items (fixture values; links are dashboard paths, as the notify branch writes them).
    inbox: [
      { id: 'ntf_01', severity: 'critical', topic: 'backups', title: 'Backup failing', body: 'The USB disk is full. The last good backup is 26 hours old.', link: '/backups', action_id: null, created_at: new Date((now - 600) * 1000).toISOString(), read_at: null },
      { id: 'ntf_02', severity: 'info', topic: 'approvals', title: 'hermes asks to install home-assistant', body: '', link: '/approvals/e104c3e9', action_id: 'e104c3e9', created_at: new Date((now - 120) * 1000).toISOString(), read_at: null },
    ],
    updates: { nodes_reporting: 3, available: 1, security: false },
    backups: { health: 'verified', last_success_at: new Date((now - 3 * 3600) * 1000).toISOString() },
    fetched_at: now - 4,
  };
  const boxes = {
    status: [{ id: 'a1b2c3d4e5f6', name: 'Home box', url: 'https://onemind.local:8080', insecure: false, has_token: true, status }],
    calm: [{ id: 'a1b2c3d4e5f6', name: 'Home box', url: 'https://onemind.local:8080', insecure: false, has_token: true,
      status: { ...status, pending: [], inbox: [], updates: null, backups: null } }],
    down: [{ id: 'a1b2c3d4e5f6', name: 'Home box', url: 'http://onemind.local:8080', insecure: true, has_token: true,
      status: { ...status, reachable: false, error: 'unreachable', pending: [], fetched_at: now - 200 } }],
  }[scene] || [];
  if (!boxes.length && (scene.startsWith('approval') || scene === 'inbox')) boxes.push(...[{ id: 'a1b2c3d4e5f6', name: 'Home box', url: 'https://onemind.local:8443', insecure: false, has_token: true, live: true, status }]);
  if (scene === 'inbox' || scene === 'status') boxes.forEach((b) => (b.live = true));
  const passkey = scene === 'approval-passkey';
  const detail = {
    box_id: 'a1b2c3d4e5f6', id: 'e104c3e9', kind: passkey ? 'backup.restore' : 'app.install', state: 'awaiting_approval',
    risk: passkey ? 'destructive' : 'sensitive', target: passkey ? 'vaultwarden' : 'home-assistant',
    requested_by: 'agent:hermes-agent', requester_kind: 'agent',
    reason: passkey ? 'Vaultwarden data looks corrupted since 02:00.' : 'You asked for smart-home control; Home Assistant is the app for it.',
    expires_at: new Date((now + 20 * 3600) * 1000).toISOString(),
    params: passkey ? { snapshot_id: 'snap_01JC', scope: { app_id: 'vaultwarden' }, mode: 'portable', target: 'in_place' } : { app_id: 'home-assistant', version: '2026.11.1' },
    plan: passkey
      ? { summary: 'Restore vaultwarden from the 01:00 snapshot, in place.', warnings: ['Vaultwarden is down for about 1 minute.', 'Changes since 01:00 are lost.'], images: [], volumes: 1, nodes: ['3f9c2a1b7d4e'], objects: 4 }
      : { summary: 'Install Home Assistant 2026.11.1 on the hub.', warnings: [], images: ['ghcr.io/home-assistant/home-assistant:2026.11.1'], volumes: 1, nodes: ['3f9c2a1b7d4e'], objects: 6 },
    plan_sha256: 'sha256:9a1e5c0d7b3f2e8a4c6d1b0f9e7a5c3d',
    passkey: passkey ? 'risk' : null,
  };
  const inboxAll = [...status.inbox, { id: 'ntf_00', severity: 'warning', topic: 'updates', title: 'Security update ready', body: 'OneMind OS 0.1.20261112 fixes 2 issues.', link: '/updates', action_id: null, created_at: new Date((now - 86400) * 1000).toISOString(), read_at: new Date((now - 80000) * 1000).toISOString() }];
  const found = [{ name: 'Home box', url: 'http://onemind.local:8080', instance_id: 'demo', via: 'mdns' }];
  const handlers = {
    list_boxes: () => boxes,
    discover: () => new Promise((r) => setTimeout(() => r(found), 300)),
    pair: () => Promise.reject(scene === 'pair-error' ? 'unauthorized' : 'needs_https'),
    approval: () => detail,
    decide: ({ decision }) => (decision === 'deny' ? { outcome: 'done', state: 'denied', approval: null } : { outcome: 'done', state: 'accepted', approval: 'token' }),
    inbox: () => inboxAll,
    inbox_read: () => null,
    open_link: () => null,
    open_approvals: () => null,
  };
  window.__TAURI__ = {
    core: { invoke: async (cmd, args) => (handlers[cmd] ? handlers[cmd](args) : null) },
    event: { listen: async () => () => {} },
  };
  if (scene.startsWith('approval') || scene === 'inbox') {
    // Open the card or the inbox the way a click would.
    window.addEventListener('load', () => setTimeout(() => {
      const label = scene === 'inbox' ? 'See all notifications' : 'Review';
      [...document.querySelectorAll('button')].find((b) => b.textContent === label)?.click();
    }, 500));
  }
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
