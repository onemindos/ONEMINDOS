// SPDX-License-Identifier: Apache-2.0
// Yjs -> lib0 picks `webcrypto.react-native.cjs` under Metro's "react-native" condition, and that file requires
// isomorphic-webcrypto (last release 2022, wants the removed expo-random). We answer that one import with the
// platform CSPRNG from expo-crypto, which is all lib0 uses it for (random ids). Wired in metro.config.js and jest.
const { getRandomBytes } = require('expo-crypto');

function getRandomValues(view) {
  const bytes = getRandomBytes(view.byteLength);
  new Uint8Array(view.buffer, view.byteOffset, view.byteLength).set(bytes);
  return view;
}

module.exports = { ensureSecure() {}, subtle: undefined, getRandomValues };
