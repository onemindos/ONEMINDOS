// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { openApp } from './openApp';

function fakeWindow() {
  const tab = { opener: 'x' as unknown, location: { href: '' }, close: vi.fn() };
  return { tab, win: { open: vi.fn(() => tab) } as unknown as Pick<Window, 'open'> };
}

describe('openApp (UMB-P02)', () => {
  it('sets the app-host sign-in cookie before the tab goes to the app', async () => {
    const { tab, win } = fakeWindow();
    const order: string[] = [];
    const api = { openAppSession: vi.fn(async () => { order.push(`session, tab at "${tab.location.href}"`); }) };
    await openApp(api, 'https://x.onemind.local/', win);
    expect(order).toEqual(['session, tab at ""']);
    expect(tab.location.href).toBe('https://x.onemind.local/');
    expect(tab.opener).toBeNull();
  });

  it('closes the tab and throws when the sign-in cookie cannot be set', async () => {
    const { tab, win } = fakeWindow();
    const api = { openAppSession: vi.fn(async () => { throw new Error('sign in first'); }) };
    await expect(openApp(api, 'https://x.onemind.local/', win)).rejects.toThrow('sign in first');
    expect(tab.close).toHaveBeenCalled();
    expect(tab.location.href).toBe('');
  });

  it('falls back to a plain open when the browser gave no tab', async () => {
    const open = vi.fn(() => null);
    await openApp({ openAppSession: async () => {} }, 'https://x.onemind.local/', { open } as unknown as Pick<Window, 'open'>);
    expect(open).toHaveBeenLastCalledWith('https://x.onemind.local/', '_blank', 'noopener');
  });
});
