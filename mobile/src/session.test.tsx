// SPDX-License-Identifier: Apache-2.0
import { act, renderHook } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { insecureHub } from './screens/ConnectScreen';
import { SessionProvider, useSession } from './session';
import type { Connection } from './storage';
import { loadConnection, saveConnection, clearConnection } from './storage';

describe('session', () => {
  it('saves the connection only after the hub accepts the token', async () => {
    const save = jest.fn(async (_c: Connection) => undefined);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save, clear: async () => undefined }}>{children}</SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => {
      await expect(result.current.connect({ mode: 'mock', token: 'wrong' })).rejects.toMatchObject({ code: 'unauthenticated' });
    });
    expect(save).not.toHaveBeenCalled();
    expect(result.current.session).toBeNull();
    await act(async () => {
      await result.current.connect({ mode: 'mock', token: 'owner-demo' });
    });
    expect(save).toHaveBeenCalledWith({ mode: 'mock', token: 'owner-demo' });
    expect(result.current.session?.canDecide).toBe('yes');
  });

  it('connects but does not remember when the secure store refuses (never falls back to plain storage)', async () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save: async () => { throw new Error('-34018'); }, clear: async () => undefined }}>
        {children}
      </SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => {
      await result.current.connect({ mode: 'mock', token: 'owner-demo' });
    });
    expect(result.current.session?.remembered).toBe(false);
  });

  it('round-trips through the secure store and clears', async () => {
    await saveConnection({ mode: 'live', hubUrl: 'https://hub.example', token: 'secret' });
    expect(await loadConnection()).toEqual({ mode: 'live', hubUrl: 'https://hub.example', token: 'secret' });
    await clearConnection();
    expect(await loadConnection()).toBeNull();
  });

  it('warns about plain HTTP except to this device', () => {
    expect(insecureHub('http://hub.example:8080')).toBe(true);
    expect(insecureHub('http://localhost:8080')).toBe(false);
    expect(insecureHub('https://hub.example')).toBe(false);
  });
});
