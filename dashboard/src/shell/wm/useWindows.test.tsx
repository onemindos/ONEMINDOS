// SPDX-License-Identifier: Apache-2.0
import { renderHook } from '@testing-library/react';
import { ToastProvider } from '@onemind/ui';
import type { ReactNode } from 'react';
import { MemoryRouter, useLocation } from 'react-router';
import { expect, it, vi } from 'vitest';
import { personStorage } from '../../data/prefs';
import { useWindows } from './useWindows';

vi.mock('../../session', () => ({
  useSignedIn: () => ({ principal: { id: 'owner', kind: 'person', role: 'owner' } }),
}));
vi.mock('../Shell', () => ({
  useShell: () => ({ view: 'pro', role: 'owner' }),
}));

it('restores the saved window when the desktop mounts with its router', () => {
  const rect = { x: 3, y: 3, width: 60, height: 80 };
  personStorage('owner')!.setItem('shell.windows', JSON.stringify([
    { path: '/market', rect },
    { path: '/settings/appearance', rect },
  ]));
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter><ToastProvider>{children}</ToastProvider></MemoryRouter>
  );
  const { result } = renderHook(() => ({ location: useLocation(), desktop: useWindows() }), { wrapper });
  expect(result.current.location.pathname).toBe('/settings/appearance');
  expect(result.current.desktop.active).toBe('settings');
  expect(result.current.desktop.windows.map(w => [w.path, w.minimised])).toEqual([
    ['/market', false],
    ['/settings/appearance', false],
  ]);
});
