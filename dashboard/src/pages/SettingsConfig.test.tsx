// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SettingsConfig } from './SettingsConfig';

const session = vi.hoisted(() => ({ token: 'fixture', mock: false, canDecide: 'yes' }));
vi.mock('../session', () => ({ useSignedIn: () => session }));

beforeEach(() => { session.canDecide = 'yes'; });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const exported = Object.fromEntries(['settings', 'apps', 'users', 'schedules'].map((id) =>
  [`${id}.yaml`, `schema: onemind.io/config-as-code/${id}/v1\n`]));

function gateway(diff?: Response) {
  const request = vi.fn(async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === '/v1/config/export' && init.method === 'GET') return Response.json({ yaml: exported['settings.yaml'], files: exported });
    if (path === '/v1/config/diff' && init.method === 'POST' && diff) return diff;
    throw new Error(`Unexpected test request ${init.method} ${path}`);
  });
  vi.stubGlobal('fetch', request);
  return request;
}

it('exports each gateway file with its original name and YAML bytes', async () => {
  const request = gateway();
  const create = vi.fn<(blob: Blob) => string>().mockReturnValue('blob:config');
  const revoke = vi.fn();
  vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = revoke; });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  const user = userEvent.setup();
  render(<SettingsConfig />);
  expect(request).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Export config' }));

  for (const name of Object.keys(exported)) {
    await user.click(await screen.findByRole('button', { name: `Download ${name}` }));
  }
  expect(click.mock.contexts.map((link) => (link as HTMLAnchorElement).download)).toEqual(Object.keys(exported));
  const downloaded = await Promise.all(create.mock.calls.map(([blob]) => new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsText(blob);
  })));
  expect(downloaded).toEqual(Object.values(exported));
  expect(revoke).toHaveBeenCalledTimes(Object.keys(exported).length);
  expect(request).toHaveBeenCalledTimes(1);
  expect(new Headers(request.mock.calls[0]?.[1].headers).get('Authorization')).toBe('Bearer fixture');
});

it('compares selected YAML through the gateway and displays before and after without requesting apply', async () => {
  const before = `${exported['settings.yaml']}box:\n  name: old-box\n`;
  const after = `${exported['settings.yaml']}box:\n  name: new-box\n`;
  const request = gateway(Response.json({
    revision: 'rev', changes: [{ file: 'settings.yaml', before, after }], blockers: ['Prepare the backup destination.'],
  }));
  const user = userEvent.setup();
  render(<SettingsConfig />);
  const compare = screen.getByRole('button', { name: 'Compare with this box' });
  expect(compare).toBeDisabled();
  const picker = screen.getByLabelText('Choose YAML files to compare');
  const settings = new File([after], 'settings.yaml');
  const apps = new File([exported['apps.yaml']!], 'apps.yaml');
  await user.upload(picker, [settings, apps]);
  await user.click(compare);

  expect(await screen.findByText('Review the proposed changes.')).toBeVisible();
  expect(screen.getByText('settings.yaml')).toBeVisible();
  expect(screen.getByRole('heading', { name: 'On this box' }).nextElementSibling?.textContent).toBe(before);
  expect(screen.getByRole('heading', { name: 'From your files' }).nextElementSibling?.textContent).toBe(after);
  expect(screen.getByRole('heading', { name: 'Resolve before requesting approval' })).toBeVisible();
  expect(screen.getByText('Prepare the backup destination.')).toBeVisible();
  expect(screen.getByText(/onemind config apply --dir <path>.*approve the plan in Approvals/)).toBeVisible();
  expect(screen.queryByText('apps.yaml')).not.toBeInTheDocument();
  expect(request).toHaveBeenCalledTimes(1);
  expect(JSON.parse(String(request.mock.calls[0]?.[1].body))).toEqual({ files: { 'settings.yaml': after, 'apps.yaml': exported['apps.yaml'] } });
  await user.upload(picker, apps);
  expect(screen.queryByText('Review the proposed changes.')).not.toBeInTheDocument();
});

it('shows a matching comparison and communicates version refusals', async () => {
  const user = userEvent.setup();
  const file = new File(['schema: v9\n'], 'settings.yaml');
  gateway(Response.json({ error: 'invalid_config', message: 'Unsupported schema in settings.yaml.' }, { status: 422 }));
  const view = render(<SettingsConfig />);
  await user.upload(screen.getByLabelText('Choose YAML files to compare'), file);
  await user.click(screen.getByRole('button', { name: 'Compare with this box' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Unsupported schema in settings.yaml.');
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  view.unmount();

  gateway(Response.json({ revision: 'rev', changes: [], blockers: [] }));
  render(<SettingsConfig />);
  await user.upload(screen.getByLabelText('Choose YAML files to compare'), new File([exported['settings.yaml']!], 'settings.yaml'));
  await user.click(screen.getByRole('button', { name: 'Compare with this box' }));
  expect(await screen.findByRole('status')).toHaveTextContent('The selected files match this box.');
});

it('does not offer configuration to a nonowner', () => {
  session.canDecide = 'no';
  const request = gateway();
  render(<SettingsConfig />);
  expect(screen.queryByRole('button', { name: 'Export config' })).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Choose YAML files to compare')).not.toBeInTheDocument();
  expect(request).not.toHaveBeenCalled();
});
