// SPDX-License-Identifier: Apache-2.0
import { renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { INSTANCE } from './api/fixtures';
import { ApiError } from './api/types';
import { HubDataProvider, useHubData } from './data';
import { SessionProvider, useSession } from './session';
import { v0Api } from './test/fakes';
import type { Connection } from './storage';

const forbidden = () => Promise.reject(new ApiError(403, 'permission_denied', 'missing scope'));
const LIVE: Connection = { mode: 'live', hubUrl: 'https://onemind.local:8443', token: 't' };

function wrap(api: ReturnType<typeof v0Api>, clear: jest.Mock) {
  function Gate({ children }: { children: ReactNode }) {
    const { session } = useSession();
    return session ? <HubDataProvider intervalMs={0}>{children}</HubDataProvider> : null;
  }
  return ({ children }: { children: ReactNode }) => (
    <SessionProvider deps={{ load: async () => LIVE, save: async () => undefined, clear, makeApi: () => api }}>
      <Gate>{children}</Gate>
    </SessionProvider>
  );
}

describe('hub data for a person with few scopes (§12.6 role defaults)', () => {
  it('a child without nodes:read or actions:read still sees the instance and shared apps, with no error and no sign-out', async () => {
    const clear = jest.fn(async () => undefined);
    const api = v0Api({ nodes: forbidden, actions: forbidden });
    const { result } = await renderHook(() => useHubData(), { wrapper: wrap(api, clear) });
    await waitFor(() => expect(result.current?.loading).toBe(false));
    expect(result.current.instance).toEqual(INSTANCE);
    expect(result.current.apps?.length).toBeGreaterThan(0);
    expect(result.current.nodes).toBeUndefined();
    expect(result.current.actions).toBeUndefined();
    expect(result.current.error).toBeUndefined();
    expect(result.current.pendingCount).toBe(0);
    expect(clear).not.toHaveBeenCalled();
  });

  it('any other failure still marks the refresh as failed', async () => {
    const clear = jest.fn(async () => undefined);
    const api = v0Api({ nodes: () => Promise.reject(new ApiError(503, 'unavailable', 'starting')) });
    const { result } = await renderHook(() => useHubData(), { wrapper: wrap(api, clear) });
    await waitFor(() => expect(result.current?.loading).toBe(false));
    expect(result.current.error?.code).toBe('unavailable');
  });
});
