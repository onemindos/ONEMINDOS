// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CustomizeProvider, LocalPreferencesStore } from '@onemind/ui';
import { afterEach, expect, it } from 'vitest';
import { SettingsAccessibility } from './SettingsAccessibility';

afterEach(() => { window.localStorage.clear(); document.documentElement.removeAttribute('data-om-motion'); });

it('offers only motion choices that work, and Reduce motion reaches the page', async () => {
  const user = userEvent.setup();
  render(<CustomizeProvider store={new LocalPreferencesStore({ storage: window.localStorage })}><SettingsAccessibility /></CustomizeProvider>);
  expect(screen.getAllByRole('radio', { name: /motion|system/i }).map((r) => r.parentElement?.textContent?.trim())).toEqual(['Follow system', 'Reduce motion']);
  expect(screen.queryByText(/Full motion/)).toBeNull();
  await user.click(screen.getByRole('radio', { name: /Reduce motion/ }));
  await waitFor(() => expect(document.documentElement).toHaveAttribute('data-om-motion', 'reduce'));
});
