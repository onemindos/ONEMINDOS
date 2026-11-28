// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { afterEach, expect, it, vi } from 'vitest';
import type { OneMindApi } from '../../api/client';
import { usePoll } from '../../lib/hooks';
import { SessionProvider, useSession, useSignedIn } from '../../session';
import { LockScreen } from './LockScreen';
import { readIdleLock, readLock, saveIdleLock, useIdleLock } from './state';

afterEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  vi.useRealTimers();
});

it('clears the credential and destroys polls while locked; only fresh sign-in restores the workspace', async () => {
  sessionStorage.setItem('onemind.token', 'original');
  const io = vi.fn().mockResolvedValue([]);
  const instance = vi.fn().mockResolvedValue({});
  const logout = vi.fn().mockResolvedValue(undefined);
  const loginPassword = vi.fn()
    .mockRejectedValueOnce(new Error('Rejected'))
    .mockResolvedValueOnce({ access_token: 'fresh' });

  function Protected() {
    const { lock } = useSignedIn();
    usePoll(io, 5);
    return <><p>Private window title</p><button onClick={() => lock({ boxName: 'Home Hub', waiting: 2 })}>Lock now</button></>;
  }
  function View() {
    const state = useSession();
    return state.locked ? <LockScreen summary={state.locked} mock={false} /> : state.session ? <Protected /> : null;
  }
  const makeApi = () => ({ instance, logout, loginPassword } as unknown as OneMindApi);
  render(
    <SessionProvider deps={{ mock: true, makeApi, knownPrincipal: () => ({ kind: 'person', role: 'owner', id: 'owner' }) }}>
      <View />
    </SessionProvider>,
  );
  expect(await screen.findByText('Private window title')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Lock now' }));
  expect(screen.queryByText('Private window title')).toBeNull();
  expect(screen.getByRole('heading', { name: 'Home Hub is locked' })).toHaveFocus();
  expect(screen.getByText('2 waiting for a decision')).toBeVisible();
  expect(sessionStorage.getItem('onemind.token')).toBeNull();
  expect(readLock()).toEqual({ boxName: 'Home Hub', waiting: 2 });
  expect(logout).toHaveBeenCalledOnce();
  const calls = io.mock.calls.length;
  const violations = await axe.run(document.querySelector('main')!, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa'] });
  expect(violations.violations).toEqual([]);
  expect(io.mock.calls).toHaveLength(calls);

  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Unlock' }));
  const username = screen.getByLabelText(/username/i);
  const password = screen.getByLabelText(/^password$/i);
  await user.type(username, 'owner');
  await user.type(password, 'test-only-password');
  fireEvent.submit(username.closest('form')!);
  expect(await screen.findByRole('alert')).toHaveTextContent('Rejected');
  expect(screen.queryByText('Private window title')).toBeNull();

  fireEvent.submit(username.closest('form')!);
  expect(await screen.findByText('Private window title')).toBeVisible();
  expect(sessionStorage.getItem('onemind.token')).toBe('fresh');
  expect(readLock()).toBeNull();
});

it('a person signed in with an access token can unlock with a fresh token, and a bad one stays locked', async () => {
  sessionStorage.setItem('onemind.token', 'original');
  const logout = vi.fn().mockResolvedValue(undefined);
  function Protected() {
    const { lock } = useSignedIn();
    return <><p>Private window title</p><button onClick={() => lock({ boxName: 'Home Hub', waiting: 0 })}>Lock now</button></>;
  }
  function View() {
    const state = useSession();
    return state.locked ? <LockScreen summary={state.locked} mock={false} /> : state.session ? <Protected /> : null;
  }
  const makeApi = () => ({ instance: vi.fn().mockResolvedValue({}), logout } as unknown as OneMindApi);
  render(
    <SessionProvider deps={{ mock: true, makeApi, knownPrincipal: () => ({ kind: 'person', role: 'owner', id: 'owner' }) }}>
      <View />
    </SessionProvider>,
  );
  expect(await screen.findByText('Private window title')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Lock now' }));
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Unlock' }));
  const token = screen.getByLabelText('Access token');
  await user.type(token, 'fresh-token');
  fireEvent.submit(token.closest('form')!);
  expect(await screen.findByText('Private window title')).toBeVisible();
  expect(sessionStorage.getItem('onemind.token')).toBe('fresh-token');
  expect(readLock()).toBeNull();
});

it('resets the idle clock on input and preserves each person’s selected timeout', () => {
  vi.useFakeTimers();
  const lock = vi.fn();
  expect(readIdleLock('owner', true)).toBe(15);
  expect(readIdleLock('adult', false)).toBe(0);
  expect(saveIdleLock('owner', 5)).toBe(true);
  expect(readIdleLock('owner', true)).toBe(5);
  expect(readIdleLock('adult', false)).toBe(0);
  renderHook(() => useIdleLock(readIdleLock('owner', true), lock));
  act(() => vi.advanceTimersByTime(4 * 60_000));
  fireEvent.keyDown(window, { key: 'Tab' });
  act(() => vi.advanceTimersByTime(4 * 60_000));
  expect(lock).not.toHaveBeenCalled();
  act(() => vi.advanceTimersByTime(60_000));
  expect(lock).toHaveBeenCalledOnce();
});

it('Atlas lock: welcomes the person back with their initials, shows the clock, the waiting count and where it signs in', async () => {
  const { initials, whereLine } = await import('./LockScreen');
  render(<LockScreen summary={{ boxName: 'Home Hub', waiting: 1, person: 'Sam Rivera' }} mock={false} />);
  expect(screen.getByRole('heading', { name: 'Welcome back, Sam Rivera' })).toHaveFocus();
  expect(screen.getByText('SR')).toHaveAttribute('aria-hidden', 'true');
  expect(screen.getByText('Home Hub is locked.')).toBeVisible();
  expect(screen.getByText('1 waiting for a decision')).toBeVisible();
  expect(document.querySelector('main time')).not.toBeNull();
  // D-034: passkeys are optional, and the screen says so instead of offering a passkey only.
  expect(screen.getByText(/your passkey, your password \(and code/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Unlock' })).toBeVisible();
  const violations = await axe.run(document.querySelector('main')!, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa'] });
  expect(violations.violations).toEqual([]);

  expect(initials('maya')).toBe('M');
  expect(initials('  Ana  María López ')).toBe('AM');
  expect(whereLine('Home', { protocol: 'http:', hostname: '127.0.0.1' })).toMatch(/on this box's own screen$/);
  expect(whereLine('Home', { protocol: 'https:', hostname: 'home.local' })).toMatch(/encrypted connection$/);
  expect(whereLine('Home', { protocol: 'http:', hostname: '192.0.2.10' })).toMatch(/not encrypted/);
  expect(whereLine('Home', { protocol: 'https:', hostname: 'home.local' })).toContain('no cloud account');
});

it('the lock snapshot keeps a display name only, trimmed, and stays valid without one', () => {
  sessionStorage.setItem('onemind.locked', JSON.stringify({ boxName: 'Home', waiting: 0, person: '  Sam  ' }));
  expect(readLock()).toEqual({ boxName: 'Home', waiting: 0, person: 'Sam' });
  sessionStorage.setItem('onemind.locked', JSON.stringify({ boxName: 'Home', waiting: 0, person: 42 }));
  expect(readLock()).toEqual({ boxName: 'Home', waiting: 0 });
  sessionStorage.setItem('onemind.locked', JSON.stringify({ boxName: 'Home', waiting: 0, person: 'x'.repeat(200) }));
  expect(readLock()?.person).toHaveLength(64);
});

it('sign-in offers the password and authenticator code beside the passkey, not hidden behind it (D-034)', async () => {
  // A browser that can use passkeys (webauthnSupported reads these two).
  vi.stubGlobal('PublicKeyCredential', function PublicKeyCredential() {});
  if (!navigator.credentials) Object.defineProperty(navigator, 'credentials', { value: {}, configurable: true });
  const { SignIn } = await import('../../pages/SignIn');
  render(
    <SessionProvider deps={{ mock: true, makeApi: () => ({ instance: vi.fn().mockResolvedValue({}) } as unknown as OneMindApi), knownPrincipal: () => undefined }}>
      <SignIn mock={false} lockedBox="Home Hub" />
    </SessionProvider>,
  );
  expect(screen.getByRole('button', { name: 'Use my passkey' })).toBeVisible();
  const username = screen.getByLabelText('Username');
  expect(username.closest('details')).toBeNull();                 // a first choice, not "other ways"
  expect(screen.getByLabelText('Authenticator code (only if you set one up)')).toHaveAttribute('inputmode', 'numeric');
  expect(screen.getByLabelText('Access token').closest('details')).not.toBeNull();
  vi.unstubAllGlobals();
});
