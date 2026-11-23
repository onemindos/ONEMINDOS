// SPDX-License-Identifier: Apache-2.0
// What the phone bundle gets for sdk/ts/src/nodeca.ts (see metro.config.js). That file pins the box CA
// through Node's https module, which React Native does not have; on the phone the OS trust store and
// the app's own network rules decide, so nothing may call this.
export function caFetch(_ca: string): typeof fetch {
  return () => Promise.reject(new Error('onemind: a pinned CA (ONEMIND_GATEWAY_CA) is a Node-only option'));
}
