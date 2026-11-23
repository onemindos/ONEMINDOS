// SPDX-License-Identifier: Apache-2.0
// CI-08 (#233), the phone slice. Three guards for the one-API-client rule:
//  1. the type contract in contract.ts really catches drift (the @ts-expect-error lines fail
//     `npm run typecheck` if it stops doing so);
//  2. HttpApi sends through the generated client (`OneMind.call`) and hands it out as `.sdk`;
//  3. the bundler alias resolves the SDK source the way the phone build needs it.
import { OneMind, type components } from '@onemind/sdk';
import { HttpApi, sdkOf, type FetchLike } from './client';
import type { Agrees, Expect } from './contract';
import { MockApi } from './mock';
import { ApiError } from './types';

type Sdk = components['schemas'];
// @ts-expect-error a field the gateway no longer sends (a renamed SDK field)
type _Missing = Expect<Agrees<{ name: string; hub_node: string }, Sdk['Instance']>>;
// @ts-expect-error a field whose type changed
type _Retyped = Expect<Agrees<{ name: number }, Sdk['Instance']>>;
type _Ok = Expect<Agrees<{ name: string; version: string; hub_node_id: string }, Sdk['Instance']>>;
export type Unused = [_Missing, _Retyped, _Ok];

type Call = { url: string; headers: Record<string, string> };

function recorder(body: unknown = { name: 'Home', version: '1.0.0', hub_node_id: 'n1' }): { fn: FetchLike; calls: Call[] } {
  const calls: Call[] = [];
  const fn: FetchLike = async (url, init) => {
    calls.push({ url, headers: { ...(init?.headers as Record<string, string>) } });
    return new Response(JSON.stringify(body), { status: 200 });
  };
  return { fn, calls };
}

describe('HttpApi on @onemind/sdk', () => {
  it('sends every JSON request through OneMind.call', async () => {
    const { fn } = recorder([]);
    const api = new HttpApi({ token: 't', baseUrl: 'https://hub.test', fetchFn: fn });
    const call = jest.spyOn(api.sdk, 'call');
    await api.nodes();
    await api.healthz().catch(() => undefined);
    expect(call).toHaveBeenCalledTimes(2);
    expect(call.mock.calls[0]![0]).toMatchObject({ method: 'GET', path: '/v1/nodes', retry: false });
    expect(call.mock.calls[1]![0]).toMatchObject({ method: 'GET', path: '/healthz' });
  });

  it('exposes the generated client on the same hub, token and wire headers', async () => {
    const { fn, calls } = recorder();
    const api = new HttpApi({ token: 'tok', baseUrl: 'https://hub.test/', fetchFn: fn });
    expect(api.sdk).toBeInstanceOf(OneMind);
    expect(sdkOf(api)).toBe(api.sdk);
    const inst = await api.sdk.instance.get();
    expect(inst.hub_node_id).toBe('n1');
    expect(calls[0]!.url).toBe('https://hub.test/v1/instance');
    expect(calls[0]!.headers.Authorization).toBe('Bearer tok');
    expect(calls[0]!.headers['OneMind-API-Version']).toBe('1');
    // The internal marker that ties a request to its HttpApi call never leaves the phone.
    expect(Object.keys(calls[0]!.headers).filter((h) => /phone-call/i.test(h))).toEqual([]);
  });

  it('sends no bearer on the open routes, even through the SDK', async () => {
    const { fn, calls } = recorder({ paths: {} });
    const api = new HttpApi({ token: 'tok', baseUrl: 'https://hub.test', fetchFn: fn });
    await api.features();
    await api.loginOptions();
    expect(calls.map((c) => c.headers.Authorization)).toEqual([undefined, undefined]);
  });

  it('keeps parallel calls apart (each answer goes to the call that asked)', async () => {
    const fn: FetchLike = async (url) => {
      await new Promise((r) => setTimeout(r, url.endsWith('/v1/nodes') ? 15 : 1));
      return new Response(url.endsWith('/v1/nodes') ? '[{"node_id":"a"}]' : '[{"id":"jellyfin"}]', { status: 200 });
    };
    const api = new HttpApi({ token: 't', baseUrl: 'https://hub.test', fetchFn: fn });
    const [nodes, apps] = await Promise.all([api.nodes(), api.apps()]);
    expect(nodes[0]!.node_id).toBe('a');
    expect(apps[0]!.id).toBe('jellyfin');
  });

  it('a demo API has no generated client', () => {
    expect(sdkOf(new MockApi('owner-demo'))).toBeUndefined();
  });

  it('keeps System controls hidden: systemPlan sends nothing', async () => {
    const { fn, calls } = recorder();
    const api = new HttpApi({ token: 't', baseUrl: 'https://hub.test', fetchFn: fn });
    const e = await api.systemPlan('system.restart').catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect((e as ApiError).code).toBe('not_found');
    expect(calls).toEqual([]);
  });
});

describe('the bundler alias (metro.config.js)', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { resolveSdk, sdkSrc, nodecaStub } = require('./sdk/metro-resolver') as {
    resolveSdk: (ctx: { originModulePath: string }, name: string, platform: string | null, next: (c: unknown, n: string, p: string | null) => unknown) => unknown;
    sdkSrc: string;
    nodecaStub: string;
  };
  const next = jest.fn((_c: unknown, n: string) => ({ type: 'next', name: n }));
  const app = { originModulePath: '/repo/mobile/src/api/client.ts' };
  const inSdk = { originModulePath: `${sdkSrc}/client.ts` };

  it('points at the SDK source next to the app, and at the phone stub for the CA fetch', () => {
    expect(sdkSrc).toMatch(/[\\/]sdk[\\/]ts[\\/]src$/);
    expect(nodecaStub).toMatch(/[\\/]mobile[\\/]src[\\/]api[\\/]sdk[\\/]nodeca\.ts$/);
  });
  it('resolves @onemind/sdk to its index.ts', () => {
    expect(resolveSdk(app, '@onemind/sdk', 'android', next)).toEqual({ type: 'sourceFile', filePath: `${sdkSrc}/index.ts` });
  });
  it("reads the SDK's own ./x.js imports as the .ts files, and stubs the Node-only CA fetch", () => {
    expect(resolveSdk(inSdk, './errors.js', 'android', next)).toEqual({ type: 'next', name: './errors' });
    expect(resolveSdk(inSdk, './nodeca.js', 'android', next)).toEqual({ type: 'sourceFile', filePath: nodecaStub });
  });
  it('leaves every other import alone', () => {
    expect(resolveSdk(app, './types.js', 'android', next)).toEqual({ type: 'next', name: './types.js' });
    expect(resolveSdk(inSdk, 'react-native', 'android', next)).toEqual({ type: 'next', name: 'react-native' });
  });
});
