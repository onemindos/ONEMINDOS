// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { describe, expect, it, vi } from 'vitest';
import { catalog, collections, featured, installed, jobs, logs, NOW, planFor } from '../../demo/src/store/fixtures';
import { AppDetail } from './AppDetail';
import { InstalledList, ManageApp } from './Installed';
import { InstallReview } from './InstallReview';
import { JobProgress, JobsTray } from './Jobs';
import { Market } from './Market';
import type { LoadState } from './types';

const READY: LoadState = { kind: 'ready', fetched_at: new Date(NOW).toISOString() };

async function noAxeViolations(el: Element) {
  const res = await axe.run(el, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(', ')}`)).toEqual([]);
}

const handlers = () => ({ onRequestInstall: vi.fn(), onOpen: vi.fn(), appHref: (id: string) => `#/store/app/${id}` });

describe('Market', () => {
  it('shows Discover rails and passes axe', async () => {
    const { container } = render(<Market apps={catalog} state={READY} now={NOW} collections={collections} featured={featured} jobs={jobs} {...handlers()} />);
    expect(screen.getByRole('heading', { name: 'Every photo, off the phone and on your box' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Needs you/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Recommended for this box/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Field & Robotics/ })).toBeInTheDocument();
    await noAxeViolations(container);
  });

  it('filters by category chip, shows sub-tags, and announces the count', async () => {
    const u = userEvent.setup();
    render(<Market apps={catalog} state={READY} now={NOW} {...handlers()} />);
    await u.click(screen.getByRole('button', { name: /^Files & Photos/ }));
    expect(screen.getByRole('button', { name: /^Files & Photos/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('status')).toHaveTextContent('3 apps');
    await u.click(screen.getByRole('button', { name: /#photos/ }));
    expect(within(screen.getByRole('list', { name: 'Apps' })).getAllByRole('article')).toHaveLength(1);
  });

  it('searches, shows an empty state with the CLI, and resets', async () => {
    const u = userEvent.setup();
    render(<Market apps={catalog} state={READY} now={NOW} {...handlers()} />);
    await u.type(screen.getByRole('searchbox'), 'zzzz');
    expect(screen.getByText('No apps match')).toBeInTheDocument();
    expect(screen.getByText(/onemind apps list --search "zzzz"/)).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: 'Clear search and filters' }));
    expect(screen.getByRole('searchbox')).toHaveValue('');
  });

  it('keeps disabled install buttons explained, and turns on hidden apps', async () => {
    const u = userEvent.setup();
    const h = handlers();
    render(<Market apps={catalog} state={READY} now={NOW} {...h} initialFilters={{ q: 'grafana' }} />);
    const btn = screen.getByRole('button', { name: /Request install Grafana/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAccessibleDescription(/more than 7 days old/);
    await u.clear(screen.getByRole('searchbox'));
    await u.type(screen.getByRole('searchbox'), 'ollama');
    await u.click(screen.getByRole('button', { name: 'Show them anyway' }));
    expect(screen.getByRole('button', { name: /Request install Ollama/ })).toHaveAccessibleDescription(/No node can run it/);
  });

  it('opens filters as a disclosure and shows community apps when asked', async () => {
    const u = userEvent.setup();
    render(<Market apps={catalog} state={READY} now={NOW} {...handlers()} initialFilters={{ q: 'searx' }} />);
    expect(screen.getByText('No apps match')).toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: /Filters/ });
    await u.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await u.click(screen.getByRole('checkbox', { name: /Community/ }));
    expect(screen.getByRole('link', { name: 'SearXNG' })).toBeInTheDocument();
    expect(toggle).toHaveAccessibleName(/1 changed/);
  });

  it('renders loading, error and stale states', () => {
    const { rerender } = render(<Market apps={catalog} state={{ kind: 'loading' }} now={NOW} {...handlers()} />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading app catalog');
    rerender(<Market apps={catalog} state={{ kind: 'error', code: 'unauthenticated', message: 'Sign in again.' }} now={NOW} {...handlers()} />);
    expect(screen.getByRole('alert')).toHaveTextContent('unauthenticated');
    rerender(<Market apps={catalog} state={{ kind: 'ready', fetched_at: new Date(NOW - 300_000).toISOString(), stale: true }} now={NOW} {...handlers()} featured={featured} />);
    expect(screen.getAllByText(/Last known app catalog/).length).toBeGreaterThan(0);
    for (const b of screen.getAllByRole('button', { name: /Request install/ })) expect(b).toBeDisabled();
  });
});

describe('AppDetail', () => {
  const imm = catalog.find((a) => a.id === 'immich')!;
  it('shows hero, trust, fit verdict with the stale node, and passes axe', async () => {
    const h = handlers();
    const { container } = render(<AppDetail app={imm} state={READY} plan={planFor('immich')} planState={READY} now={NOW} backHref="#/store" {...h} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Immich' })).toBeInTheDocument();
    expect(screen.getByText(/Fits, but/)).toHaveTextContent('office-laptop is stale');
    expect(screen.getByText(/AGPL-3.0/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Source/ })).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('img', { name: /Placeholder for: Timeline/ })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Request install' }));
    expect(h.onRequestInstall).toHaveBeenCalledWith(imm);
    await noAxeViolations(container);
  });
  it('says when the app does not exist', () => {
    render(<AppDetail state={READY} planState={READY} now={NOW} backHref="#/store" {...handlers()} />);
    expect(screen.getByText('No such app')).toBeInTheDocument();
  });
  it('shows list-only apps with an upstream link and no placement', () => {
    render(<AppDetail app={catalog.find((a) => a.id === 'invoice-ninja')} state={READY} planState={READY} now={NOW} backHref="#/store" {...handlers()} />);
    expect(screen.getByRole('link', { name: /Get it upstream/ })).toHaveAttribute('href', 'https://invoiceninja.com/');
    expect(screen.getByText(/Elastic License 2.0/)).toBeInTheDocument();
  });
});

describe('InstallReview', () => {
  it('walks only the applicable steps and sends one app.install request', async () => {
    const u = userEvent.setup();
    const onSubmit = vi.fn();
    const ha = catalog.find((a) => a.id === 'immich')!;
    render(<InstallReview app={ha} plan={planFor('immich')} open now={NOW} onClose={() => {}} onSubmit={onSubmit} />);
    const dlg = screen.getByRole('dialog');
    expect(dlg).toHaveTextContent('Step 1 of 4');
    expect(screen.getByRole('radio', { name: /pi-garage/ })).toBeDisabled();
    await u.click(screen.getByRole('radio', { name: /home-hub/ }));
    await u.click(screen.getByRole('button', { name: 'Next' }));
    await u.click(screen.getByRole('button', { name: 'Next' }));
    await u.click(screen.getByRole('button', { name: 'Next' }));
    expect(dlg).toHaveTextContent('Review request');
    await noAxeViolations(dlg);
    await u.click(screen.getByRole('button', { name: /Send request/ }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ type: 'app.install', params: { app_id: 'immich', node: 'home-hub' } }));
  });
  it('requires acknowledging a community app before going on', async () => {
    const u = userEvent.setup();
    render(<InstallReview app={catalog.find((a) => a.id === 'searxng')!} plan={planFor('searxng')} open now={NOW} onClose={() => {}} onSubmit={() => {}} />);
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    await u.click(screen.getByRole('checkbox'));
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled();
  });
  it('cannot be sent when no node fits', async () => {
    render(<InstallReview app={catalog.find((a) => a.id === 'ollama')!} plan={planFor('ollama')} open now={NOW} onClose={() => {}} onSubmit={() => {}} />);
    expect(screen.getByText(/No node can run Ollama/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });
});

describe('Jobs', () => {
  it('shows the four steps with the current one, a progressbar and the rollback text', () => {
    const { rerender } = render(<JobProgress job={jobs[1]!} now={NOW} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '43');
    expect(screen.getByText('Pulling image', { selector: '.om-store-step-label' }).closest('li')).toHaveAttribute('aria-current', 'step');
    rerender(<JobProgress job={jobs[2]!} now={NOW} />);
    expect(screen.queryByRole('progressbar')).toBeNull();
    expect(screen.getByText(/put the previous state back/)).toBeInTheDocument();
  });
  it('tray expands to the list and can dismiss finished jobs', async () => {
    const u = userEvent.setup();
    const onDismiss = vi.fn();
    render(<JobsTray jobs={jobs} now={NOW} onDismiss={onDismiss} />);
    const pill = screen.getByRole('button', { name: /2 jobs/ });
    await u.click(pill);
    expect(pill).toHaveAttribute('aria-expanded', 'true');
    await u.click(screen.getByRole('button', { name: 'Dismiss Grafana' }));
    expect(onDismiss).toHaveBeenCalledWith('act-33d0');
  });
});

describe('Installed', () => {
  it('lists apps with honest state and batches updates into one request', async () => {
    const u = userEvent.setup();
    const onRequest = vi.fn();
    const { container, rerender } = render(<InstalledList apps={installed} state={READY} now={NOW} manageHref={(id) => `#/m/${id}`} onOpen={() => {}} onRequest={onRequest} />);
    expect(screen.getByText('Stale')).toBeInTheDocument();
    await noAxeViolations(container);
    rerender(<InstalledList apps={installed} state={READY} now={NOW} view="updates" manageHref={(id) => `#/m/${id}`} onOpen={() => {}} onRequest={onRequest} />);
    await u.click(screen.getByRole('button', { name: 'Request all updates' }));
    await u.click(screen.getByRole('button', { name: 'Send one request' }));
    expect(onRequest).toHaveBeenCalledTimes(1);
    expect(onRequest.mock.calls[0]![0].params.apps).toHaveLength(2);
  });
  it("shows each app's category and deployment kind, and says when there is no web page", () => {
    render(<InstalledList apps={installed} state={READY} now={NOW} manageHref={(id) => `#/m/${id}`} onOpen={() => {}} onRequest={() => {}} />);
    const ha = screen.getByRole('link', { name: 'Home Assistant' }).closest('li')!;
    expect(within(ha).getByText('Home & IoT')).toBeInTheDocument();
    expect(within(ha).getByText('Verified')).toBeInTheDocument();
    const noUrl = installed.find((i) => !i.url)!;
    const row = screen.getByRole('link', { name: noUrl.app.name }).closest('li')!;
    expect(within(row).getByText('No web page')).toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: /^Open/ })).toBeNull();
  });
  it('shows an empty state', () => {
    render(<InstalledList apps={[]} state={READY} now={NOW} manageHref={() => '#'} onOpen={() => {}} onRequest={() => {}} />);
    expect(screen.getByText('No apps installed yet')).toBeInTheDocument();
  });

  const manage = (over: Partial<Parameters<typeof ManageApp>[0]> = {}) => {
    const onRequest = vi.fn();
    const utils = render(
      <ManageApp inst={installed[0]} state={READY} now={NOW} isOwner logs={logs} logState={READY} backHref="#" onOpen={() => {}} onRequest={onRequest} {...over} />,
    );
    return { onRequest, ...utils };
  };

  it('reveals credentials only for the owner, and passes axe', async () => {
    const u = userEvent.setup();
    const { container } = manage();
    expect(screen.queryByText('demo-only-not-a-real-secret')).toBeNull();
    await u.click(screen.getByRole('button', { name: 'Reveal First-run password' }));
    expect(screen.getByText('demo-only-not-a-real-secret')).toBeInTheDocument();
    await noAxeViolations(container);
  });
  it('hides credentials from non-owners', () => {
    manage({ isOwner: false });
    expect(screen.getByText(/Only the owner can see/)).toBeInTheDocument();
  });
  it('remove keeps data by default; deleting needs the typed name and is a second request', async () => {
    const u = userEvent.setup();
    const { onRequest } = manage();
    await u.click(screen.getByRole('button', { name: /Remove/ }));
    const dlg = screen.getByRole('alertdialog');
    expect(within(dlg).getByRole('radio', { name: /Keep the data/ })).toBeChecked();
    await u.click(within(dlg).getByRole('radio', { name: /Delete the data too/ }));
    const go = within(dlg).getByRole('button', { name: 'Request removal and deletion' });
    expect(go).toBeDisabled();
    await u.type(within(dlg).getByRole('textbox'), 'Home Assistant');
    await u.click(go);
    expect(onRequest.mock.calls.map((c) => c[0].type)).toEqual(['app.remove', 'app.delete_data']);
    expect(onRequest.mock.calls[0]![0].params.keep_data).toBe(false);
  });
  it('update shows release notes and the health-gated steps', async () => {
    const u = userEvent.setup();
    const { onRequest } = manage();
    await u.click(screen.getByRole('button', { name: /Update to 2026.11.2/ }));
    const dlg = screen.getByRole('dialog');
    expect(dlg).toHaveTextContent('Fixes Zigbee devices dropping');
    expect(dlg).toHaveTextContent('put 2026.11.1 and the snapshot back');
    await u.click(within(dlg).getByRole('button', { name: 'Request update' }));
    expect(onRequest).toHaveBeenCalledWith(expect.objectContaining({ type: 'app.update', params: { app_id: 'home-assistant', to_version: '2026.11.2' } }));
  });
  it('tabs work with arrow keys; settings submit one app.configure; logs filter', async () => {
    const u = userEvent.setup();
    const { onRequest } = manage();
    const overview = screen.getByRole('tab', { name: 'Overview' });
    overview.focus();
    await u.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Settings' })).toHaveAttribute('aria-selected', 'true');
    await u.click(screen.getByRole('checkbox', { name: /Zigbee radio/ }));
    await u.click(screen.getByRole('button', { name: /Request 1 change/ }));
    expect(onRequest).toHaveBeenCalledWith(expect.objectContaining({ type: 'app.configure', params: { app_id: 'home-assistant', values: { zigbee: false } } }));
    await u.click(screen.getByRole('tab', { name: 'Logs' }));
    expect(screen.getByRole('log')).toHaveTextContent('zigbee: network formed');
    await u.click(screen.getByRole('radio', { name: 'Errors' }));
    expect(screen.getByRole('log')).not.toHaveTextContent('network formed');
  });
  it('does not offer Remove for a core app', () => {
    manage({ inst: installed[3] });
    expect(screen.queryByRole('button', { name: /Remove/ })).toBeNull();
    expect(screen.getByText(/cannot be removed/)).toBeInTheDocument();
  });
});
