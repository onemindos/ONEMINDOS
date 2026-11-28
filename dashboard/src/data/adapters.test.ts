// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { makeActions, makeApps, makeNodes } from '../api/fixtures';
import type { Action, NodeRecord } from '../api/types';
import { toRoute } from '../shell/routes';
import { activityFrom, categorySlug, deployClass, NO_APP_NAME_NOTE, iconOf, jobState, notificationsFrom, openUrl, runState, toActionPlan, toActionSummary, principalNamer, toInstalled, toJob, toStoreApp, toHomeNode } from './adapters';
import { personKey, personStorage } from './prefs';

const NOW = Date.parse('2026-11-12T12:00:00Z');
const names = (id: string) => ({ ollama: 'Ollama', 'uptime-kuma': 'Uptime Kuma' })[id] ?? id;

describe('catalog → Market (TAXONOMY §1, §11.4)', () => {
  it('maps legacy category slugs on main to the 16 categories', () => {
    expect(categorySlug('home-automation')).toBe('home');
    expect(categorySlug('iot')).toBe('home');
    expect(categorySlug('notifications')).toBe('automation');
    expect(categorySlug('passwords')).toBe('network');
    expect(categorySlug('finance')).toBe('finance');
    expect(categorySlug('something-new')).toBeUndefined();
    expect(categorySlug(null)).toBeUndefined();
  });

  it('derives the deployment class from the tier, never claiming more than the gate said', () => {
    expect(deployClass('verified')).toBe('market-verified');
    expect(deployClass('blocked')).toBe('market-verified');
    expect(deployClass('community')).toBe('market-community');
    expect(deployClass(null)).toBe('market-community');
  });

  it('uses the gate class only for the current manifest licence', () => {
    // An older gateway sends no declared class: only the gate's scan record can give one.
    const app = { ...makeApps(NOW)[0]!, licence_class: undefined };
    const scan = { scanned_at: new Date(NOW).toISOString(), result: 'pass' as const };
    const checked = { ...scan, licence: { spdx: 'MIT', class: 'L1' as const } };
    expect(toStoreApp({ ...app, license: 'MIT', scan: checked }).licence_class).toBe('L1');
    expect(toStoreApp({ ...app, license: 'MIT', scan }).licence_class).toBe('L?');
    expect(toStoreApp({ ...app, license: 'GPL-3.0', scan: checked }).licence_class).toBe('L?');
    expect(toStoreApp({ ...app, license: 'MIT', scan: { ...scan, licence: { spdx: 'MIT', class: 'blocked' } } }).licence_class).toBe('blocked');
  });

  it('takes the manifest licence class first and never shows unknown as green (#173)', () => {
    const app = makeApps(NOW)[0]!;
    const scan = { scanned_at: new Date(NOW).toISOString(), result: 'pass' as const };
    const gate = (cls: 'L1' | 'L2' | 'blocked') => ({ ...scan, licence: { spdx: 'MIT', class: cls } });
    const of = (licence_class: 'L1' | 'L2' | 'blocked' | 'unknown', s = scan) =>
      toStoreApp({ ...app, license: 'MIT', licence_class, scan: s }).licence_class;
    expect(of('L1')).toBe('L1');
    expect(of('L2')).toBe('L2');
    expect(of('unknown', gate('L1'))).toBe('L?');
    expect(of('blocked', gate('L1'))).toBe('blocked');
    expect(of('L1', gate('blocked'))).toBe('blocked');
  });

  it('keeps scan, tier, links and licence; tolerates null fields from the gateway', () => {
    const [kuma] = makeApps(NOW);
    const s = toStoreApp(kuma!);
    expect(s.scan).toEqual(kuma!.scan);
    expect(s.tier).toBe('verified');
    expect(s.links?.github).toContain('github.com');
    const bare = toStoreApp({ ...kuma!, name: null, version: null, description: null, category: null, license: null, icon: null });
    expect(bare.name).toBe('uptime-kuma');
    expect(bare.license).toBe('unknown');
    expect(bare.category).toBe('uncategorised');
  });

  it('uses only http(s) or same-origin icons', () => {
    expect(iconOf('icon.svg')).toBeUndefined();
    expect(iconOf('javascript:alert(1)')).toBeUndefined();
    expect(iconOf('//evil.example/a.png')).toBeUndefined();
    expect(iconOf('/v1/apps/x/icon')).toBe('/v1/apps/x/icon');
    expect(iconOf('https://example.org/a.png')).toBe('https://example.org/a.png');
  });

  it('opens an installed app at its own name on the box, never its raw port', () => {
    const loc = { protocol: 'https:', hostname: 'onemind.local' };
    expect(openUrl({ id: 'uptime-kuma', installed: true, web_port: 3001 }, loc)).toBe('https://uptime-kuma.onemind.local/');
    expect(openUrl({ id: 'uptime-kuma', installed: true, web_port: 3001 }, { protocol: 'https:', hostname: 'box1.local' })).toBe('https://uptime-kuma.box1.local/');
    expect(openUrl({ id: 'x', installed: false, web_port: 3001 }, loc)).toBeUndefined();
    expect(openUrl({ id: 'x', installed: true, web_port: null }, loc)).toBeUndefined();
  });

  it('has no link from an address that cannot name the app (an IP or another domain)', () => {
    for (const hostname of ['192.0.2.10', 'localhost', 'box.example.org', 'evil.local.example.org']) {
      expect(openUrl({ id: 'x', installed: true, web_port: 3001 }, { protocol: 'https:', hostname })).toBeUndefined();
    }
    expect(openUrl({ id: 'a.b', installed: true, web_port: 3001 }, { protocol: 'https:', hostname: 'onemind.local' })).toBeUndefined();
  });

  it('says "installed", not "running": v0 reports no health', () => {
    expect(runState('installed')).toBe('installed');
    expect(runState('installing')).toBe('starting');
    expect(runState('failed')).toBe('unhealthy');
    expect(runState('removing')).toBe('unknown');
    expect(toInstalled(makeApps(NOW)[0]!, new Date(NOW).toISOString()).state).toBe('installed');
  });

  it('links to the app behind the sign-in, and says so when it cannot', () => {
    const app = makeApps(NOW)[0]!;
    const named = toInstalled(app, new Date(NOW).toISOString(), { protocol: 'https:', hostname: 'onemind.local' });
    expect(named.url).toBe(`https://${app.id}.onemind.local/`);
    expect(named.url_note).toBeUndefined();
    const byIp = toInstalled(app, new Date(NOW).toISOString(), { protocol: 'http:', hostname: '192.0.2.10' });
    expect(byIp.url).toBeUndefined();
    expect(byIp.url_note).toBe(NO_APP_NAME_NOTE);
  });
});

