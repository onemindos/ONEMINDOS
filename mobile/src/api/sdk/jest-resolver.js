// SPDX-License-Identifier: Apache-2.0
// Jest's half of the @onemind/sdk alias (metro.config.js is the bundler's half). Two rules for files
// inside sdk/ts/src, every other import resolves exactly as before:
//  - the SDK imports its siblings as `./client.js` (TypeScript's ESM spelling): those mean the `.ts` files;
//  - a package import (the Babel helpers the transform adds) comes from the app's node_modules,
//    since sdk/ts has none of the app's packages.
const path = require('node:path');

const appRoot = path.resolve(__dirname, '../../..');
const sdkSrc = path.resolve(appRoot, '../sdk/ts/src');

module.exports = (request, options) => {
  const inSdk = options.basedir === sdkSrc || options.basedir.startsWith(sdkSrc + path.sep);
  if (!inSdk) return options.defaultResolver(request, options);
  if (request.startsWith('.')) return options.defaultResolver(request.endsWith('.js') ? request.slice(0, -'.js'.length) : request, options);
  if (path.isAbsolute(request)) return options.defaultResolver(request, options);
  return options.defaultResolver(request, { ...options, basedir: appRoot });
};
