// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { MachineFitDetails } from './AppMachineFit';

it('groups the hub and workers and labels all four verdicts with words', () => {
  render(<MachineFitDetails hubID="hub" nameFor={(id) => id}
    report={{ passing_nodes: ['hub', 'slow'], nodes: [
      { node_id: 'hub', verdict: 'yes', reasons: [] },
      { node_id: 'slow', verdict: 'yes-but-slow', reasons: ['No accelerator'] },
      { node_id: 'small', verdict: 'not-on-this-machine', reasons: ['Needs more memory'] },
      { node_id: 'old', verdict: 'not-checked', reasons: ['VRAM unreported'] },
    ] }} />);
  expect(screen.getByRole('heading', { name: 'This machine' })).toBeVisible();
  expect(screen.getByRole('heading', { name: 'Other machines' })).toBeVisible();
  const rows = screen.getAllByRole('listitem').filter((row) => row.querySelector('strong'));
  expect(within(rows[0]!).getByText('Runs here')).toBeVisible();
  expect(within(rows[1]!).getByText('Runs with limits')).toBeVisible();
  expect(within(rows[2]!).getByText('Does not fit')).toBeVisible();
  expect(within(rows[3]!).getByText('Not checked')).toBeVisible();
});
