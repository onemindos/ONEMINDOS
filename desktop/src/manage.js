// SPDX-License-Identifier: Apache-2.0
// Pure helpers for the Manage view (app lifecycle §12.40, backups §12.12, first-run settings §12.41).
// No DOM and no Tauri here, so `node --test` can check them. Everything the tray sends is a REQUEST:
// the box's owner approves it (see src-tauri/src/manage.rs).

export const LIFECYCLE_LABEL = {
  'app.start': 'Start',
  'app.stop': 'Stop',
  'app.restart': 'Restart',
  'app.update': 'Update',
  'app.remove': 'Remove',
};

export function lifecycleLabel(kind) {
  return LIFECYCLE_LABEL[kind] || kind;
}

/** Is this token an owner? true / false when `/v1/me` said so, null when the box did not say. */
export function isOwner(st) {
  const me = st && st.me;
  if (!me || !me.role) return null;
  return me.kind === 'person' && me.role === 'owner';
}

const HEALTH = {
  ok: ['ok', 'Protected'],
  stale: ['warn', 'Out of date'],
  failing: ['bad', 'Failing'],
  not_configured: ['warn', 'Not set up'],
};

export function backupHealth(health) {
  const [tone, label] = HEALTH[health] || ['neutral', 'Unknown'];
  return { tone, label };
}

/** What the confirmation card says about a plan. `refused` means the box will not file it now. */
export function planCard(plan) {
  if (plan.verdict === 'refused') {
    return { canSend: false, title: `The box will not file this now${plan.reason ? `: ${plan.reason}` : ''}.`, facts: [] };
  }
  const facts = [];
  if (plan.from_version && plan.to_version) facts.push(['Version', `${plan.from_version} → ${plan.to_version}`]);
  if (plan.volumes) facts.push(['Storage', `${plan.volumes} volume${plan.volumes === 1 ? '' : 's'}`]);
  if (plan.risk) facts.push(['Risk', plan.risk]);
  return { canSend: !!plan.plan_sha256, title: plan.summary || 'The box sent a plan without a summary.', facts };
}

/** Words for a request the box accepted. Nothing has happened yet. */
export function filedText(f) {
  return `Request sent (${(f.state || 'awaiting_approval').replace(/_/g, ' ')}). Nothing has changed yet: it waits in the approval list until an owner decides.`;
}

export function validBoxName(n) {
  return /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(n);
}

const KIND = { usb: 'usb', peer: 'box', s3: 's3' };

export function destinationsFor(choice, dests) {
  return KIND[choice] ? dests.filter((d) => d.kind === KIND[choice]) : [];
}

/** Same checks as the Rust side; the box validates again and writes nothing on a refusal. */
export function settingsProblem(b, dests) {
  if (!validBoxName(b.box_name)) return 'invalid_box_name';
  const z = b.time_zone.trim();
  if (!z || z.startsWith('/') || /\s/.test(z)) return 'invalid_time_zone';
  if (b.backup_choice === 'later' && b.backup_destination_id) return 'destination_not_allowed';
  if (b.backup_destination_id && !destinationsFor(b.backup_choice, dests).some((d) => d.id === b.backup_destination_id)) return 'destination_mismatch';
  return null;
}

export const CHOICES = [
  ['usb', 'USB disk'],
  ['peer', 'Another box'],
  ['s3', 'Cloud (S3)'],
  ['later', 'Later'],
];
