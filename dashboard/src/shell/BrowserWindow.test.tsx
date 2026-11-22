// SPDX-License-Identifier: Apache-2.0
// #692: the browser window frames only the person's own browser host, Close stops the pod and keeps
// the profile, Reset profile only files a request for an owner.
import { act, fireEvent, render, screen } from '@testing-library/react';
import { ToastProvider } from '@onemind/ui';
import { vi } from 'vitest';
import { checkBrowser, type BrowserSession } from '../api/client';
import type { Action } from '../api/types';
import { BrowserWindowView } from './BrowserWindow';
import screenDef from '../screens/browser/screen';
import { href } from './routes';

const PK = 'ab'.repeat(8);
const SESSION: BrowserSession = { app_id: 'firefox', person_key: PK, url: `https://firefox--${PK}.onemind.local/`, profile: `profile-${PK}`, state: 'starting', password: 'own-member-password' };

function fakeApi() {
  return {
    openAppSession: vi.fn(async () => undefined),
    openBrowser: vi.fn(async () => SESSION),
    closeBrowser: vi.fn(async () => ({ ...SESSION, state: 'stopped' as const })),
    resetBrowserProfile: vi.fn(async () => ({ id: 'a1', type: 'browser.profile.reset', state: 'awaiting_approval' }) as unknown as Action),
  };
}

describe('browser window (#692)', () => {
  it('signs in for app hosts, then frames the person’s own browser host', async () => {
    const api = fakeApi();
    render(<ToastProvider><BrowserWindowView appId="firefox" name="Firefox" api={api} onClosed={() => {}} /></ToastProvider>);
    const frame = await screen.findByTitle('Firefox, your profile');
    expect(frame.getAttribute('src')).toBe(SESSION.url);
    expect(api.openAppSession.mock.invocationCallOrder[0]).toBeLessThan(api.openBrowser.mock.invocationCallOrder[0]!);
    expect(api.openBrowser).toHaveBeenCalledWith('firefox');
    expect(screen.getByLabelText('Your browser password').textContent).toBe('own-member-password');
  });

  it('Close stops the pod and leaves the window; Reset profile only asks the owner', async () => {
    const api = fakeApi();
    const onClosed = vi.fn();
    render(<ToastProvider><BrowserWindowView appId="firefox" name="Firefox" api={api} onClosed={onClosed} /></ToastProvider>);
    await screen.findByTitle('Firefox, your profile');
    fireEvent.click(screen.getByRole('button', { name: 'Reset profile…' }));
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Ask the owner' })); });
    expect(api.resetBrowserProfile).toHaveBeenCalledWith('firefox');
    expect(await screen.findByText(/only after an owner approves/)).toBeTruthy();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Close' })); });
    expect(api.closeBrowser).toHaveBeenCalledWith('firefox');
    expect(onClosed).toHaveBeenCalled();
  });

  it('says why when the gateway refuses, and frames nothing', async () => {
    const api = { ...fakeApi(), openBrowser: vi.fn(async () => { throw new Error('only a signed-in person opens their own browser'); }) };
    render(<ToastProvider><BrowserWindowView appId="firefox" name="Firefox" api={api} onClosed={() => {}} /></ToastProvider>);
    expect((await screen.findByRole('alert')).textContent).toContain('only a signed-in person');
    expect(screen.queryByTitle('Firefox, your profile')).toBeNull();
  });

  it('refuses a session for another app or another host', () => {
    expect(checkBrowser(SESSION, 'firefox')).toBe(SESSION);
    expect(() => checkBrowser(SESSION, 'chromium')).toThrow();
    expect(() => checkBrowser({ ...SESSION, url: 'https://evil.example/' }, 'firefox')).toThrow();
    expect(() => checkBrowser({ ...SESSION, password: 7 as unknown as string }, 'firefox')).toThrow();
    expect(() => checkBrowser({ ...SESSION, url: `javascript:alert(1)//firefox--${PK}` }, 'firefox')).toThrow();
  });

  it('is a routed, hidden window at /browser/:appId', () => {
    expect(screenDef).toMatchObject({ id: 'browser', path: '/browser/:appId', hidden: true });
    expect(href.browser('firefox')).toBe('/browser/firefox');
  });
});
