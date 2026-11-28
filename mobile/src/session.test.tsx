// SPDX-License-Identifier: Apache-2.0
import { act, renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import * as SecureStore from 'expo-secure-store';
import { Features, HttpApi, OP, type FetchLike } from './api/client';
import type { InboxItem, Me } from './api/types';
import { inboxAlerts } from './lib/alerts';
import { insecureHub } from './screens/ConnectScreen';
import { abilitiesFromMe, buildSession, localAccountKey, SessionProvider, useSession } from './session';
import { v0Api } from './test/fakes';
import { mockApi, mockConnection } from './test/mockHub';
import type { Connection } from './storage';
import { loadConnection, saveConnection, clearConnection } from './storage';
import * as localDb from './device/localDb';

jest.mock('./device/localDb', () => ({
  activateLocalDatabases: jest.fn(async () => undefined),
  lockLocalDatabases: jest.fn(async () => undefined),
  resumeLocalDatabases: jest.fn(async () => undefined),
  wipeLocalDatabases: jest.fn(async () => undefined),
}));

beforeEach(() => jest.clearAllMocks());


describe('session', () => {
  it('wipes app databases before clearing the sign-in', async () => {
    const wipe = jest.spyOn(localDb, 'wipeLocalDatabases').mockResolvedValue(undefined);
    const clear = jest.fn(async () => expect(wipe).toHaveBeenCalledTimes(1));
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save: async () => undefined, clear, makeApi: mockApi }}>
        {children}
      </SessionProvider>
    );
    try {
      const { result } = await renderHook(() => useSession(), { wrapper });
      await act(async () => { await result.current.connect(mockConnection('owner-demo')); });
      await act(async () => { await result.current.disconnect(); });
      expect(clear).toHaveBeenCalledTimes(1);
      expect(result.current.session).toBeNull();
    } finally {
      wipe.mockRestore();
    }
  });

  it('clears the credentials and signs out even when the database wipe fails', async () => {
    jest.mocked(localDb.wipeLocalDatabases).mockRejectedValueOnce(new Error('disk error'));
    const clear = jest.fn(async () => undefined);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save: async () => undefined, clear, makeApi: mockApi }}>
        {children}
      </SessionProvider>
    );
    const { result, unmount } = await renderHook(() => useSession(), { wrapper });
    await act(async () => { await result.current.connect(mockConnection('owner-demo')); });
    await act(async () => { await result.current.disconnect(); });
    expect(clear).toHaveBeenCalledTimes(1);
    expect(result.current.session).toBeNull();
    await unmount();
    jest.mocked(localDb.resumeLocalDatabases).mockClear();
    await renderHook(() => useSession(), { wrapper });
    expect(localDb.resumeLocalDatabases).toHaveBeenCalledWith(undefined);
  });

  it('saves the connection only after the hub accepts the token', async () => {
    const save = jest.fn(async (_c: Connection) => undefined);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save, clear: async () => undefined, makeApi: mockApi }}>{children}</SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => {
      await expect(result.current.connect(mockConnection('wrong'))).rejects.toMatchObject({ code: 'unauthenticated' });
    });
    expect(save).not.toHaveBeenCalled();
    expect(result.current.session).toBeNull();
    await act(async () => {
      await result.current.connect(mockConnection('owner-demo'));
    });
    expect(save).toHaveBeenCalledWith({ ...mockConnection('owner-demo'), localAccount: JSON.stringify(['3f9c2a1b7d4e', 'person', 'owner']) });
    expect(result.current.session?.canDecide).toBe('yes');
  });

  it('activates local data with the hub node and principal after /v1/me, and different people get different keys', async () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save: async () => undefined, clear: async () => undefined, makeApi: mockApi }}>{children}</SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => { await result.current.connect(mockConnection('owner-demo')); });
    await act(async () => { await result.current.connect(mockConnection('adult-demo')); });
    expect(jest.mocked(localDb.activateLocalDatabases).mock.calls).toEqual([
      [JSON.stringify(['3f9c2a1b7d4e', 'person', 'owner'])],
      [JSON.stringify(['3f9c2a1b7d4e', 'person', 'alex'])],
    ]);
    expect(localDb.lockLocalDatabases).not.toHaveBeenCalled();
  });

  it('keeps the same key for the same person after expire() and signing in again', async () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save: async () => undefined, clear: async () => undefined, makeApi: mockApi }}>{children}</SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => { await result.current.connect(mockConnection('owner-demo')); });
    await act(async () => { await result.current.expire(); });
    expect(localDb.lockLocalDatabases).toHaveBeenCalledTimes(1);
    expect(localDb.wipeLocalDatabases).not.toHaveBeenCalled();
    await act(async () => { await result.current.connect(mockConnection('owner-demo')); });
    const keys = jest.mocked(localDb.activateLocalDatabases).mock.calls.map(([k]) => k);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('locks local data when the hub gives no /v1/me or no node id, and never falls back to the URL', async () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save: async () => undefined, clear: async () => undefined, makeApi: () => v0Api() }}>{children}</SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => { await result.current.connect(mockConnection('tok')); });
    expect(localDb.activateLocalDatabases).not.toHaveBeenCalled();
    expect(localDb.lockLocalDatabases).toHaveBeenCalledTimes(1);
    expect(localAccountKey('', { kind: 'person', id: 'owner' })).toBeUndefined();
    expect(localAccountKey(undefined, { kind: 'person', id: 'owner' })).toBeUndefined();
  });

  it('leaves local data alone when the hub refuses the token', async () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save: async () => undefined, clear: async () => undefined, makeApi: mockApi }}>{children}</SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => { await expect(result.current.connect(mockConnection('wrong'))).rejects.toBeDefined(); });
    expect(localDb.activateLocalDatabases).not.toHaveBeenCalled();
    expect(localDb.lockLocalDatabases).not.toHaveBeenCalled();
    expect(localDb.wipeLocalDatabases).not.toHaveBeenCalled();
  });

  it('a sign-in saved before local data existed gets its key at startup, activates, and is saved', async () => {
    const save = jest.fn(async (_c: Connection) => undefined);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => mockConnection('owner-demo'), save, clear: async () => undefined, makeApi: mockApi }}>{children}</SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    const key = JSON.stringify(['3f9c2a1b7d4e', 'person', 'owner']);
    await waitFor(() => expect(localDb.activateLocalDatabases).toHaveBeenCalledWith(key));
    await waitFor(() => expect(save).toHaveBeenCalledWith({ ...mockConnection('owner-demo'), localAccount: key }));
    await waitFor(() => expect(result.current.session?.connection.localAccount).toBe(key));
  });

  it('a stored key is not recomputed at startup', async () => {
    const stored = { ...mockConnection('owner-demo'), localAccount: 'k' };
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => stored, save: async () => undefined, clear: async () => undefined, makeApi: mockApi }}>{children}</SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.session?.canDecide).toBe('yes'));
    expect(localDb.resumeLocalDatabases).toHaveBeenCalledWith('k');
    expect(localDb.activateLocalDatabases).not.toHaveBeenCalled();
  });

  it('a failed clear() keeps the signed-in screen so the error can be shown, and Disconnect can be retried', async () => {
    jest.mocked(localDb.wipeLocalDatabases).mockResolvedValue(undefined);
    const clear = jest.fn().mockRejectedValueOnce(new Error('keystore')).mockResolvedValue(undefined);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save: async () => undefined, clear, makeApi: mockApi }}>{children}</SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => { await result.current.connect(mockConnection('owner-demo')); });
    await act(async () => { await expect(result.current.disconnect()).rejects.toThrow('keystore'); });
    expect(result.current.session).not.toBeNull();
    await act(async () => { await result.current.disconnect(); });
    expect(clear).toHaveBeenCalledTimes(2);
    expect(result.current.session).toBeNull();
  });

  it('connects but does not remember when the secure store refuses (never falls back to plain storage)', async () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save: async () => { throw new Error('-34018'); }, clear: async () => undefined, makeApi: mockApi }}>
        {children}
      </SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => {
      await result.current.connect(mockConnection('owner-demo'));
    });
    expect(result.current.session?.remembered).toBe(false);
  });

  it('a demo connection stored by an older build loads as signed out', async () => {
    await SecureStore.setItemAsync('onemind.connection.v1', JSON.stringify({ mode: 'mock', token: 'owner-demo' }));
    expect(await loadConnection()).toBeNull();
    // The whole provider, with its real secure-store loader: the app starts at Connect.
    const wrapper = ({ children }: { children: ReactNode }) => <SessionProvider>{children}</SessionProvider>;
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(result.current.ready).toBe(true);
    expect(result.current.session).toBeNull();
    await clearConnection();
  });

  it('the app builds only the HTTP client; who you are comes from the hub, never from a demo token', () => {
    const s = buildSession({ mode: 'live', hubUrl: 'https://hub.example', token: 'owner-demo' });
    expect(s.api).toBeInstanceOf(HttpApi);
    expect(s.principal).toBeUndefined();
    expect(s.canDecide).toBe('unknown');
    expect(s.label).toBe('hub.example');
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


const me = (over: Partial<Me['principal']>, caps: string[] = [], scopes: string[] = []): Me => ({
  principal: { id: 'p', kind: 'person', role: 'owner', ...over },
  token: { id: 't', scopes, expires_at: null },
  session: null,
  passkeys: 1,
  capabilities: caps,
});

describe('identity (§12.6)', () => {
  it('takes abilities from /v1/me, treating unknown roles as least privileged', () => {
    expect(abilitiesFromMe(me({}, ['can_approve']))).toEqual({ canDecide: 'yes', canRequest: 'yes' });
    expect(abilitiesFromMe(me({ role: 'adult' }, [], ['actions:request']))).toEqual({ canDecide: 'no', canRequest: 'yes' });
    expect(abilitiesFromMe(me({ role: 'child' }))).toEqual({ canDecide: 'no', canRequest: 'no' });
    expect(abilitiesFromMe(me({ kind: 'agent', role: 'agent' }, [], ['actions:request:app.install'])).canDecide).toBe('no');
  });

  it('reads features and /v1/me after connecting, so the role is known before any 403', async () => {
    const api = v0Api({
      features: async () => new Features([OP.me], 'openapi'),
      me: async () => me({ id: 'ana', role: 'adult' }, []),
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider deps={{ load: async () => null, save: async () => undefined, clear: async () => undefined, makeApi: () => api }}>{children}</SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => {
      await result.current.connect({ mode: 'live', hubUrl: 'https://hub.example', token: 't' });
    });
    expect(result.current.session?.principal).toEqual({ id: 'ana', kind: 'person', role: 'adult' });
    expect(result.current.session?.canDecide).toBe('no');
    expect(result.current.session?.features.has(OP.me)).toBe(true);
  });

  it('renews an expired passkey session with the refresh token and saves the new one', async () => {
    const saved: Connection[] = [];
    const fn: FetchLike = async (url, init) => {
      const auth = (init?.headers as Record<string, string>)?.Authorization;
      if (url.endsWith('/openapi.json')) return new Response(JSON.stringify({ paths: { '/v1/auth/refresh': { post: {} } } }), { status: 200 });
      if (url.endsWith('/v1/auth/refresh'))
        return new Response(JSON.stringify({ access_token: 'fresh', expires_at: '2030-01-01T00:00:00Z', refresh_token: 'r2' }), { status: 200 });
      if (auth === 'Bearer fresh') return new Response(JSON.stringify({ name: 'Home', version: '1', hub_node_id: 'h' }), { status: 200 });
      return new Response(JSON.stringify({ error: 'unauthenticated', message: 'expired' }), { status: 401 });
    };
    const start: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 'old', auth: 'passkey', refreshToken: 'r1' };
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider
        deps={{
          load: async () => start,
          save: async (c) => void saved.push(c),
          clear: async () => undefined,
          makeApi: (c, tokens) => new HttpApi({ tokens, baseUrl: (c as { hubUrl: string }).hubUrl, fetchFn: fn }),
        }}
      >
        {children}
      </SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    await act(async () => {
      await expect(result.current.session!.api.instance()).resolves.toMatchObject({ name: 'Home' });
    });
    expect(saved.at(-1)).toMatchObject({ token: 'fresh', refreshToken: 'r2', auth: 'passkey' });
    expect(result.current.session?.connection).toMatchObject({ token: 'fresh' });
  });

  it('renews even when the hub routes were not known yet at start (first /openapi.json read failed)', async () => {
    let openapiCalls = 0;
    const fn: FetchLike = async (url, init) => {
      const auth = (init?.headers as Record<string, string>)?.Authorization;
      if (url.endsWith('/openapi.json'))
        return ++openapiCalls === 1
          ? new Response('busy', { status: 503 })
          : new Response(JSON.stringify({ paths: { '/v1/auth/refresh': { post: {} } } }), { status: 200 });
      if (url.endsWith('/v1/auth/refresh')) return new Response(JSON.stringify({ access_token: 'fresh', expires_at: 'x' }), { status: 200 });
      if (auth === 'Bearer fresh') return new Response(JSON.stringify({ name: 'Home', version: '1', hub_node_id: 'h' }), { status: 200 });
      return new Response(JSON.stringify({ error: 'unauthenticated', message: 'expired' }), { status: 401 });
    };
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider
        deps={{
          load: async () => ({ mode: 'live', hubUrl: 'https://hub.example', token: 'old', auth: 'passkey', refreshToken: 'r1' }),
          save: async () => undefined,
          clear: async () => undefined,
          makeApi: (c, tokens) => new HttpApi({ tokens, baseUrl: (c as { hubUrl: string }).hubUrl, fetchFn: fn }),
        }}
      >
        {children}
      </SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(result.current.session?.features.source).toBe('unknown');
    await act(async () => {
      await expect(result.current.session!.api.instance()).resolves.toMatchObject({ name: 'Home' });
    });
    expect(openapiCalls).toBe(2);
  });

  it('an expired sign-in returns to Connect with the hub address kept', async () => {
    const clear = jest.fn(async () => undefined);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SessionProvider
        deps={{ load: async () => ({ mode: 'live', hubUrl: 'https://hub.example', token: 't', auth: 'passkey' }), save: async () => undefined, clear, makeApi: () => v0Api() }}
      >
        {children}
      </SessionProvider>
    );
    const { result } = await renderHook(() => useSession(), { wrapper });
    await act(async () => {
      await result.current.expire();
    });
    expect(result.current.session).toBeNull();
    expect(result.current.expiredHub).toBe('https://hub.example');
    expect(clear).toHaveBeenCalled();
    expect(localDb.lockLocalDatabases).toHaveBeenCalledTimes(1);
    expect(localDb.wipeLocalDatabases).not.toHaveBeenCalled();
  });
});

describe('inbox notifications', () => {
  const item = (id: string, read = false, action_id?: string, topic = 'apps'): InboxItem => ({
    id,
    severity: 'info',
    topic,
    title: `t${id}`,
    body: 'b',
    link: null,
    source: 's',
    action_id,
    created_at: '2026-11-12T00:00:00Z',
    read_at: read ? '2026-11-12T00:00:01Z' : null,
  });
  it('raises nothing on the first refresh, then only new unread items; approvals open the Approvals tab', () => {
    expect(inboxAlerts(undefined, [item('1')])).toEqual([]);
    const out = inboxAlerts(new Set(['1']), [item('1'), item('2'), item('3', true), item('4', false, 'act-1', 'approvals')]);
    expect(out.map((a) => [a.id, a.route])).toEqual([
      ['ntf:2', 'inbox'],
      ['ntf:4', 'approvals'],
    ]);
  });
});