describe('actions → approvals, progress, notifications, activity', () => {
  const actions = makeActions(NOW);

  it('keeps who asked and the failure message', () => {
    const s = toActionSummary(actions[2]!);
    expect(s.requested_by?.id).toBe('owner');
    expect(s.message).toBe('kubectl delete exited with status 1');
    expect(toActionSummary(actions[0]!).requested_by?.kind).toBe('agent');
    // Catalog names, not ids: "Install Ollama", never "Install ollama".
    const named = toActionSummary({ ...actions[0]!, params: { app_id: 'ollama' } }, (id) => (id === 'ollama' ? 'Ollama' : id));
    expect(named.target_name).toBe('Ollama');
    expect(toActionSummary({ ...actions[0]!, params: { app_id: 'ollama' } }).target_name).toBeUndefined();
  });

  it('carries the key level approving needs, so the card shows it before the owner tries (D-028)', () => {
    expect(toActionSummary({ ...actions[0]!, required_level: 'L2' }).required_level).toBe('L2');
    expect(toActionSummary(actions[0]!).required_level).toBeUndefined();
  });

  it('keeps why a request needs a hold: physical, or (without physical) cannot be undone', () => {
    const card = (physical: boolean) => ({ ...actions[0]!, approval: { hold: true, hold_ms: 2000, physical } }) as unknown as Action;
    expect(toActionSummary(card(true))).toMatchObject({ hold: { duration: 2000 }, physical: true });
    expect(toActionSummary(card(false)).physical).toBeUndefined();
    expect(toActionSummary(card(false)).hold).toBeDefined();
  });

  it('maps action states onto the install progress track', () => {
    expect(jobState('awaiting_approval')).toBe('awaiting_approval');
    expect(jobState('accepted')).toBe('pulling');
    expect(jobState('dispatched')).toBe('starting');
    expect(jobState('succeeded')).toBe('healthy');
    expect(jobState('cancelled')).toBe('denied');
    expect(jobState('outcome_unknown')).toBe('failed');
    expect(toJob(actions[0]!, 'Ollama').app_name).toBe('Ollama');
  });

  it('builds notifications from actions and offline nodes, with stable ids and read state', () => {
    const nodes = makeNodes(NOW);
    const list = notificationsFrom(actions, nodes, names, new Set(['act:act-0000:done']));
    const waiting = list.find((n) => n.kind === 'approval_waiting')!;
    expect(waiting.title).toBe('Install Ollama is waiting for approval');
    expect(waiting.href).toBe('/approvals?highlight=act-0001');
    expect(list.find((n) => n.id === 'act:act-0000:done')?.read).toBe(true);
    expect(list.find((n) => n.id.startsWith('act:act-ffff'))?.severity).toBe('critical');
    expect(list.filter((n) => n.kind === 'node_offline')).toHaveLength(nodes.filter((n) => n.status === 'offline').length);
  });

  it('builds activity: request, decision, result, numbered oldest first, not chained', () => {
    const entries = activityFrom(actions, names);
    expect(entries.map((e) => e.seq)).toEqual(entries.map((_, i) => i + 1));
    expect(entries.every((e) => e.hash === '')).toBe(true);
    const failed = entries.find((e) => e.kind === 'result' && e.result === 'bad')!;
    expect(failed.text).toContain('kubectl delete exited with status 1');
    const agentAsk = entries.find((e) => e.actor.kind === 'agent')!;
    expect(agentAsk.text).toBe('asked to install Ollama');
  });

  it('does not crash or mislabel on §12.5 action types and §12.1 principal kinds (additive)', () => {
    const drain = { ...actions[0]!, id: 'act-drain', type: 'node.drain', params: { node_id: 'pi5' }, requested_by: { id: 'automation:rule_1', kind: 'automation' } } as unknown as Action;
    const plugin = { ...actions[0]!, id: 'act-plug', state: 'succeeded', requested_by: { id: 'plugin:hermes', kind: 'plugin' } } as unknown as Action;
    const entries = activityFrom([drain, plugin], names);
    expect(entries.find((e) => e.kind === 'request' && e.text.includes('pi5'))?.text).toBe('asked to node.drain pi5');
    expect(entries.every((e) => e.actor.kind !== 'person')).toBe(true);
    const list = notificationsFrom([drain], [], names, new Set());
    expect(list[0]!.title).toBe('node.drain pi5 is waiting for approval');
    // An automation or plugin must never read "Person" on the approval card.
    expect(toActionSummary(drain).requested_by?.kind).toBe('agent');
    expect(toActionSummary(plugin).requested_by?.kind).toBe('agent');
    expect(toJob(drain, 'x').app_id).toBe('');
  });

  it('records a denial as a decision, not a result', () => {
    const denied: Action = { ...actions[0]!, state: 'cancelled', decided_by: { id: 'owner', kind: 'person', role: 'owner' }, decided_at: new Date(NOW).toISOString() };
    const e = activityFrom([denied], names);
    expect(e.map((x) => x.kind)).toEqual(['request', 'decision']);
    expect(e[1]!.resultLabel).toBe('Denied');
  });
});

