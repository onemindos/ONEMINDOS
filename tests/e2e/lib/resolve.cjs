// SPDX-License-Identifier: Apache-2.0
// Test-only name mapping (preloaded with NODE_OPTIONS=--require by tests/e2e/harness/run.sh).
//
// The hub's HTTPS certificate is for the box's names (onemind.local, <box>.local, ...), not for an
// address, and the box CA may not vouch for other names or addresses. The VM's gateway is reached
// through a forwarded port on this machine, so the harness maps onemind.local to 127.0.0.1 for this
// process only. Certificate verification stays on: the box CA is trusted through NODE_EXTRA_CA_CERTS.
//
//   E2E_RESOLVE=onemind.local=127.0.0.1
'use strict';
const dns = require('node:dns');

const map = new Map();
for (const pair of (process.env.E2E_RESOLVE || '').split(',')) {
  const [name, addr] = pair.split('=');
  if (name && addr) map.set(name.toLowerCase(), addr);
}

if (map.size > 0) {
  const orig = dns.lookup;
  dns.lookup = function lookup(hostname, options, callback) {
    const addr = map.get(String(hostname).toLowerCase());
    if (addr) {
      const cb = typeof options === 'function' ? options : callback;
      const opts = typeof options === 'object' && options !== null ? options : {};
      process.nextTick(() => (opts.all ? cb(null, [{ address: addr, family: 4 }]) : cb(null, addr, 4)));
      return {};
    }
    return orig.call(dns, hostname, options, callback);
  };
}
