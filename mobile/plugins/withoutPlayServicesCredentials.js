// SPDX-License-Identifier: Apache-2.0
// Expo config plugin: keep Google Play Services out of the Android app.
// react-native-passkey depends on androidx.credentials:credentials-play-services-auth, which pulls in
// com.google.android.gms:play-services-auth (Android SDK License, proprietary). That bridge is needed
// only for passkeys on Android 13 and older; on Android 14+ androidx.credentials (Apache-2.0) talks to
// the system Credential Manager. Excluding it keeps every linked library under the repo's licence rule.
const { withAppBuildGradle } = require('expo/config-plugins');

const MARK = '// onemind: no Play Services credentials bridge (plugins/withoutPlayServicesCredentials.js)';

function addExclusion(gradle) {
  if (gradle.includes(MARK)) return gradle;
  return `${gradle.trimEnd()}\n\n${MARK}\nconfigurations.all {\n    exclude group: 'androidx.credentials', module: 'credentials-play-services-auth'\n}\n`;
}

const withoutPlayServicesCredentials = (config) =>
  withAppBuildGradle(config, (c) => {
    c.modResults.contents = addExclusion(c.modResults.contents);
    return c;
  });

module.exports = withoutPlayServicesCredentials;
module.exports.addExclusion = addExclusion;
