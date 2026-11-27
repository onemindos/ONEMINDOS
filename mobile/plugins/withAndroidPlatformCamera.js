// SPDX-License-Identifier: Apache-2.0
const { readFile, writeFile } = require('node:fs/promises');
const path = require('node:path');
const { withFinalizedMod } = require('expo/config-plugins');

module.exports = config => withFinalizedMod(config, ['android', async mod => {
  // Expo's camera prebuild resets its barcode flag to the default. Set the two
  // Android flags after prebuild has finished writing Gradle properties.
  const file = path.join(mod.modRequest.platformProjectRoot, 'gradle.properties');
  const keys = ['expo.camera.barcode-scanner-enabled', 'expo.camera.document-scanner-enabled'];
  const lines = (await readFile(file, 'utf8')).trimEnd().split('\n');
  const remaining = lines.filter(line => !keys.some(key => line.startsWith(key + '=')));
  await writeFile(file, [...remaining, ...keys.map(key => key + '=false'), ''].join('\n'));
  return mod;
}]);
