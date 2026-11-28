// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { DesktopHome, desktopSummary, type DesktopHomeProps } from './DesktopHome';
import type { HomeLayout } from './layout';
import type { HomeData } from './types';
import { NOW, TIME_ZONE, demoLayout, homeData, loadingData, offlineData, pending } from '../../demo/src/home/fixtures';

const START: HomeLayout = { version: 1, widgets: [{ id: 'w-approvals', kind: 'approvals', size: 'M' }, { id: 'w-system', kind: 'system', size: 'M' }], pinned: [] };

function Harness(props: Partial<DesktopHomeProps> & { start?: HomeLayout; onSaved?: (l: HomeLayout) => void }) {
  const { start = START, onSaved, data = homeData, ...rest } = props;
  const [layout, setLayout] = useState(start);
  return (
    <main>
      <DesktopHome data={data} now={NOW} timeZone={TIME_ZONE} personName="Robin" layout={layout} defaultLayout={START} canDecide={{ allowed: true }}
        onLayoutChange={(l) => { setLayout(l); onSaved?.(l); }} {...rest} />
    </main>
  );
}

describe('desktopSummary', () => {
  it('says what needs you in bold first, then what is not fine, else that everything runs', () => {
    const base = { waiting: 0, staleNodes: 0, offlineNodes: 0, unhealthyApps: 0, connecting: false, answering: true };
    expect(desktopSummary(base)).toEqual({ lead: 'Nothing needs you.', rest: 'Everything is running.' });
    expect(desktopSummary({ ...base, waiting: 3 })).toEqual({ lead: '3 requests need you.', rest: 'Everything else is running.' });
    expect(desktopSummary({ ...base, waiting: 1, staleNodes: 1, offlineNodes: 2 })).toEqual({ lead: '1 request needs you.', rest: '1 machine is late with a heartbeat and 2 machines are offline.' });
    expect(desktopSummary({ ...base, connecting: true }).lead).toBe('Connecting to the hub.');
    // A hub that is not answering never claims that everything runs.
    expect(desktopSummary({ ...base, answering: false })).toEqual({ lead: 'The hub is not answering.', rest: 'Everything here is its last known state.' });
  });
});

describe('DesktopHome', () => {
  it('is the desktop, not a page: greeting and summary, status, then the tiles; no search bar or app grid', async () => {
    const { container } = render(<Harness status={<section aria-label="Box health">ok</section>} />);
    const h1 = screen.getByRole('heading', { level: 1 });
    expect(h1.textContent).toMatch(/^Good (morning|afternoon|evening|night), Robin$/);
    expect(container.querySelector('.omd-summary strong')?.textContent).toBe(`${pending.length} requests need you.`);
    const health = screen.getByRole('region', { name: 'Box health' });
    const tiles = screen.getByRole('region', { name: 'Home tiles' });
    expect(h1.compareDocumentPosition(health) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(health.compareDocumentPosition(tiles) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Your apps' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Search apps/ })).toBeNull();
    const res = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(res.violations.map((v) => v.id)).toEqual([]);
  });

  it('gives every machine an age: fresh ones too, stale and offline with their state', () => {
    render(<Harness />);
    const machines = within(screen.getByRole('region', { name: 'System' }));
    expect(machines.getAllByTitle('Last heartbeat').length).toBeGreaterThan(0);
    expect(machines.getByText(/^Stale · /)).toBeInTheDocument();
    expect(machines.getByText(/^Offline · /)).toBeInTheDocument();
  });

  it('sends a hold action to Approvals with Review, never a one-tap Approve', () => {
    const hold = { ...pending[0]!, id: 'a-hold', hold: { duration: 2000 } };
    const data: HomeData = { ...homeData, approvals: { state: 'ready', data: [hold] } };
    render(<Harness data={data} links={{ approval: (id) => `/approvals?highlight=${id}` }} />);
    const needs = within(screen.getByRole('region', { name: /Needs you/ }));
    expect(needs.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(needs.getByText('Moves a device')).toBeInTheDocument();
    expect(needs.getByRole('link', { name: /^Review/ })).toHaveAttribute('href', '/approvals?highlight=a-hold');
  });

  it('never looks live while connecting or when the hub stopped answering', () => {
    const { unmount } = render(<Harness data={loadingData} />);
    expect(screen.getByText('Connecting to the hub.')).toBeInTheDocument();
    unmount();
    render(<Harness data={offlineData} />);
    expect(screen.getByText('The hub is not answering.')).toBeInTheDocument();
    expect(screen.getByText(/Last answer from the hub .* ago/)).toBeInTheDocument();
  });

  it('edits Home and dock together: tray adds a tile, removing sends it back, Reset keeps the dock, Done leaves', async () => {
    const u = userEvent.setup();
    const saved = vi.fn();
    render(<Harness onSaved={saved} />);
    await u.click(screen.getByRole('button', { name: 'Edit Home and dock' }));
    expect(screen.getByRole('region', { name: 'Editing Home' })).toHaveTextContent('Nothing is lost');
    const tray = within(screen.getByRole('complementary', { name: 'Add to Home' }));
    await u.click(tray.getByRole('button', { name: 'Add Backups to Home' }));
    expect(saved.mock.lastCall?.[0].widgets.map((w: { kind: string }) => w.kind)).toEqual(['approvals', 'system', 'backups']);
    expect(tray.queryByRole('button', { name: 'Add Backups to Home' })).toBeNull();
    await u.click(screen.getByRole('button', { name: 'Remove Backups from Home' }));
    expect(tray.getByRole('button', { name: 'Add Backups to Home' })).toBeInTheDocument();
    // Apps go in and out of the dock from the same tray.
    const installed = homeData.apps.state === 'ready' ? homeData.apps.data.find((a) => a.installed)! : undefined;
    const pin = tray.getByRole('button', { name: `${installed!.name} in the dock` });
    expect(pin).toHaveAttribute('aria-pressed', 'false');
    await u.click(pin);
    expect(saved.mock.lastCall?.[0].pinned).toEqual([installed!.id]);
    await u.click(screen.getByRole('button', { name: 'Add Trust to Home' }));
    await u.click(screen.getByRole('button', { name: 'Reset to default' }));
    expect(saved.mock.lastCall?.[0]).toEqual({ ...START, pinned: [installed!.id] });
    await u.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByRole('complementary', { name: 'Add to Home' })).toBeNull();
  });

  it('opens in edit mode for screenshots', () => {
    render(<Harness start={demoLayout} initialEditing />);
    expect(screen.getByRole('region', { name: 'Editing Home' })).toBeInTheDocument();
  });
});
