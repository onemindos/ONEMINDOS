// SPDX-License-Identifier: Apache-2.0
// Metro (the React Native bundler) for the phone app: Expo's defaults plus one addition, the generated
// gateway client @onemind/sdk bundled from its source in ../sdk/ts/src (src/api/sdk/metro-resolver.js).
const path = require('node:path');
const { getDefaultConfig } = require('expo/metro-config');
const { resolveSdk, sdkSrc } = require('./src/api/sdk/metro-resolver');

const config = getDefaultConfig(__dirname);
config.watchFolders = [...(config.watchFolders ?? []), sdkSrc];
// The SDK source has no node_modules of its own: packages it needs (the Babel helpers) come from the app's.
config.resolver.nodeModulesPaths = [...(config.resolver.nodeModulesPaths ?? []), path.join(__dirname, 'node_modules')];
const upstream = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) =>
  // Yjs (notes spike): lib0's React Native crypto import is answered by a small shim, see the file.
  moduleName === 'isomorphic-webcrypto/src/react-native'
    ? { type: 'sourceFile', filePath: path.join(__dirname, 'src/spikes/notes/webcryptoShim.js') }
    : resolveSdk(context, moduleName, platform, upstream ?? context.resolveRequest);

module.exports = config;
