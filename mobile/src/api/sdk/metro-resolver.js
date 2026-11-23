// SPDX-License-Identifier: Apache-2.0
// Metro's half of the @onemind/sdk alias (metro.config.js installs it; jest-resolver.js is Jest's half).
// The phone bundles the generated gateway client from its source in sdk/ts/src (CI-08, issue 233), the
// same way the dashboard's Vite config and tsconfig.json alias it.
const path = require('node:path');

const sdkSrc = path.resolve(__dirname, '../../../../sdk/ts/src');
// nodeca.ts trusts one CA through Node's https module, which a phone does not have; its dynamic
// import() would also stop Metro's build. The phone gets a stub that says so if anything calls it.
const nodecaStub = path.join(__dirname, 'nodeca.ts');

/**
 * Resolves @onemind/sdk to its source, and the SDK's own `./x.js` imports (TypeScript's ESM
 * spelling) to the `.ts` files next to them. Everything else goes to `next` unchanged.
 */
function resolveSdk(context, moduleName, platform, next) {
  if (moduleName === '@onemind/sdk') return { type: 'sourceFile', filePath: path.join(sdkSrc, 'index.ts') };
  const origin = context.originModulePath || '';
  if (origin.startsWith(sdkSrc + path.sep) && moduleName.startsWith('.') && moduleName.endsWith('.js')) {
    const target = path.resolve(path.dirname(origin), moduleName);
    if (target === path.join(sdkSrc, 'nodeca.js')) return { type: 'sourceFile', filePath: nodecaStub };
    return next(context, moduleName.slice(0, -'.js'.length), platform);
  }
  return next(context, moduleName, platform);
}

module.exports = { resolveSdk, sdkSrc, nodecaStub };
