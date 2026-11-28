// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const slot = (s: string, declared: boolean, names: string[] = [], approval = 'none') => ({ slot: s, declared, names, approval });
const IRRIGATION = { id: 'irrigation', name: 'Irrigation', installed_version: '1.2.0', status: 'installed', slots: [
  slot('home_tile', true, ['next-run']), slot('map_layer', true, ['water-lines']), slot('settings_panel', true, ['schedule', 'beds']),
  slot('commands', true, ['run', 'skip'], 'each_time'), slot('dock_item', false)] };
const SOLAR = { id: 'solar-monitor', name: 'Solar Monitor', installed_version: null, status: 'stopped', slots: [
  slot('home_tile', true, ['today']), slot('map_layer', false), slot('settings_panel', false), slot('commands', false), slot('dock_item', false)] };

const BROKEN = { id: 'zigbee', name: 'Zigbee Devices', installed_version: '1.2.0', status: 'failed', slots: SOLAR.slots };

function setup(plugins: unknown[]) {
  const writes: Array<Record<string, unknown>> = [];
  const previews: Array<Record<string, unknown>> = [];
  const fetchFn = vi.fn(async (path: string, init?: RequestInit) => {
    path = new URL(path, window.location.origin).pathname;
    if (path === '/v1/plugins') return Response.json(plugins);
    if (path === '/v1/actions') {
      const body = JSON.parse(init!.body as string);
      writes.push(body);
      return Response.json({ ...body, id: 'plugin-request', state: 'awaiting_approval' });
    }
    const body = JSON.parse(init!.body as string);
    previews.push(body);
    return Response.json({ plan: { summary: `Plan for ${body.type}`, objects: [], volumes: [], warnings: [] }, plan_sha256: 'sha256:reviewed', app_id: body.params.app_id, type: body.type, policy_verdict: 'needs_approval', risk: 'write', reason: null });
  });
  const http = new HttpApi({ token: 'test-only', fetchFn });
  const api = Object.assign(new MockApi('owner-demo'), {
    plugins: http.plugins.bind(http), previewAction: http.previewAction.bind(http), createAction: http.createAction.bind(http), appPlan: http.appPlan.bind(http),
  });
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/plugins']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'test-owner', kind: 'person', role: 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { writes, previews, user: userEvent.setup() };
}

describe('Plugins screen', () => {
  it('lists real plugins and the five places each one uses, with who decides', async () => {
    setup([IRRIGATION, SOLAR]);
    const list = await screen.findByRole('navigation', { name: 'Installed plugins' });
    expect(within(list).getByText('Installed · 2 · 1 paused')).toBeInTheDocument();
    expect(within(list).getByText('v1.2.0')).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: 'Places used by Irrigation' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows.map((r) => within(r).getAllByRole('rowheader')[0]!.textContent?.replace(/^\d\s*/, '').trim())).toEqual(['Home tile', 'Map layer', 'Settings panel', 'Commands', 'Dock item']);
    expect(rows[3]).toHaveTextContent('run, skip');
    expect(rows[3]).toHaveTextContent('A person approves each call');
    expect(rows[4]).toHaveTextContent('Not declared');
  });

  it('shows a stopped plugin paused on its own row and offers Enable, not Restart', async () => {
    const { user } = setup([IRRIGATION, SOLAR]);
    await user.click(await screen.findByRole('button', { name: /Solar Monitor/ }));
    expect(await screen.findByText('Solar Monitor is paused.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Restart' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Enable' })).toBeEnabled();
    expect(screen.getByText('$ onemind plugins enable solar-monitor')).toBeInTheDocument();
  });

  it('lists a failed plugin as Failed, keeps Restart and Disable available, and offers no update when none is offered', async () => {
    const { user, previews } = setup([IRRIGATION, BROKEN]);
    const list = await screen.findByRole('navigation', { name: 'Installed plugins' });
    expect(within(list).getByText('Installed · 2 · 1 failed')).toBeInTheDocument();
    await user.click(within(list).getByRole('button', { name: /Zigbee Devices/ }));
    expect(await screen.findByText('Zigbee Devices failed.')).toBeInTheDocument();
    expect(screen.getAllByText('Failed').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Disable' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Up to date' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Restart' }));
    await screen.findByRole('dialog', { name: 'Review app request' });
    expect(previews[0]).toMatchObject({ type: 'app.restart', params: { app_id: 'zigbee' } });
  });

  it('Disable previews the plan, then files a request that waits for approval and does not run anything', async () => {
    const { user, writes, previews } = setup([IRRIGATION]);
    await user.click(await screen.findByRole('button', { name: 'Disable' }));
    const dialog = await screen.findByRole('dialog', { name: 'Review app request' });
    expect(writes).toEqual([]);
    expect(previews[0]).toMatchObject({ type: 'app.stop', params: { app_id: 'irrigation' } });
    await user.click(within(dialog).getByRole('button', { name: 'Send request' }));
    await screen.findByText('Request sent');
    expect(writes).toHaveLength(1);
    expect(writes[0]).toMatchObject({ type: 'app.stop', params: { app_id: 'irrigation' }, plan_sha256: 'sha256:reviewed' });
  });

  it('says what happens next when there are no plugins, with the CLI line, and invents no sample plugin', async () => {
    setup([]);
    expect(await screen.findByText('No plugins installed')).toBeInTheDocument();
    expect(screen.getByText('onemind plugins list')).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Installed plugins' })).not.toBeInTheDocument();
  });
});
