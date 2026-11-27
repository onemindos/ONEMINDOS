// SPDX-License-Identifier: Apache-2.0
const { AndroidConfig, withGradleProperties } = require('expo/config-plugins');

module.exports = (config) => withGradleProperties(config, (c) => {
  for (const key of ['expo.camera.barcode-scanner-enabled', 'expo.camera.document-scanner-enabled']) {
    c.modResults = AndroidConfig.BuildProperties.updateAndroidBuildProperty(c.modResults, key, 'false');
  }
  return c;
});
