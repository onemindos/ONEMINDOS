// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { makeActions, makeApps, makeNodes } from '../api/fixtures';
import type { Action } from '../api/types';
import { toRoute } from '../shell/routes';
import { activityFrom, categorySlug, deployClass, iconOf, jobState, notificationsFrom, openUrl, runState, toActionSummary, toInstalled, toJob, toStoreApp } from './adapters';
import { personStorage } from './prefs';

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

  it('opens an installed app on its web port on this host, and nothing else', () => {
    const loc = { protocol: 'https:', hostname: 'onemind.local' };
    expect(openUrl({ installed: true, web_port: 3001 }, loc)).toBe('https://onemind.local:3001/');
    expect(openUrl({ installed: false, web_port: 3001 }, loc)).toBeUndefined();
    expect(openUrl({ installed: true, web_port: null }, loc)).toBeUndefined();
  });

  it('says "installed", not "running": v0 reports no health', () => {
    expect(runState('installed')).toBe('installed');
    expect(runState('installing')).toBe('starting');
    expect(runState('failed')).toBe('unhealthy');
    expect(runState('removing')).toBe('unknown');
    expect(toInstalled(makeApps(NOW)[0]!, new Date(NOW).toISOString()).state).toBe('installed');
  });
});

describe('actions → approvals, progress, notifications, activity', () => {
  const actions = makeActions(NOW);

  it('keeps who asked and the failure message', () => {
    const s = toActionSummary(actions[2]!);
    expect(s.requested_by?.id).toBe('owner');
    expect(s.message).toBe('kubectl delete exited with status 1');
    expect(toActionSummary(actions[0]!).requested_by?.kind).toBe('agent');
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
    expect(toRoute('#/backups')).toBe('/settings/backups');
    expect(toRoute('/installed/x')).toBe('/installed/x');
  });

  it('never follows an external or protocol-relative link', () => {
    expect(toRoute('https://example.org')).toBeUndefined();
    expect(toRoute('//example.org/x')).toBeUndefined();
    expect(toRoute('javascript:alert(1)')).toBeUndefined();
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
});
