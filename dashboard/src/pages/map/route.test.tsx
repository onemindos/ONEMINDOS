// SPDX-License-Identifier: Apache-2.0
// The Map is reachable: /map is routed and windowed, Map is second in the dock, and on the demo gateway (which has
// no places and no asset feed) it shows the empty state, never sample assets.
import { screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { renderApp, seriousViolations } from '../../test/helpers';

const T = { timeout: 4000 };

it('opens from the dock, second after Home, with an honest empty state that passes axe', async () => {
  const { container } = renderApp({ token: 'owner-demo', route: '/map' });
  expect(await screen.findByText('Draw your first place', {}, T)).toBeVisible();
  expect(screen.getByText('No live feed in demo mode')).toBeVisible();
  const dock = within(screen.getByRole('navigation', { name: 'Main' }));
  const links = dock.getAllByRole('link').map((a) => a.getAttribute('href'));
  expect(links.indexOf('/map')).toBe(links.indexOf('/') + 1);
  expect(await seriousViolations(container)).toEqual([]);
});
