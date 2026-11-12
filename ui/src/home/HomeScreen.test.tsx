// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { HomeScreen, type HomeScreenProps } from './HomeScreen';
import type { HomeLayout } from './layout';
import type { HomeData } from './types';
import { NOW, TIME_ZONE, demoLayout, errorData, freshData, homeData, loadingData, offlineData } from '../../demo/src/home/fixtures';

async function noAxeViolations(container: Element) {
  const res = await axe.run(container, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(' | ')}`)).toEqual([]);
}

function Harness(props: Partial<HomeScreenProps> & { data?: HomeData; start?: HomeLayout; onSaved?: (l: HomeLayout) => void }) {
  const { data = homeData, start = demoLayout, onSaved, ...rest } = props;
  const [layout, setLayout] = useState(start);
  return (
    <main>
    <HomeScreen
      data={data}
      now={NOW}
      timeZone={TIME_ZONE}
      personName="Robin"
      layout={layout}
      onLayoutChange={(l) => {
        setLayout(l);
        onSaved?.(l);
      }}
      canDecide={{ allowed: true }}
      {...rest}
    />
    </main>
  );
}

const widget = (name: RegExp | string) => screen.getByRole('region', { name });

describe('HomeScreen', () => {
  it('greets by name and time of day, and says what needs the person', async () => {
    const { container } = render(<Harness />);
    expect(screen.getByRole('heading', { level: 1, name: 'Good afternoon, Robin' })).toBeInTheDocument();
    expect(screen.getByText('3 requests need your decision; 1 app is unhealthy; 1 stale and 1 offline nodes.')).toBeInTheDocument();
    expect(screen.getByLabelText('Weather')).toHaveTextContent('Light rain');
    await noAxeViolations(container);
  });

  it('keeps Needs you first; approve and deny go to the host with the action', async () => {
    const onApprove = vi.fn();
    const onDeny = vi.fn();
    render(<Harness onApprove={onApprove} onDeny={onDeny} />);
    const list = within(screen.getByRole('list', { name: 'Widgets' })).getAllByRole('listitem');
    expect(within(list[0]!).getByRole('heading', { name: 'Needs you' })).toBeInTheDocument();
    const needs = widget('Needs you');
    expect(within(needs).getByText('3 waiting')).toBeInTheDocument();
    expect(within(needs).getByText('Agent')).toBeInTheDocument();
    await userEvent.click(within(needs).getAllByRole('button', { name: 'Approve' })[0]!);
    expect(onApprove).toHaveBeenCalledWith(expect.objectContaining({ id: 'a-7f31' }));
    await userEvent.click(within(needs).getAllByRole('button', { name: 'Deny' })[1]!);
    expect(onDeny).toHaveBeenCalledWith(expect.objectContaining({ id: 'a-7f2c' }));
  });

  it('a viewer who may not decide sees the buttons disabled with the reason', () => {
    render(<Harness canDecide={{ allowed: false, reason: 'Only the owner can approve.' }} />);
    const approve = within(widget('Needs you')).getAllByRole('button', { name: 'Approve' })[0]!;
    expect(approve).toBeDisabled();
    expect(approve).toHaveAccessibleDescription('Only the owner can approve.');
  });

  it('never shows a cached green: hub offline makes everything last known and blocks decisions', () => {
    render(<Harness data={offlineData} />);
    expect(screen.getByText(/Showing the last known state from 6 min ago/)).toBeInTheDocument();
    expect(screen.getByText('The hub is not answering. Everything below is its last known state.')).toBeInTheDocument();
    expect(screen.getAllByText('Last known').length).toBeGreaterThan(3);
    expect(within(widget('Needs you')).getAllByRole('button', { name: 'Approve' })[0]).toHaveAccessibleDescription('The hub is not answering. Decide when it is back.');
    expect(screen.getAllByText('Running (last known)').length).toBeGreaterThan(0);
  });

  it('shows stale nodes and stale or stopped app widgets honestly', () => {
    render(<Harness />);
    const system = widget('System');
    expect(within(system).getByText('2 of 4 online')).toBeInTheDocument();
    expect(within(system).getByText(/Stale · 1 min ago/)).toBeInTheDocument();
    const energy = widget('Home Assistant · Energy today');
    expect(within(energy).getByText('Stale')).toBeInTheDocument();
    expect(within(energy).getByText(/should refresh every 300 s/)).toBeInTheDocument();
    const frigate = widget('Frigate · Events');
    expect(within(frigate).getByText('Unhealthy')).toBeInTheDocument();
    expect(within(frigate).getByText(/Frigate is not running/)).toBeInTheDocument();
    const hub = widget('home-hub');
    expect(within(hub).getByRole('meter', { name: 'CPU' })).toHaveAttribute('aria-valuenow', '23');
    expect(within(hub).getByText('12 d 5 h')).toBeInTheDocument();
  });

  it('renders loading skeletons and error states per widget, without blocking Home', async () => {
    const { container, unmount } = render(<Harness data={loadingData} />);
    expect(within(widget('Needs you')).getByRole('status')).toHaveTextContent('Loading Needs you');
    expect(screen.getByText('Loading apps')).toBeInTheDocument();
    await noAxeViolations(container);
    unmount();
    render(<Harness data={errorData} />);
    expect(within(widget('Backups')).getByRole('alert')).toHaveTextContent('The backup agent is not running on home-hub.');
    expect(within(widget('Uptime Kuma · Monitors')).getByText('invalid_payload')).toBeInTheDocument();
    expect(within(widget('Updates')).getByText('3 available')).toBeInTheDocument();
  });

  it('a fresh box shows calm empty states and how to get apps', () => {
    render(<Harness data={freshData} start={{ version: 1, widgets: [{ id: 'w-approvals', kind: 'approvals', size: 'M' }, { id: 'w-u', kind: 'updates', size: 'S' }, { id: 'w-b', kind: 'backups', size: 'S' }], pinned: [] }} />);
    expect(screen.getByText('Nothing needs you')).toBeInTheDocument();
    expect(screen.getByText('Everything is up to date')).toBeInTheDocument();
    expect(screen.getByText('No backups set up')).toBeInTheDocument();
    expect(screen.getByText('No apps yet')).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Dock' })).not.toBeInTheDocument();
  });

  it('opens the command palette from the search bar and Ctrl/Cmd+K', async () => {
    const onOpenSearch = vi.fn();
    render(<Harness onOpenSearch={onOpenSearch} />);
    await userEvent.click(screen.getByRole('button', { name: /Search apps, nodes and settings/ }));
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });
    fireEvent.keyDown(document, { key: 'K', metaKey: true });
    expect(onOpenSearch).toHaveBeenCalledTimes(3);
  });
});

describe('editing Home', () => {
  it('moves with arrow keys and buttons, resizes and removes, announcing each change', async () => {
    const saved = vi.fn();
    const { container } = render(<Harness onSaved={saved} />);
    await userEvent.click(screen.getByRole('button', { name: 'Edit Home' }));
    expect(screen.getByRole('button', { name: 'Done' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('button', { name: /Remove Needs you/ })).not.toBeInTheDocument();
    expect(screen.getByText('GET /v1/actions?state=awaiting_approval')).toBeInTheDocument();
    await noAxeViolations(container);

    const handle = screen.getByRole('button', { name: /Move Updates\. Use arrow keys/ });
    handle.focus();
    await userEvent.keyboard('{ArrowLeft}');
    expect(saved.mock.lastCall![0].widgets.map((w: { id: string }) => w.id).slice(0, 3)).toEqual(['w-approvals', 'w-updates', 'w-system']);
    expect(screen.getByText('Updates moved to position 2 of 12.')).toBeInTheDocument();
    await userEvent.keyboard('{ArrowLeft}');
    expect(saved.mock.lastCall![0].widgets[1].id).toBe('w-updates');

    await userEvent.click(screen.getByRole('button', { name: 'Move Backups later' }));
    expect(saved.mock.lastCall![0].widgets.findIndex((w: { id: string }) => w.id === 'w-backups')).toBe(4);

    const sizes = screen.getByRole('group', { name: 'Size of Network' });
    await userEvent.click(within(sizes).getByRole('radio', { name: 'Large' }));
    expect(saved.mock.lastCall![0].widgets.find((w: { id: string }) => w.id === 'w-mesh').size).toBe('L');
    expect(screen.getByText('Network is now large.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Remove Network from Home' }));
    expect(screen.queryByRole('region', { name: 'Network' })).not.toBeInTheDocument();
  });

  it('drag and drop reorders widgets', () => {
    const saved = vi.fn();
    render(<Harness onSaved={saved} initialEditing />);
    const cells = Array.from(screen.getByRole('list', { name: 'Widgets' }).children) as HTMLElement[];
    const dt = { data: '', setData(_t: string, v: string) { this.data = v; }, getData() { return this.data; }, effectAllowed: '' };
    fireEvent.dragStart(cells[5]!, { dataTransfer: dt });
    fireEvent.dragOver(cells[1]!, { dataTransfer: dt });
    fireEvent.drop(cells[1]!, { dataTransfer: dt });
    expect(saved.mock.lastCall![0].widgets[1].id).toBe('w-mesh');
    // The locked widget is never a drop target.
    fireEvent.dragStart(cells[3]!, { dataTransfer: dt });
    fireEvent.drop(cells[0]!, { dataTransfer: dt });
    expect(saved.mock.lastCall![0].widgets[0].id).toBe('w-approvals');
  });

  it('adds widgets from the gallery, including app widgets from manifests', async () => {
    const start: HomeLayout = { version: 1, widgets: [{ id: 'w-approvals', kind: 'approvals', size: 'M' }], pinned: [] };
    const saved = vi.fn();
    render(<Harness start={start} onSaved={saved} initialEditing />);
    await userEvent.click(screen.getByRole('button', { name: 'Add widget' }));
    const dialog = screen.getByRole('dialog', { name: 'Add a widget' });
    await noAxeViolations(dialog);
    expect(within(dialog).getByText('Immich · Phone backup')).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add Immich · Phone backup' }));
    expect(saved.mock.lastCall![0].widgets.at(-1)).toMatchObject({ kind: 'app', appId: 'immich', widgetId: 'library' });
    expect(within(dialog).getAllByText('On Home').length).toBe(1);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add System, pi-garage' }));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    expect(screen.getByRole('region', { name: 'pi-garage' })).toBeInTheDocument();
  });

  it('pins apps to the dock and reorders the dock', async () => {
    const saved = vi.fn();
    render(<Harness start={{ ...demoLayout, pinned: [] }} onSaved={saved} initialEditing />);
    const dock = screen.getByRole('navigation', { name: 'Dock' });
    expect(within(dock).getByText(/Pin apps from/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Dock Jellyfin' }));
    await userEvent.click(screen.getByRole('button', { name: 'Dock Immich' }));
    expect(screen.getByRole('button', { name: 'In dock Jellyfin' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(within(dock).getByRole('button', { name: 'Move Immich left in the dock' }));
    expect(saved.mock.lastCall![0].pinned).toEqual(['immich', 'jellyfin']);
    const links = within(dock).getAllByRole('link');
    expect(links[0]).toHaveAccessibleName('Immich, Running');
    expect(links[1]).toHaveAccessibleName('Jellyfin, Running');
    expect(links[2]).toHaveAccessibleName('All apps');
  });
});

describe('Your apps', () => {
  it('lists installed apps by category with status in words, and filters', async () => {
    render(<Harness />);
    const grid = screen.getByRole('list', { name: 'Installed apps' });
    expect(within(grid).getAllByRole('listitem')).toHaveLength(13); // 12 installed + Get apps
    const ha = within(grid).getByRole('link', { name: /Home Assistant/ });
    expect(ha).toHaveTextContent('Running');
    expect(ha).toHaveAccessibleName(expect.stringContaining('update 2026.11.2 available'));
    expect(ha).toHaveAttribute('href', 'https://home-assistant.home-hub.example');
    expect(within(grid).getByRole('link', { name: /Vaultwarden/ })).toHaveAttribute('href', '#/app/vaultwarden');
    expect(within(grid).getByRole('link', { name: /Frigate/ })).toHaveTextContent('Unhealthy');

    const cats = screen.getByRole('group', { name: 'Category' });
    // Legacy slugs from main are mapped: home-automation -> Home & IoT, security -> Network & Security.
    await userEvent.click(within(cats).getByRole('button', { name: /Home & IoT/ }));
    expect(within(screen.getByRole('list', { name: 'Installed apps' })).getAllByRole('link').map((a) => a.querySelector('.omh-app-name')?.textContent)).toEqual(['Home Assistant', 'Frigate']);
    await userEvent.click(within(cats).getByRole('button', { name: /^All/ }));

    const src = screen.getByRole('group', { name: 'Where apps come from' });
    await userEvent.click(within(src).getByRole('button', { name: 'Your own' }));
    const own = within(screen.getByRole('list', { name: 'Installed apps' })).getAllByRole('link');
    expect(own).toHaveLength(1);
    expect(own[0]).toHaveTextContent('Your own');
    await userEvent.click(within(src).getByRole('button', { name: 'System' }));
    expect(within(screen.getByRole('list', { name: 'Installed apps' })).getByRole('link')).toHaveTextContent('Backups');
    await userEvent.click(within(cats).getByRole('button', { name: /Media/ }));
    expect(screen.getByText(/No installed apps match/)).toBeInTheDocument();
    await act(async () => userEvent.click(screen.getByRole('button', { name: 'Show all apps' })));
    expect(within(screen.getByRole('list', { name: 'Installed apps' })).getAllByRole('listitem')).toHaveLength(13);
  });
});
