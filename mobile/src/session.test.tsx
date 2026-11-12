// SPDX-License-Identifier: Apache-2.0
import { act, renderHook } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Features, HttpApi, OP, type FetchLike } from './api/client';
import type { InboxItem, Me } from './api/types';
import { inboxAlerts } from './lib/alerts';
import { insecureHub } from './screens/ConnectScreen';
import { abilitiesFromMe, SessionProvider, useSession } from './session';
import { v0Api } from './test/fakes';
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
  });
});

describe('inbox notifications', () => {
  const item = (id: string, read = false, action_id?: string): InboxItem => ({
    id,
    severity: 'info',
    topic: 'apps',
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
    const out = inboxAlerts(new Set(['1']), [item('1'), item('2'), item('3', true), item('4', false, 'act-1')]);
    expect(out.map((a) => [a.id, a.route])).toEqual([
      ['ntf:2', 'inbox'],
      ['ntf:4', 'approvals'],
    ]);
  });
});
