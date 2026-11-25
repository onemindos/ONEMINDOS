// SPDX-License-Identifier: Apache-2.0
// Test helper: the in-memory gateway (api/mock.ts) behind an ordinary hub connection. The app never
// builds MockApi (session.tsx makes only HttpApi); tests hand it in through SessionDeps.makeApi.
import type { OneMindApi } from '../api/client';
import { MockApi } from '../api/mock';
import type { SessionDeps } from '../session';
import type { Connection } from '../storage';

export const MOCK_HUB = 'https://hub.example';

export const mockConnection = (token: string): Connection => ({ mode: 'live', hubUrl: MOCK_HUB, token });

export const mockApi = (c: Connection): OneMindApi => new MockApi(c.token);

/** A session already signed in to the in-memory gateway as `token` (owner-demo, adult-demo, agent-demo). */
export function mockDeps(token: string, over: Partial<SessionDeps> = {}): SessionDeps {
  return { load: async () => mockConnection(token), save: async () => undefined, clear: async () => undefined, makeApi: mockApi, ...over };
}