describe('routes from ui links', () => {
  it('maps the ui hash links to dashboard paths', () => {
    expect(toRoute('#/home')).toBe('/');
    expect(toRoute('#/apps')).toBe('/market');
    expect(toRoute('#/app/immich')).toBe('/market/immich');
    expect(toRoute('#/approvals/a-1')).toBe('/approvals?highlight=a-1');
    expect(toRoute('#/settings/people')).toBe('/settings/users');
    expect(toRoute('#/settings/appearance')).toBe('/settings/appearance');
    expect(toRoute('#/settings/security')).toBe('/settings/security'); // the Security overview page, no alias to account
    expect(toRoute('#/backups')).toBe('/backups');
    expect(toRoute('/installed/x')).toBe('/installed/x');
  });

  it('never follows an external or protocol-relative link', () => {
    expect(toRoute('https://example.org')).toBeUndefined();
    expect(toRoute('//example.org/x')).toBeUndefined();
    expect(toRoute('javascript:alert(1)')).toBeUndefined();
    // Browsers read "\\" as "/" and drop tabs/newlines: both would leave the origin.
    expect(toRoute('/\\evil.example')).toBeUndefined();
    expect(toRoute('#/\\evil.example/x')).toBeUndefined();
    expect(toRoute('/\t/evil.example')).toBeUndefined();
    expect(toRoute('/\n/evil.example')).toBeUndefined();
  });
});

