// SPDX-License-Identifier: Apache-2.0
// Test helpers: a gateway fake that serves only the §3 routes (a v0 box), with overrides per test.
import { Features, type OneMindApi } from '../api/client';
import { INSTANCE, makeActions, makeApps, makeNodes } from '../api/fixtures';
import { ApiError } from '../api/types';

const missing = () => Promise.reject(new ApiError(404, 'not_found', 'not on this gateway'));

export function v0Api(over: Partial<OneMindApi> = {}, now = Date.now()): OneMindApi {
  return {
    healthz: async () => ({ ok: true }),
    instance: async () => INSTANCE,
    nodes: async () => makeNodes(now),
    node: async () => makeNodes(now)[0]!,
    apps: async () => makeApps(now),
    actions: async () => makeActions(now),
    action: async () => makeActions(now)[0]!,
    createAction: async () => makeActions(now)[0]!,
    approve: async () => ({ ...makeActions(now)[0]!, state: 'succeeded' }),
    deny: async () => ({ ...makeActions(now)[0]!, state: 'cancelled' }),
    hubOffsetMs: () => 0,
    features: async () => Features.none(),
    me: missing,
    approveOptions: missing,
    preview: missing,
    notifications: missing,
    notification: missing,
    markRead: missing,
    markAllRead: missing,
    alerts: missing,
    ackAlert: missing,
    fixAlert: missing,
    pushRegister: missing,
    pushRegistrations: missing,
    pushUnregister: missing,
    vapidPublicKey: missing,
    loginOptions: missing,
    login: missing,
    refreshSession: missing,
    logout: async () => undefined,
    passkeyRegisterOptions: missing,
    passkeyRegister: missing,
    deviceRequest: missing,
    deviceRequestStatus: missing,
    deviceToken: missing,
    eventsEndpoint: () => undefined,
    ...over,
  };
}
