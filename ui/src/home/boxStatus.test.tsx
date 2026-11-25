// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { BoxHealth, statusRows } from './boxStatus';

it('renders an absent source or a source without an observation as unknown, never green', () => {
  const rows = statusRows({
    alerts: { state: 'ok', observed_at: null, summary: 'no alerts' },
    backups: { state: 'ok', observed_at: '2026-11-21T01:00:00Z', summary: 'backups are current' },
    updates: { state: 'critical', observed_at: '2026-11-21T01:00:00Z', summary: 'update rolled back' },
  });
  render(<BoxHealth rows={rows} links={{}} />);
  const widget = within(screen.getByRole('region', { name: 'Box health' }));
  for (const name of ['Alerts', 'Storage']) {
    const row = widget.getByText(name).closest('li')!;
    expect(within(row).getByText('Unknown')).toBeInTheDocument();
    expect(row.querySelector('.om-tone-ok')).toBeNull();
  }
  expect(widget.getByText('backups are current').closest('li')?.querySelector('.om-tone-ok')).toBeTruthy();
  expect(widget.getByText('update rolled back').closest('li')?.querySelector('.om-tone-bad')).toBeTruthy();
});