describe('per-person storage', () => {
  it('keeps two people apart in one browser', () => {
    const m = new Map<string, string>();
    const base = { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) } as Storage;
    const a = personStorage('owner', base)!;
    const b = personStorage('alex', base)!;
    a.setItem('k', '1');
    expect(b.getItem('k')).toBeNull();
    expect(a.getItem('k')).toBe('1');
  });

  it('gives each token its own slot when the gateway cannot say who is signed in (v0)', () => {
    const t1 = 'a'.repeat(64);
    const t2 = 'b'.repeat(64); // same length: the old key collapsed these two people
    expect(personKey(undefined, t1)).not.toBe(personKey(undefined, t2));
    expect(personKey(undefined, t1)).toBe(personKey(undefined, t1));
    expect(personKey(undefined, t1)).toMatch(/^token-[0-9a-f]{8}$/);
    expect(personKey('owner', t1)).toBe('owner');
  });
});

describe('tainted agent request (AIG-04, #168)', () => {
  const base = { id: 'a1', type: 'app.remove', params: { app_id: 'whoami' }, idempotency_key: 'k', expires_at: '', state: 'awaiting_approval', plan_sha256: 'h' };
  it('puts the gateway taint note first on the approval card, high risk, naming what the agent read', () => {
    const plan = { summary: 'Remove whoami.', warnings: [], taint: { sources: ['mcp:get_app', 'mcp:resource:catalog'], since: '2026-11-22T10:00:00Z', message: 'This agent read text written by third parties before asking. Check the request against what you wanted, not against what the agent says.' } };
    const p = toActionPlan({ ...base, plan } as unknown as Action)!;
    expect(p.effects[0]).toMatchObject({ kind: 'note', risk: 'high' });
    expect(p.effects[0]!.label).toMatch(/third parties/);
    expect(p.effects[0]!.detail).toContain('mcp:get_app, mcp:resource:catalog');
  });
  it('adds nothing when the requester read nothing from outside', () => {
    const p = toActionPlan({ ...base, plan: { summary: 'Remove whoami.', warnings: [] } } as unknown as Action)!;
    expect(p.effects.map((e) => e.label)).toEqual(['Remove whoami.']);
  });
  it('shows the physical print job and printer on the approval plan', () => {
    const a = { ...base, type: 'print.job.release', plan: {}, approval: {
      physical: true, hold: true, hold_ms: 2000, limits: [],
      preview: { kind: 'text', text: 'Print report.pdf on Office' },
    } } as unknown as Action;
    expect(toActionPlan(a)?.effects).toEqual([{ kind: 'note', risk: 'high', label: 'Print report.pdf on Office' }]);
  });
});

describe('names on approvals', () => {
  const nameOf = principalNamer([{ id: 'usr_1', display_name: 'Alex' }], [{ id: 'ops-agent' }]);
  it('uses the display name of a person and the name of an agent, and nothing for the unknown', () => {
    expect(nameOf({ id: 'usr_1', kind: 'person' })).toBe('Alex');
    expect(nameOf({ id: 'usr_2', kind: 'person' })).toBeUndefined();
    expect(nameOf({ id: 'agent:ops-agent', kind: 'agent' })).toBe('ops-agent');
    expect(nameOf({ id: 'ops-agent', kind: 'agent' })).toBe('ops-agent');
    expect(nameOf({ id: 'plugin:x', kind: 'plugin' })).toBeUndefined();
  });
  it('puts the names on the summary and leaves the ids intact', () => {
    const a: Action = { id: 'a1', type: 'app.restart', params: {}, idempotency_key: 'k', expires_at: '2026-11-12T13:00:00Z', state: 'succeeded', requested_by: { id: 'usr_1', kind: 'person', role: 'owner' }, decided_by: { id: 'usr_1', kind: 'person', role: 'owner' } } as Action;
    const s = toActionSummary(a, undefined, nameOf);
    expect(s.requested_by).toMatchObject({ id: 'usr_1', name: 'Alex' });
    expect(s.decided_by).toMatchObject({ id: 'usr_1', name: 'Alex' });
    expect(toActionSummary(a).requested_by?.name).toBeUndefined();
  });
});

describe('node heartbeat → Home node (CPU and temperature)', () => {
  const [base] = makeNodes(NOW) as [NodeRecord];
  it('lifts the heartbeat metrics object into the flat fields Home reads', () => {
    const n = toHomeNode({ ...base, metrics: { cpu_pct: 37.5, load1: 0.4, temp_c: 51 } });
    expect(n.cpu_percent).toBe(37.5);
    expect(n.temp_c).toBe(51);
  });
  it('keeps a figure the node did not report null, never 0', () => {
    expect(toHomeNode({ ...base, metrics: { cpu_pct: null, temp_c: null } })).toMatchObject({ cpu_percent: null, temp_c: null });
    expect(toHomeNode({ ...base, metrics: undefined })).toMatchObject({ cpu_percent: null, temp_c: null });
  });
});
